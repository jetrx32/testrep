import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketFilters:

    @staticmethod
    def parse_time_filter(hours_range: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Парсит фильтр времени и возвращает диапазон"""
        now = datetime.utcnow().replace(tzinfo=None)

        try:
            if '-' in hours_range:
                # Диапазон часов, например "6-12"
                start_h, end_h = map(int, hours_range.split('-'))
                start_time = now + timedelta(hours=start_h)
                end_time = now + timedelta(hours=end_h)
            else:
                # Одно значение часов, например "12"
                hours = int(hours_range)
                start_time = now + timedelta(hours=hours - 1)
                end_time = now + timedelta(hours=hours)

            return start_time, end_time
        except Exception as e:
            print(f"Error parsing time filter: {e}")
            return None, None

    @staticmethod
    def filter_by_time_range(markets: List[Dict], hours_range: str) -> List[Dict]:
        """Фильтрует рынки по диапазону времени до окончания"""
        start_time, end_time = MarketFilters.parse_time_filter(hours_range)
        if not start_time or not end_time:
            return markets

        filtered_markets = []

        for market in markets:
            end_date_str = market.get('endDate')
            if not end_date_str:
                continue

            try:
                # Парсим дату окончания
                if end_date_str.endswith('Z'):
                    dt_str = end_date_str[:-1] + '+00:00'
                else:
                    dt_str = end_date_str

                market_end = datetime.fromisoformat(dt_str)
                market_end_utc = market_end.replace(tzinfo=None)

                if start_time <= market_end_utc <= end_time:
                    filtered_markets.append(market)
            except Exception as e:
                print(f"Error parsing end date {end_date_str}: {e}")
                continue

        return filtered_markets

    @staticmethod
    def filter_by_spread(markets: List[Dict], spread_range: str) -> List[Dict]:
        """Фильтрует рынки по спреду из данных markets API"""
        try:
            min_spread, max_spread = map(float, spread_range.split('-'))
            # Конвертируем в проценты, если spread в десятичных (например, 0.003 = 0.3%)
            min_spread_percent = min_spread
            max_spread_percent = max_spread

            filtered_markets = []
            for market in markets:
                try:
                    # Получаем спред из данных markets
                    spread_str = market.get('spread')
                    if spread_str is None:
                        continue

                    spread = float(spread_str) * 100  # Конвертируем в проценты

                    # Проверяем, попадает ли спред в диапазон
                    print("============================================")
                    print(min_spread_percent)
                    print(spread)
                    print(max_spread_percent)
                    if min_spread_percent <= spread <= max_spread_percent:
                        filtered_markets.append(market)
                except Exception as e:
                    print(f"Error filtering market by spread: {e}")
                    continue

        except Exception as e:
            print(f"Error parsing spread filter: {e}")
            return markets

        return filtered_markets

    @staticmethod
    def filter_by_combined_price(markets: List[Dict], price_range: str) -> List[Dict]:
        """Фильтрует рынки по цене YES ИЛИ NO"""
        try:
            min_price, max_price = map(float, price_range.split('-'))
            # Конвертируем в десятичные дроби
            min_price_decimal = min_price / 100
            max_price_decimal = max_price / 100

            filtered_markets = []
            for market in markets:
                try:
                    # Получаем цены YES и NO
                    outcome_prices_str = market.get('outcomePrices', '[]')
                    if outcome_prices_str.startswith('"') and outcome_prices_str.endswith('"'):
                        outcome_prices_str = outcome_prices_str[1:-1]
                    outcome_prices_str = outcome_prices_str.replace('\\"', '"')
                    outcome_prices = json.loads(outcome_prices_str)

                    if not outcome_prices or len(outcome_prices) < 2:
                        continue

                    yes_price = float(outcome_prices[0])
                    no_price = float(outcome_prices[1])

                    # Проверяем, попадает ли YES ИЛИ NO в диапазон
                    if (min_price_decimal <= yes_price <= max_price_decimal or
                            min_price_decimal <= no_price <= max_price_decimal):
                        filtered_markets.append(market)
                except Exception as e:
                    print(f"Error filtering market by combined price: {e}")
                    continue

        except Exception as e:
            print(f"Error parsing price filter: {e}")
            return markets

        return filtered_markets

    @staticmethod
    def filter_by_liquidity(markets: List[Dict], liquidity_filter: str) -> List[Dict]:
        """Фильтрует рынки по ликвидности"""
        try:
            filtered_markets = []

            for market in markets:
                try:
                    # Получаем ликвидность из рынка
                    liquidity_str = market.get('liquidity')
                    if not liquidity_str:
                        continue

                    liquidity = float(liquidity_str)

                    # Применяем фильтр в зависимости от формата
                    if '-' in liquidity_filter and '+' not in liquidity_filter:
                        # Диапазон: "10000-50000"
                        min_liquidity, max_liquidity = map(float, liquidity_filter.split('-'))

                        if min_liquidity <= liquidity <= max_liquidity:
                            filtered_markets.append(market)

                    elif '+' in liquidity_filter:
                        # Больше чем: "10000+"
                        min_liquidity = float(liquidity_filter.replace('+', '').strip())

                        if liquidity >= min_liquidity:
                            filtered_markets.append(market)

                    elif liquidity_filter.endswith('-'):
                        # Меньше чем: "10000-"
                        max_liquidity = float(liquidity_filter.replace('-', '').strip())

                        if liquidity <= max_liquidity:
                            filtered_markets.append(market)

                    else:
                        # Диапазон с одним значением: "5000" -> 4000-6000
                        try:
                            target_liquidity = float(liquidity_filter)
                            min_liquidity = target_liquidity * 0.8  # -20%
                            max_liquidity = target_liquidity * 1.2  # +20%

                            if min_liquidity <= liquidity <= max_liquidity:
                                filtered_markets.append(market)
                        except:
                            continue

                except Exception as e:
                    print(f"Error filtering market by liquidity: {e}")
                    continue

            return filtered_markets

        except Exception as e:
            print(f"Error parsing liquidity filter: {e}")
            return markets


class PolymarketAPI:
    def __init__(self):
        self.markets_url = "https://gamma-api.polymarket.com/markets"
        self.orderbook_url = "https://clob.polymarket.com/books"

    async def fetch_all_markets(self) -> List[Dict]:
        """Получает все рынки с учетом пагинации"""
        all_markets = []
        offset = 0
        limit = 100

        async with aiohttp.ClientSession() as session:
            while True:
                params = {
                    'limit': limit,
                    'offset': offset,
                    'closed': 'false'  # Получаем только активные рынки
                }

                try:
                    async with session.get(self.markets_url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            # API возвращает список markets напрямую
                            markets = data if isinstance(data, list) else []

                            if not markets:
                                break

                            all_markets.extend(markets)
                            offset += len(markets)

                            if len(markets) < limit:
                                break
                        else:
                            print(f"Error fetching markets: {response.status}")
                            break
                except Exception as e:
                    print(f"Exception fetching markets: {e}")
                    break

        return all_markets

    async def fetch_orderbooks(self, token_ids: List[str]) -> Dict[str, Dict]:
        """Получает стаканы ордеров для списка токенов"""
        if not token_ids:
            return {}

        # Разбиваем на группы по 100 токенов
        chunks = [token_ids[i:i + 100] for i in range(0, len(token_ids), 100)]
        all_orderbooks = {}

        async with aiohttp.ClientSession() as session:
            for chunk in chunks:
                # Создаем payload в правильном формате
                payload = [{"token_id": token_id} for token_id in chunk]

                try:
                    async with session.post(self.orderbook_url, json=payload) as response:
                        if response.status == 200:
                            data = await response.json()
                            # Ответ - это список словарей, нужно преобразовать в удобный формат
                            for book in data:
                                if isinstance(book, dict) and 'asset_id' in book:
                                    all_orderbooks[book['asset_id']] = book
                except Exception as e:
                    print(f"Error fetching orderbook for chunk: {e}")
                    continue

        return all_orderbooks

    def calculate_spread(self, orderbook: Dict) -> Optional[float]:
        """Рассчитывает спред между лучшим bid и ask в процентах"""
        try:
            if not orderbook:
                return None

            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])

            if not bids or not asks:
                return None

            # Лучший bid (самая высокая цена покупки)
            best_bid = float(bids[0]['price']) if bids else 0
            # Лучший ask (самая низкая цена продажи)
            best_ask = float(asks[0]['price']) if asks else 1

            # Спред в процентах
            spread = (best_ask - best_bid) * 100
            return round(spread, 2)

        except Exception as e:
            print(f"Error calculating spread: {e}")
            return None

    def get_market_tokens(self, market: Dict) -> List[str]:
        """Извлекает clobTokenIds из рынка"""
        try:
            clob_token_ids_str = market.get('clobTokenIds', '[]')
            # Удаляем лишние кавычки и преобразуем JSON строку
            clob_token_ids_str = clob_token_ids_str.replace('\\"', '"').strip('"')
            clob_token_ids = json.loads(clob_token_ids_str)
            return clob_token_ids
        except Exception as e:
            print(f"Error parsing clobTokenIds: {e}")
            return []

    def parse_market_prices(self, market: Dict) -> Dict[str, float]:
        """Парсит цены outcomes из рынка"""
        try:
            outcome_prices_str = market.get('outcomePrices', '[]')
            outcome_prices_str = outcome_prices_str.replace('\\"', '"').strip('"')
            outcome_prices = json.loads(outcome_prices_str)

            outcomes_str = market.get('outcomes', '[]')
            outcomes_str = outcomes_str.replace('\\"', '"').strip('"')
            outcomes = json.loads(outcomes_str)

            return {outcomes[i]: float(outcome_prices[i]) for i in range(len(outcomes))}
        except Exception as e:
            print(f"Error parsing market prices: {e}")
            return {}

    def parse_end_time(self, end_time_str: str) -> Optional[datetime]:
        """Парсит время окончания события"""
        try:
            # Удаляем 'Z' и добавляем информацию о часовом поясе
            if end_time_str.endswith('Z'):
                dt_str = end_time_str[:-1] + '+00:00'
            else:
                dt_str = end_time_str

            dt = datetime.fromisoformat(dt_str)
            return dt.replace(tzinfo=pytz.UTC)
        except Exception as e:
            print(f"Error parsing end time {end_time_str}: {e}")
            return None

    def get_market_info(self, market: Dict) -> Dict[str, Any]:
        """Извлекает основную информацию о рынке"""

        return {
            'id': market.get('id'),
            'question': market.get('question'),
            'conditionId': market.get('conditionId'),
            'slug': market['events'][0]['slug'],
            'endDate': market.get('endDate'),
            'tokens': self.get_market_tokens(market),
            'prices': self.parse_market_prices(market),
            'bestBid': market.get('bestBid'),
            'bestAsk': market.get('bestAsk'),
            'spread': market.get('spread'),
            'volume24hr': market.get('volume24hr'),
            'liquidity': market.get('liquidity')
        }

# Состояния для FSM
class FilterStates(StatesGroup):
    waiting_for_time_filter = State()
    waiting_for_spread_filter = State()
    waiting_for_price_filter = State()
    waiting_for_liquidity_filter = State()


class PolymarketBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.api = PolymarketAPI()
        self.user_filters = {}

        # Регистрация обработчиков
        self.register_handlers()

    def register_handlers(self):
        """Регистрируем все обработчики команд"""

        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                "👋 Добро пожаловать в Polymarket Scanner Bot!\n\n"
                "Я помогу найти подходящие рынки на Polymarket по вашим критериям.\n\n"
                "📋 Доступные команды:\n"
                "/filters - Настроить фильтры поиска\n"
                "/search - Начать поиск по фильтрам\n"
                "/current_filters - Показать текущие фильтры\n"
                "/clear_filters - Сбросить фильтры\n"
                "/help - Показать справка\n\n"
                "Для начала настройте фильтры с помощью /filters"
            )

        @self.dp.message(Command("help"))
        async def cmd_help(message: types.Message):
            help_text = (
                "📋 Команды бота:\n\n"
                "/start - Начать работу с ботом\n"
                "/filters - Настроить фильтры поиска\n"
                "/search - Начать поиск по фильтрам\n"
                "/current_filters - Показать текущие фильтры\n"
                "/clear_filters - Сбросить фильтры\n"
                "/help - Эта справка\n\n"
                "📝 Форматы ввода фильтров:\n\n"
                "⏰ Время до окончания (в часах):\n"
                "• '6-12' - события, которые завершатся через 6-12 часов\n"
                "• '12' - события, которые завершатся примерно через 12 часов\n"
                "• Или введите свой диапазон в часах\n\n"
                "📈 Спред (разница между лучшей ценой покупки и продажи в %):\n"
                "• '0.1-1' - спред от 0.1% до 1% \n"
                "• '1-3' - спред от 1% до 3% \n"
                "• '3-10' - спред от 3% до 10% \n\n"
                "💰 Диапазон цены (в центах):\n"
                "• '80-95' - цена от 80 до 95 центов\n"
                "• '5-20' - цена от 5 до 20 центов\n"
                "• '30-70' - цена от 30 до 70 центов для YES или NO\n\n"
                "💵 Фильтр по ликвидности (в долларах):\n"
                "• '10000-50000' - ликвидность от $10K до $50K\n"
                "• '10000+' - ликвидность от $10K и выше\n"
                "• '10000-' - ликвидность до $10K\n"
                "• '5000' - ликвидность около $5K (±20%)\n\n"
                "🔍 Поиск может занять некоторое время, так как я анализирую все активные рынки."
            )
            await message.answer(help_text)

        @self.dp.message(Command("filters"))
        async def cmd_filters(message: types.Message, state: FSMContext):
            """Начинаем процесс настройки фильтров"""
            await state.set_state(FilterStates.waiting_for_time_filter)

            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="6-12"), KeyboardButton(text="12-24")],
                    [KeyboardButton(text="24-48"), KeyboardButton(text="48-72")],
                    [KeyboardButton(text="1-6"), KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )

            await message.answer(
                "⏰ Шаг 1/4: Введите диапазон времени до окончания событий (в часах):\n\n"
                "Примеры:\n"
                "• '6-12' - события, которые завершатся через 6-12 часов\n"
                "• '12' - события, которые завершатся через ~12 часов\n"
                "• '24-48' - события, которые завершатся через 24-48 часов\n\n"
                "Или выберите один из вариантов ниже:\n",
                reply_markup=keyboard
            )

        @self.dp.message(FilterStates.waiting_for_time_filter, F.text.lower() != "отмена")
        async def process_time_filter(message: types.Message, state: FSMContext):
            user_id = message.from_user.id
            user_input = message.text.strip()

            # Проверяем формат ввода
            try:
                if '-' in user_input:
                    # Проверяем, что это два числа через дефис
                    parts = user_input.split('-')
                    if len(parts) != 2:
                        raise ValueError("Неверный формат")
                    start_h = int(parts[0].strip())
                    end_h = int(parts[1].strip())
                    if start_h < 0 or end_h < 0 or start_h >= end_h:
                        raise ValueError("Неверный диапазон")
                else:
                    # Проверяем, что это число
                    hours = int(user_input)
                    if hours <= 0:
                        raise ValueError("Время должно быть положительным")
            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат времени. Пожалуйста, введите корректный диапазон часов.\n"
                    f"Примеры: '6-12' или '12'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            # Инициализируем фильтры для пользователя, если их нет
            if user_id not in self.user_filters:
                self.user_filters[user_id] = {}

            self.user_filters[user_id]['time'] = user_input

            await state.set_state(FilterStates.waiting_for_spread_filter)

            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="0.1-1"), KeyboardButton(text="1-3")],
                    [KeyboardButton(text="3-5"), KeyboardButton(text="5-10")],
                    [KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )

            await message.answer(
                "✅ Фильтр времени сохранен!\n\n"
                "📈 Шаг 2/4: Введите диапазон спреда (в центах):\n\n"
                "Примеры:\n"
                "• '0.1-1'\n"
                "• '1-3'\n"
                "• '3-5'\n"
                "• '5-10'\n\n"
                "Спред - это разница между лучшей ценой покупки и продажи в центах.\n"
                "Меньший спред = больше ликвидность.",
                reply_markup=keyboard
            )

        @self.dp.message(FilterStates.waiting_for_spread_filter)
        async def process_spread_filter(message: types.Message, state: FSMContext):
            if message.text.lower() == "отмена":
                await state.clear()
                await message.answer(
                    "❌ Настройка фильтров отменена",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            user_id = message.from_user.id
            user_input = message.text.strip()

            # Проверяем формат ввода
            try:
                if '-' not in user_input:
                    raise ValueError("Используйте формат 'мин-макс'")

                parts = user_input.split('-')
                if len(parts) != 2:
                    raise ValueError("Неверный формат")

                min_spread = float(parts[0].strip())
                max_spread = float(parts[1].strip())

                if min_spread < 0 or max_spread < 0 or min_spread >= max_spread:
                    raise ValueError("Неверный диапазон")

                if max_spread > 100:
                    raise ValueError("Спред не может превышать 100%")

            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат спреда. Пожалуйста, введите корректный диапазон.\n"
                    f"Пример: '0.1-1' или '1-3'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            self.user_filters[user_id]['spread'] = user_input

            await state.set_state(FilterStates.waiting_for_price_filter)

            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="80-95"), KeyboardButton(text="5-20")],
                    [KeyboardButton(text="30-70"), KeyboardButton(text="10-40")],
                    [KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )

            await message.answer(
                "✅ Фильтр спреда сохранен!\n\n"
                "💰 Шаг 3/4: Введите диапазон цены YES или NO (в центах):\n\n"
                "Примеры:\n"
                "• '80-95' - цена от 80 до 95 центов\n"
                "• '5-20' - цена от 5 до 20 центов\n"
                "• '30-70' - цена от 30 до 70 центов для YES или NO\n\n"
                "Это диапазон текущей цены события.\n"
                "Цены вводятся в центах (1$ = 100¢).",
                reply_markup=keyboard
            )

        @self.dp.message(FilterStates.waiting_for_price_filter)
        async def process_price_filter(message: types.Message, state: FSMContext):
            if message.text.lower() == "отмена":
                await state.clear()
                await message.answer(
                    "❌ Настройка фильтров отменена",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            user_id = message.from_user.id
            user_input = message.text.strip()

            # Проверяем формат ввода
            try:
                if '-' not in user_input:
                    raise ValueError("Используйте формат 'мин-макс'")

                parts = user_input.split('-')
                if len(parts) != 2:
                    raise ValueError("Неверный формат")

                min_price = float(parts[0].strip())
                max_price = float(parts[1].strip())

                if min_price < 0 or max_price < 0 or min_price >= max_price:
                    raise ValueError("Неверный диапазон")

                if max_price > 100:
                    raise ValueError("Цена не может превышать 100 центов")

            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат цены. Пожалуйста, введите корректный диапазон.\n"
                    f"Пример: '80-95' или '5-20'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            self.user_filters[user_id]['price'] = user_input

            await state.set_state(FilterStates.waiting_for_liquidity_filter)

            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="10000+"), KeyboardButton(text="5000-20000")],
                    [KeyboardButton(text="1000-5000"), KeyboardButton(text="50000+")],
                    [KeyboardButton(text="Пропустить"), KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )

            await message.answer(
                "✅ Фильтр цены сохранен!\n\n"
                "💵 Шаг 4/4: Введите фильтр по ликвидности (в долларах):\n\n"
                "Примеры:\n"
                "• '10000-50000' - ликвидность от $10K до $50K\n"
                "• '10000+' - ликвидность от $10K и выше\n"
                "• '10000-' - ликвидность до $10K\n"
                "• '5000' - ликвидность около $5K (±20%)\n"
                "• 'Пропустить' - без фильтра по ликвидности\n\n"
                "Ликвидность - это общая сумма в долларах, доступная для торгов на рынке.\n"
                "Высокая ликвидность = легче торговать большими объемами.",
                reply_markup=keyboard
            )

        @self.dp.message(FilterStates.waiting_for_liquidity_filter)
        async def process_liquidity_filter(message: types.Message, state: FSMContext):
            if message.text.lower() == "отмена":
                await state.clear()
                await message.answer(
                    "❌ Настройка фильтров отменена",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            user_id = message.from_user.id

            if message.text.lower() == "пропустить":
                self.user_filters[user_id]['liquidity'] = None
                await state.clear()

                filters = self.user_filters[user_id]
                await message.answer(
                    "🎉 Все фильтры успешно сохранены!\n\n"
                    f"📊 Ваши фильтры:\n"
                    f"⏰ Время: {filters['time']} часов\n"
                    f"📈 Спред: {filters['spread']}%\n"
                    f"💰 Цена: {filters['price']} центов\n"
                    f"💵 Ликвидность: без фильтра\n\n"
                    "Теперь вы можете начать поиск с помощью команды /search\n"
                    "Используйте /current_filters для просмотра фильтров\n"
                    "Используйте /clear_filters для сброса фильтров",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            user_input = message.text.strip()

            # Проверяем формат ввода
            try:
                # Поддерживаемые форматы:
                # 1. Диапазон: "10000-50000"
                # 2. Больше чем: "10000+"
                # 3. Меньше чем: "10000-"
                # 4. Примерное значение: "5000"

                if '-' in user_input and '+' not in user_input:
                    # Диапазон
                    if user_input.count('-') != 1:
                        raise ValueError("Неверный формат диапазона")

                    parts = user_input.split('-')
                    min_liquidity = float(parts[0].strip())
                    max_liquidity = float(parts[1].strip())

                    if min_liquidity < 0 or max_liquidity < 0 or min_liquidity >= max_liquidity:
                        raise ValueError("Неверный диапазон ликвидности")

                    self.user_filters[user_id]['liquidity'] = f"{min_liquidity}-{max_liquidity}"

                elif '+' in user_input:
                    # Больше чем
                    value = float(user_input.replace('+', '').strip())
                    if value < 0:
                        raise ValueError("Ликвидность не может быть отрицательной")

                    self.user_filters[user_id]['liquidity'] = f"{value}+"

                elif user_input.endswith('-'):
                    # Меньше чем
                    value = float(user_input.replace('-', '').strip())
                    if value < 0:
                        raise ValueError("Ликвидность не может быть отрицательной")

                    self.user_filters[user_id]['liquidity'] = f"{value}-"

                else:
                    # Примерное значение (±20%)
                    try:
                        value = float(user_input)
                        if value < 0:
                            raise ValueError("Ликвидность не может быть отрицательной")

                        min_val = value * 0.8  # -20%
                        max_val = value * 1.2  # +20%
                        self.user_filters[user_id]['liquidity'] = f"{min_val:.0f}-{max_val:.0f}"
                    except:
                        raise ValueError("Неверный формат ликвидности")

            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат ликвидности. Пожалуйста, введите корректный фильтр.\n"
                    f"Примеры: '10000-50000', '10000+', '10000-', '5000'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return

            await state.clear()

            filters = self.user_filters[user_id]
            liquidity_filter = filters.get('liquidity', 'без фильтра')

            await message.answer(
                "🎉 Все фильтры успешно сохранены!\n\n"
                f"📊 Ваши фильтры:\n"
                f"⏰ Время: {filters['time']} часов\n"
                f"📈 Спред: {filters['spread']}%\n"
                f"💰 Цена: {filters['price']} центов\n"
                f"💵 Ликвидность: {liquidity_filter}\n\n"
                "Теперь вы можете начать поиск с помощью команды /search\n"
                "Используйте /current_filters для просмотра фильтров\n"
                "Используйте /clear_filters для сброса фильтров",
                reply_markup=types.ReplyKeyboardRemove()
            )

        @self.dp.message(Command("current_filters"))
        async def cmd_current_filters(message: types.Message):
            """Показываем текущие фильтры пользователя"""
            user_id = message.from_user.id
            filters = self.user_filters.get(user_id, {})

            if not filters:
                await message.answer("❌ Фильтры не настроены. Используйте /filters для настройки.")
                return

            response = "📊 Ваши текущие фильтры:\n\n"

            time_filter = filters.get('time', 'Не задан')
            spread_filter = filters.get('spread', 'Не задан')
            price_filter = filters.get('price', 'Не задан')
            liquidity_filter = filters.get('liquidity', 'Не задан')

            response += f"⏰ Время до окончания: {time_filter} часов\n"
            response += f"📈 Диапазон спреда: {spread_filter}%\n"
            response += f"💰 Диапазон цены: {price_filter} центов\n"

            if liquidity_filter is None:
                response += f"💵 Ликвидность: без фильтра\n"
            else:
                response += f"💵 Ликвидность: {liquidity_filter}\n"

            # Проверяем, все ли обязательные фильтры заданы
            required_filters = ['time', 'spread', 'price']
            missing_filters = []
            for req in required_filters:
                if req not in filters:
                    missing_filters.append({
                                               'time': 'время',
                                               'spread': 'спред',
                                               'price': 'цена'
                                           }[req])

            if missing_filters:
                response += f"\n⚠️ Для поиска нужно настроить: {', '.join(missing_filters)}\n"
                response += "Используйте /filters для настройки недостающих фильтров."
            else:
                response += "\n✅ Все обязательные фильтры настроены. Используйте /search для начала поиска."

            await message.answer(response)

        @self.dp.message(Command("clear_filters"))
        async def cmd_clear_filters(message: types.Message):
            """Сбрасываем фильтры пользователя"""
            user_id = message.from_user.id
            if user_id in self.user_filters:
                self.user_filters[user_id] = {}
                await message.answer("✅ Все фильтры успешно сброшены.")
            else:
                await message.answer("ℹ️ У вас нет сохраненных фильтров.")

        @self.dp.message(Command("search"))
        async def cmd_search(message: types.Message):
            """Начинаем поиск по фильтрам"""
            user_id = message.from_user.id
            filters = self.user_filters.get(user_id, {})

            # Проверяем, все ли обязательные фильтры настроены
            required_filters = ['time', 'spread', 'price']
            missing_filters = [f for f in required_filters if f not in filters]

            if missing_filters:
                filter_names = {
                    'time': 'время',
                    'spread': 'спред',
                    'price': 'цена'
                }
                missing_names = [filter_names[f] for f in missing_filters]

                await message.answer(
                    f"❌ Не все обязательные фильтры настроены!\n"
                    f"Отсутствуют: {', '.join(missing_names)}\n\n"
                    f"Используйте /filters для настройки всех фильтров.\n"
                    f"Используйте /current_filters для просмотра текущих настроек."
                )
                return

            # Формируем сообщение о фильтрах
            filters_text = (
                f"🔍 Начинаю поиск рынков по вашим фильтрам:\n\n"
                f"⏰ Время: {filters['time']} часов\n"
                f"📈 Спред: {filters['spread']}%\n"
                f"💰 Цена: {filters['price']} центов\n"
            )

            if 'liquidity' in filters and filters['liquidity'] is not None:
                filters_text += f"💵 Ликвидность: {filters['liquidity']}\n"
            else:
                filters_text += "💵 Ликвидность: без фильтра\n"

            filters_text += "\nПоиск может занять до 30 секунд..."

            await message.answer(filters_text)

            # Запускаем поиск
            await self.perform_search(message, filters)

        @self.dp.message(F.text.lower() == "отмена")
        async def cancel_handler(message: types.Message, state: FSMContext):
            current_state = await state.get_state()
            if current_state is not None:
                await state.clear()
                await message.answer(
                    "❌ Настройка фильтров отменена",
                    reply_markup=types.ReplyKeyboardRemove()
                )

        @self.dp.message()
        async def handle_other_messages(message: types.Message):
            """Обработка всех остальных сообщений"""
            await message.answer(
                "Я не понимаю эту команду. Используйте /help для просмотра доступных команд."
            )

    async def perform_search(self, message: types.Message, filters: dict):
        """Выполняет поиск рынков по фильтрам"""
        try:
            # Шаг 1: Получаем все рынки
            status_msg = await message.answer("1️⃣ Получаю список всех активных рынков...")
            all_markets = await self.api.fetch_all_markets()

            if not all_markets:
                await status_msg.edit_text("❌ Не удалось получить список рынков. Попробуйте позже.")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return

            total_markets = len(all_markets)
            await status_msg.edit_text(f"✅ Найдено {total_markets} активных рынков")

            # Шаг 2: Фильтруем по времени
            status_msg = await message.answer("2️⃣ Фильтрую по времени окончания...")
            time_filtered = MarketFilters.filter_by_time_range(
                all_markets,
                filters['time']
            )

            if not time_filtered:
                await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр времени")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return

            time_filtered_count = len(time_filtered)
            await status_msg.edit_text(f"✅ Осталось {time_filtered_count} рынков после фильтрации по времени")

            # Шаг 3: Фильтруем по спреду
            status_msg = await message.answer("3️⃣ Фильтрую по спреду...")
            spread_filtered = MarketFilters.filter_by_spread(
                time_filtered,
                filters['spread']
            )

            if not spread_filtered:
                await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр спреда")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return

            spread_filtered_count = len(spread_filtered)
            await status_msg.edit_text(f"✅ Осталось {spread_filtered_count} рынков после фильтрации по спреду")

            # Шаг 4: Фильтруем по цене
            status_msg = await message.answer("4️⃣ Фильтрую по цене...")
            final_markets = MarketFilters.filter_by_combined_price(
                spread_filtered,
                filters['price']
            )

            if not final_markets:
                await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр цены")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return

            price_filtered_count = len(final_markets)
            await status_msg.edit_text(f"✅ Осталось {price_filtered_count} рынков после фильтрации по цене")

            # Шаг 5: Фильтруем по ликвидности (если задан фильтр)
            if 'liquidity' in filters and filters['liquidity'] is not None:
                status_msg = await message.answer("5️⃣ Фильтрую по ликвидности...")
                liquidity_filtered = MarketFilters.filter_by_liquidity(
                    final_markets,
                    filters['liquidity']
                )

                if not liquidity_filtered:
                    await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр ликвидности")
                    await message.answer(
                        "🔍 Хотите найти другие рынки?\n"
                        "Используйте /filters для изменения критериев поиска\n"
                        "Используйте /search для повторного поиска с текущими фильтрами"
                    )
                    return

                final_markets = liquidity_filtered

            final_count = len(final_markets)

            if 'liquidity' in filters and filters['liquidity'] is not None:
                await status_msg.edit_text(f"✅ Осталось {final_count} рынков после фильтрации по ликвидности")
            else:
                await status_msg.edit_text(f"✅ Итоговых результатов: {final_count}")

            # Шаг 6: Выводим результаты
            if final_count == 0:
                await message.answer("😔 Не найдено рынков, соответствующих всем вашим критериям.")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return

            # Отправляем сводку
            summary_text = (
                f"📊 Результаты поиска:\n"
                f"🔍 Всего проверено: {total_markets} рынков\n"
                f"⏰ После фильтра времени: {time_filtered_count}\n"
                f"📈 После фильтра спреда: {spread_filtered_count}\n"
                f"💰 После фильтра цены: {price_filtered_count}\n"
            )

            if 'liquidity' in filters and filters['liquidity'] is not None:
                summary_text += f"💵 После фильтра ликвидности: {final_count}\n"
            else:
                summary_text += f"✅ Итоговых результатов: {final_count}\n"

            summary_text += (
                f"\n📋 Ваши фильтры:\n"
                f"⏰ Время: {filters['time']} часов\n"
                f"📈 Спред: {filters['spread']}%\n"
                f"💰 Цена: {filters['price']} центов\n"
            )

            if 'liquidity' in filters and filters['liquidity'] is not None:
                summary_text += f"💵 Ликвидность: {filters['liquidity']}\n"

            summary_text += f"\nВот лучшие результаты (макс. 50 пока):"

            await message.answer(summary_text)

            # Выводим результаты (максимум 10)
            for i, market in enumerate(final_markets[:50]):
                await self.send_market_info_simple(message, market, i + 1)
                await asyncio.sleep(0.3)  # Чтобы не превысить лимиты Telegram

            if final_count > 50:
                await message.answer(f"\n📈 ... и еще {final_count - 50} рынков не показаны.")

            # Предложение изменить фильтры
            await message.answer(
                "🔍 Хотите найти другие рынки?\n"
                "Используйте /filters для изменения критериев поиска\n"
                "Используйте /search для повторного поиска с текущими фильтрами"
            )

        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            await message.answer(
                f"❌ Произошла ошибка при поиске:\n\n"
                f"Ошибка: {str(e)}\n\n"
                f"Пожалуйста, попробуйте позже или измените фильтры."
            )

    async def send_market_info_simple(self, message: types.Message, market: Dict, index: int):
        """Отправляет упрощенную информацию о рынке"""
        try:
            # Получаем основные данные
            question = market.get('question', 'Без названия')
            market_id = market.get('id', 'N/A')
            slug = market["events"][0]["slug"]

            # Получаем цены YES/NO
            yes_price = None
            no_price = None
            try:
                outcome_prices_str = market.get('outcomePrices', '[]')
                if outcome_prices_str.startswith('"') and outcome_prices_str.endswith('"'):
                    outcome_prices_str = outcome_prices_str[1:-1]
                outcome_prices_str = outcome_prices_str.replace('\\"', '"')
                outcome_prices = json.loads(outcome_prices_str)

                if len(outcome_prices) >= 2:
                    yes_price = float(outcome_prices[0])
                    no_price = float(outcome_prices[1])
            except Exception as e:
                logger.debug(f"Error parsing prices: {e}")
                yes_price = None
                no_price = None

            # Получаем лучшие bid/ask и спред
            best_bid = market.get('bestBid')
            best_ask = market.get('bestAsk')
            spread = market.get('spread')
            last_trade = market.get('lastTradePrice')

            # Получаем ликвидность
            liquidity = market.get('liquidity')
            liquidity_num = None
            if liquidity:
                try:
                    liquidity_num = float(liquidity)
                except:
                    pass

            # Время окончания
            time_left_str = 'N/A'
            end_date = market.get('endDate')
            if end_date:
                try:
                    market_end = self.api.parse_end_time(end_date)
                    if market_end:
                        now = datetime.utcnow().replace(tzinfo=None)
                        market_end_utc = market_end.replace(tzinfo=None)
                        time_left = market_end_utc - now

                        if time_left.total_seconds() > 0:
                            hours_left = int(time_left.total_seconds() / 3600)
                            days_left = hours_left // 24
                            remaining_hours = hours_left % 24

                            if days_left > 0:
                                time_left_str = f"{days_left}д {remaining_hours}ч"
                            else:
                                time_left_str = f"{hours_left}ч"
                        else:
                            time_left_str = "Завершено"
                except Exception as e:
                    logger.debug(f"Error parsing end date: {e}")
                    pass

            # Объем
            volume_24h = market.get('volume24hr')

            # Формируем сообщение
            response = f"📊 Рынок #{index}\n"
            response += "─" * 40 + "\n"
            response += f"📌 {question}\n\n"

            response += f"🆔 ID: {market_id}\n"
            response += f"⏰ До окончания: {time_left_str}\n\n"

            # Цены YES/NO
            response += "💰 Текущие цены:\n"
            if yes_price is not None:
                response += f"  ✅ YES: {yes_price:.3f} ({yes_price * 100:.1f}¢)\n"
            if no_price is not None:
                response += f"  ❌ NO: {no_price:.3f} ({no_price * 100:.1f}¢)\n"

            # Лучшие ордера и спред
            if best_bid or best_ask or spread or last_trade:
                response += "\n📊 Торговая информация:\n"

                if best_bid:
                    try:
                        bid_value = float(best_bid)
                        response += f"  🔺 Лучший bid: {bid_value:.3f} ({bid_value * 100:.1f}¢)\n"
                    except:
                        pass

                if best_ask:
                    try:
                        ask_value = float(best_ask)
                        response += f"  🔻 Лучший ask: {ask_value:.3f} ({ask_value * 100:.1f}¢)\n"
                    except:
                        pass

                if spread:
                    try:
                        spread_value = float(spread) * 100
                        response += f"  📈 Спред: {spread_value:.2f}¢\n"
                    except:
                        pass

                if last_trade:
                    try:
                        trade_value = float(last_trade)
                        response += f"  💱 Последняя сделка: {trade_value:.3f} ({trade_value * 100:.1f}¢)\n"
                    except:
                        pass

            # Ликвидность и объем
            if liquidity_num or volume_24h:
                response += "\n💵 Финансовые показатели:\n"

                if liquidity_num is not None:
                    if liquidity_num >= 1000:
                        response += f"  💧 Ликвидность: ${liquidity_num:,.0f}\n"
                    else:
                        response += f"  💧 Ликвидность: ${liquidity_num:,.2f}\n"

                if volume_24h:
                    try:
                        volume_value = float(volume_24h)
                        if volume_value >= 1000:
                            response += f"  📊 24ч объем: ${volume_value:,.0f}\n"
                        else:
                            response += f"  📊 24ч объем: ${volume_value:,.2f}\n"
                    except:
                        pass

            # Ссылка
            if slug:
                response += f"\n🔗 Ссылка: https://polymarket.com/event/{slug}"

            response += "\n" + "─" * 40

            await message.answer(response)

        except Exception as e:
            logger.error(f"Error sending market info #{index}: {e}", exc_info=True)
            # Минимальная информация
            try:
                basic_info = (
                    f"📊 Рынок #{index}\n"
                    f"📌 {market.get('question', 'Без названия')}\n"
                    f"🆔 ID: {market.get('id', 'N/A')}\n"
                )

                slug = market.get('slug')
                if slug:
                    basic_info += f"\n🔗 https://polymarket.com/event/{slug}"

                await message.answer(basic_info)
            except Exception as e2:
                logger.error(f"Error sending minimal info: {e2}")
                await message.answer(f"⚠️ Ошибка при отображении рынка #{index}")

    async def run(self):
        """Запускает бота"""
        logger.info("Starting Polymarket Bot...")
        await self.dp.start_polling(self.bot)


# Точка входа
if __name__ == "__main__":
    import sys
    import os
    from dotenv import load_dotenv

    # Загружаем переменные окружения
    load_dotenv()

    # Получаем токен из переменных окружения или аргументов
    if len(sys.argv) > 1:
        bot_token = sys.argv[1]
    else:
        bot_token = os.getenv('BOT_TOKEN')

    if not bot_token:
        print("❌ Ошибка: Токен бота не найден!")
        print("Использование:")
        print("  1. Создайте файл .env с BOT_TOKEN=ваш_токен")
        print("  2. Или запустите: python main.py ваш_токен")
        sys.exit(1)

    # Создаем и запускаем бота
    bot = PolymarketBot(bot_token)

    try:
        # Запуск бота
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
