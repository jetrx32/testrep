import asyncio
import logging
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Состояния для FSM
class FilterStates(StatesGroup):
    waiting_for_time_filter = State()
    waiting_for_liquidity_filter = State()
    waiting_for_price_filter = State()
    waiting_for_spread_filter = State()

class KalshiBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.user_filters = {}
        self.api_url = "https://api.elections.kalshi.com/trade-api/v2/markets"
        
        # Регистрация обработчиков
        self.register_handlers()
    
    def register_handlers(self):
        """Регистрируем все обработчики команд"""
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                "👋 Добро пожаловать в Kalshi Scanner Bot!\n\n"
                "Я помогу найти подходящие рынки на Kalshi по вашим критериям.\n\n"
                "📋 Доступные команды:\n"
                "/filters - Настроить фильтры поиска\n"
                "/search - Начать поиск по фильтрам\n"
                "/current_filters - Показать текущие фильтры\n"
                "/clear_filters - Сбросить фильтры\n"
                "/help - Показать справку\n\n"
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
                "• '1-6' - ближайшие события (1-6 часов)\n"
                "• Или введите свой диапазон в часах\n\n"
                "💰 Ликвидность (общая сумма на рынке):\n"
                "• '5000-10000' - ликвидность от 5000 до 10000\n"
                "• '10000+' - ликвидность более 10000\n"
                "• '1000-5000' - ликвидность от 1000 до 5000\n"
                "• Или введите свой диапазон\n\n"
                "💵 Диапазон цены (в центах):\n"
                "• '85-95' - цена от 85 до 95 центов\n"
                "• '5-20' - цена от 5 до 20 центов\n"
                "• '30-70' - цена от 30 до 70 центов\n\n"
                "📈 Спред (разница между bid и ask в центах):\n"
                "• '0.1-1' - спред от 0.1 до 1 цента\n"
                "• '1-3' - спред от 1 до 3 центов\n"
                "• '3-10' - спред от 3 до 10 центов\n\n"
                "🔍 Поиск может занять некоторое время, так как я анализирую все активные рынки."
            )
            await message.answer(help_text)
        
        @self.dp.message(Command("filters"))
        async def cmd_filters(message: types.Message, state: FSMContext):
            """Начинаем процесс настройки фильтров"""
            await state.set_state(FilterStates.waiting_for_time_filter)
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="1-6"), KeyboardButton(text="6-12")],
                    [KeyboardButton(text="12-24"), KeyboardButton(text="24-48")],
                    [KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await message.answer(
                "⏰ Шаг 1/4: Введите диапазон времени до окончания событий (в часах):\n\n"
                "Примеры:\n"
                "• '1-6' - события, которые завершатся через 1-6 часов\n"
                "• '6-12' - события, которые завершатся через 6-12 часов\n"
                "• '12' - события, которые завершатся через ~12 часов\n\n"
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
                    parts = user_input.split('-')
                    if len(parts) != 2:
                        raise ValueError("Неверный формат")
                    start_h = float(parts[0].strip())
                    end_h = float(parts[1].strip())
                    if start_h < 0 or end_h < 0 or start_h >= end_h:
                        raise ValueError("Неверный диапазон")
                else:
                    hours = float(user_input)
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
            
            await state.set_state(FilterStates.waiting_for_liquidity_filter)
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="1000-5000"), KeyboardButton(text="5000-10000")],
                    [KeyboardButton(text="10000+"), KeyboardButton(text="20000+")],
                    [KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await message.answer(
                "✅ Фильтр времени сохранен!\n\n"
                "💰 Шаг 2/4: Введите фильтр ликвидности:\n\n"
                "Примеры:\n"
                "• '1000-5000'\n"
                "• '5000-10000'\n"
                "• '10000+' - больше или равно 10000\n"
                "• '10000-' - меньше или равно 10000\n\n"
                "Ликвидность - это общая сумма на рынке в долларах.\n"
                "Или введите свой диапазон/условие:",
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
            user_input = message.text.strip()
            
            # Проверяем формат ввода
            try:
                self._parse_filter_input(user_input)
            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат ликвидности. Пожалуйста, введите корректное значение.\n"
                    f"Примеры: '1000-5000', '10000+', '5000-'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return
            
            self.user_filters[user_id]['liquidity'] = user_input
            
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
                "✅ Фильтр ликвидности сохранен!\n\n"
                "💵 Шаг 3/4: Введите диапазон цены (в центах):\n\n"
                "Примеры:\n"
                "• '80-95' - цена от 80 до 95 центов\n"
                "• '5-20' - цена от 5 до 20 центов\n"
                "• '30-70' - цена от 30 до 70 центов\n\n"
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
                self._parse_filter_input(user_input)
                # Дополнительная проверка для цены
                if '-' in user_input:
                    parts = user_input.split('-')
                    min_price = float(parts[0])
                    max_price = float(parts[1])
                    if max_price > 100:
                        raise ValueError("Цена не может превышать 100 центов")
            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат цены. Пожалуйста, введите корректный диапазон.\n"
                    f"Примеры: '80-95' или '5-20'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return
            
            self.user_filters[user_id]['price'] = user_input
            
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
                "✅ Фильтр цены сохранен!\n\n"
                "📈 Шаг 4/4: Введите диапазон спреда (в центах):\n\n"
                "Примеры:\n"
                "• '0.1-1'\n"
                "• '1-3'\n"
                "• '3-5'\n"
                "• '5-10'\n\n"
                "Спред - это разница между лучшей ценой покупки и продажи в центах.\n",
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
                self._parse_filter_input(user_input)
                # Дополнительная проверка для спреда
                if '-' in user_input:
                    parts = user_input.split('-')
                    max_spread = float(parts[1])
                    if max_spread > 100:
                        raise ValueError("Спред не может превышать 100 центов")
            except ValueError as e:
                await message.answer(
                    f"❌ Неверный формат спреда. Пожалуйста, введите корректный диапазон.\n"
                    f"Пример: '0.1-1' или '1-3'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return
            
            self.user_filters[user_id]['spread'] = user_input
            
            await state.clear()
            
            filters = self.user_filters[user_id]
            filters_text = self._format_filters_text(filters)
            
            await message.answer(
                f"🎉 Все фильтры успешно сохранены!\n\n"
                f"📊 Ваши фильтры:\n{filters_text}\n\n"
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
            
            filters_text = self._format_filters_text(filters)
            
            # Проверяем, все ли фильтры заданы
            required_filters = ['time', 'liquidity', 'price', 'spread']
            missing_filters = [f for f in required_filters if f not in filters]
            
            if missing_filters:
                filter_names = {
                    'time': '⏰ время',
                    'liquidity': '💰 ликвидность',
                    'price': '💵 цену',
                    'spread': '📊 спред'
                }
                missing_names = [filter_names[f] for f in missing_filters]
                
                await message.answer(
                    f"📊 Ваши текущие фильтры:\n{filters_text}\n\n"
                    f"⚠️ Для поиска нужно настроить: {', '.join(missing_names)}\n"
                    f"Используйте /filters для настройки недостающих фильтров."
                )
            else:
                await message.answer(
                    f"📊 Ваши текущие фильтры:\n{filters_text}\n\n"
                    f"✅ Все фильтры настроены. Используйте /search для начала поиска."
                )
        
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
            
            # Проверяем, все ли фильтры настроены
            required_filters = ['time', 'liquidity', 'price', 'spread']
            missing_filters = [f for f in required_filters if f not in filters]
            
            if missing_filters:
                filter_names = {
                    'time': 'время',
                    'liquidity': 'ликвидность', 
                    'price': 'цену',
                    'spread': 'спред'
                }
                missing_names = [filter_names[f] for f in missing_filters]
                
                await message.answer(
                    f"❌ Не все фильтры настроены!\n"
                    f"Отсутствуют: {', '.join(missing_names)}\n\n"
                    f"Используйте /filters для настройки всех фильтров.\n"
                    f"Используйте /current_filters для просмотра текущих настроек."
                )
                return
            
            filters_text = self._format_filters_text(filters)
            
            await message.answer(
                f"🔍 Начинаю поиск рынков по вашим фильтрам:\n\n"
                f"{filters_text}\n"
                f"Поиск может занять до 10 минут..."
            )
            
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
    
    def _parse_filter_input(self, text: str) -> Dict:
        """Парсит пользовательский ввод для фильтров"""
        import re
        
        text = text.strip().lower()
        
        # Паттерны
        range_pattern = r'^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$'
        greater_pattern = r'^[>](\d+(?:\.\d+)?)$|^(\d+(?:\.\d+)?)\+$'
        less_pattern = r'^[<](\d+(?:\.\d+)?)$|^(\d+(?:\.\d+)?)-$'
        exact_pattern = r'^(\d+(?:\.\d+)?)$'
        
        # Проверка на диапазон
        match = re.match(range_pattern, text)
        if match:
            min_val = float(match.group(1))
            max_val = float(match.group(2))
            if min_val >= max_val:
                raise ValueError("Минимальное значение должно быть меньше максимального")
            return {"min": min_val, "max": max_val}
        
        # Проверка на "больше"
        match = re.match(greater_pattern, text)
        if match:
            val = float(match.group(1) or match.group(2))
            return {"min": val, "max": None}
        
        # Проверка на "меньше"
        match = re.match(less_pattern, text)
        if match:
            val = float(match.group(1) or match.group(2))
            return {"min": None, "max": val}
        
        # Проверка на точное значение
        match = re.match(exact_pattern, text)
        if match:
            val = float(match.group(1))
            return {"min": val, "max": val}
        
        raise ValueError("Неверный формат")
    
    def _format_filters_text(self, filters: Dict) -> str:
        """Форматирует текст с фильтрами"""
        if not filters:
            return "Фильтры не настроены"
        
        text = ""
        
        for filter_name, filter_value in filters.items():
            if filter_name == 'time':
                name = "⏰ Время"
                unit = "ч"
            elif filter_name == 'liquidity':
                name = "💰 Ликвидность"
                unit = "$"
            elif filter_name == 'price':
                name = "💵 Цена"
                unit = "¢"
            elif filter_name == 'spread':
                name = "📊 Спред"
                unit = "¢"
            else:
                continue
            
            # Парсим значение
            parsed = self._parse_filter_input(filter_value)
            
            if parsed['min'] is not None and parsed['max'] is not None:
                if parsed['min'] == parsed['max']:
                    text += f"{name}: {parsed['min']}{unit}\n"
                else:
                    text += f"{name}: {parsed['min']}-{parsed['max']}{unit}\n"
            elif parsed['min'] is not None:
                text += f"{name}: >{parsed['min']}{unit}\n"
            elif parsed['max'] is not None:
                text += f"{name}: <{parsed['max']}{unit}\n"
        
        return text
    
    async def fetch_all_markets(self) -> List[Dict]:
        """Получает все открытые рынки через API"""
        all_markets = []
        cursor = None
        limit = 1000
        
        async with aiohttp.ClientSession() as session:
            while True:
                params = {
                    'limit': limit,
                    'status': 'open'
                }
                if cursor:
                    params['cursor'] = cursor
                
                try:
                    async with session.get(self.api_url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            markets = data.get('markets', [])
                            all_markets.extend(markets)
                            
                            cursor = data.get('cursor')
                            if not cursor or len(markets) < limit:
                                break
                        else:
                            raise Exception(f"API error: {response.status}")
                except Exception as e:
                    logger.error(f"Error fetching markets: {e}")
                    break
        
        logger.info(f"Fetched {len(all_markets)} markets")
        return all_markets
    
    def filter_markets(self, markets: List[Dict], filters: Dict) -> List[Dict]:
        """Фильтрует рынки по заданным критериям"""
        filtered_markets = []
        
        for market in markets:
            try:
                # Парсим фильтры
                time_filter = self._parse_filter_input(filters['time'])
                liquidity_filter = self._parse_filter_input(filters['liquidity'])
                price_filter = self._parse_filter_input(filters['price'])
                spread_filter = self._parse_filter_input(filters['spread'])
                
                # Проверка времени до окончания
                close_time_str = market.get('close_time')
                if not close_time_str:
                    continue
                
                close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                hours_left = (close_time - now).total_seconds() / 3600
                
                if not self._check_value(hours_left, time_filter):
                    continue
                
                # Проверка ликвидности
                liquidity = market.get('liquidity', 0)
                if not self._check_value(liquidity, liquidity_filter):
                    continue
                
                # Проверка цены
                yes_bid = market.get('yes_bid', 0)
                yes_ask = market.get('yes_ask', 0)
                no_bid = market.get('no_bid', 0)
                no_ask = market.get('no_ask', 0)
                
                # Берем лучшую цену
                best_price = max(yes_bid, no_bid, yes_ask, no_ask)
                
                if not self._check_value(best_price, price_filter):
                    continue
                
                # Проверка спреда
                if yes_ask > 0 and yes_bid > 0:
                    spread_yes = ((yes_ask - yes_bid) / yes_ask) * 100
                else:
                    spread_yes = 100
                
                if no_ask > 0 and no_bid > 0:
                    spread_no = ((no_ask - no_bid) / no_ask) * 100
                else:
                    spread_no = 100
                
                spread = min(spread_yes, spread_no)
                print(spread)
                print(spread_filter)
                print("============================================")
                if not self._check_value(spread, spread_filter):
                    continue
                
                filtered_markets.append(market)
                
            except Exception as e:
                logger.error(f"Error filtering market {market.get('ticker')}: {e}")
                continue
        
        return filtered_markets
    
    def _check_value(self, value: float, filter_dict: Dict) -> bool:
        """Проверяет значение по фильтру"""
        min_val = filter_dict.get('min')
        max_val = filter_dict.get('max')
        
        if min_val is not None and value < min_val:
            return False
        if max_val is not None and value > max_val:
            return False
        
        return True
    
    async def perform_search(self, message: types.Message, filters: dict):
        """Выполняет поиск рынков по фильтрам"""
        try:
            # Шаг 1: Получаем все рынки
            status_msg = await message.answer("1️⃣ Получаю список всех активных рынков с Kalshi...")
            all_markets = await self.fetch_all_markets()
            
            if not all_markets:
                await status_msg.edit_text("❌ Не удалось получить список рынков. Попробуйте позже.")
                return
            
            total_markets = len(all_markets)
            await status_msg.edit_text(f"✅ Найдено {total_markets} активных рынков")
            
            # Шаг 2: Фильтруем по времени
            status_msg = await message.answer("2️⃣ Фильтрую по времени окончания...")
            time_filtered = []
            time_filter = self._parse_filter_input(filters['time'])
            
            for market in all_markets:
                close_time_str = market.get('close_time')
                if not close_time_str:
                    continue
                
                try:
                    close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    hours_left = (close_time - now).total_seconds() / 3600
                    
                    if self._check_value(hours_left, time_filter):
                        time_filtered.append(market)
                except:
                    continue
            
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
            
            # Шаг 3: Фильтруем по ликвидности
            status_msg = await message.answer("3️⃣ Фильтрую по ликвидности...")
            liquidity_filtered = []
            liquidity_filter = self._parse_filter_input(filters['liquidity'])
            
            for market in time_filtered:
                liquidity = market.get('liquidity', 0)
                if self._check_value(liquidity, liquidity_filter):
                    liquidity_filtered.append(market)
            
            if not liquidity_filtered:
                await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр ликвидности")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return
            
            liquidity_filtered_count = len(liquidity_filtered)
            await status_msg.edit_text(f"✅ Осталось {liquidity_filtered_count} рынков после фильтрации по ликвидности")
            
            # Шаг 4: Фильтруем по цене
            status_msg = await message.answer("4️⃣ Фильтрую по цене...")
            price_filtered = []
            price_filter = self._parse_filter_input(filters['price'])
            
            for market in liquidity_filtered:
                yes_bid = market.get('yes_bid', 0)
                yes_ask = market.get('yes_ask', 0)
                no_bid = market.get('no_bid', 0)
                no_ask = market.get('no_ask', 0)
                
                best_price = max(yes_bid, no_bid, yes_ask, no_ask)
                
                if self._check_value(best_price, price_filter):
                    price_filtered.append(market)
            
            if not price_filtered:
                await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр цены")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return
            
            price_filtered_count = len(price_filtered)
            await status_msg.edit_text(f"✅ Осталось {price_filtered_count} рынков после фильтрации по цене")
            
            # Шаг 5: Фильтруем по спреду
            status_msg = await message.answer("5️⃣ Фильтрую по спреду...")
            final_markets = []
            spread_filter = self._parse_filter_input(filters['spread'])
            
            for market in price_filtered:
                yes_bid = market.get('yes_bid', 0)
                yes_ask = market.get('yes_ask', 0)
                no_bid = market.get('no_bid', 0)
                no_ask = market.get('no_ask', 0)
                
                if yes_ask > 0 and yes_bid > 0:
                    spread_yes = ((yes_ask - yes_bid) / yes_ask) * 100
                else:
                    spread_yes = 100
                
                if no_ask > 0 and no_bid > 0:
                    spread_no = ((no_ask - no_bid) / no_ask) * 100
                else:
                    spread_no = 100
                
                spread = min(spread_yes, spread_no)
                
                if self._check_value(spread, spread_filter):
                    final_markets.append(market)
            
            if not final_markets:
                await status_msg.edit_text("❌ Нет рынков, подходящих под все фильтры")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return
            
            final_count = len(final_markets)
            await status_msg.edit_text(f"🎉 Найдено {final_count} подходящих рынков!\n")
            
            # Шаг 6: Выводим результаты
            if final_count == 0:
                await message.answer("😔 Не найдено рынков, соответствующих всем вашим критериям.")
                return
            
            # Сортируем по времени до окончания
            final_markets.sort(key=lambda x: datetime.fromisoformat(
                x.get('close_time', '').replace('Z', '+00:00')
            ) if x.get('close_time') else datetime.max)
            
            # Отправляем сводку
            filters_text = self._format_filters_text(filters)
            
            await message.answer(
                f"📊 Результаты поиска:\n"
                f"🔍 Всего проверено: {total_markets} рынков\n"
                f"⏰ После фильтра времени: {time_filtered_count}\n"
                f"💰 После фильтра ликвидности: {liquidity_filtered_count}\n"
                f"💵 После фильтра цены: {price_filtered_count}\n"
                f"✅ Итоговых результатов: {final_count}\n\n"
                f"{filters_text}\n"
                f"Вот лучшие результаты (макс. 10):"
            )
            
            # Выводим результаты (максимум 10)
            for i, market in enumerate(final_markets[:50]):
                await self.send_market_info_simple(message, market, i+1)
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
            # Основная информация
            title = market.get('title', 'Без названия')
            ticker = market.get('ticker', 'N/A')
            
            # Время до окончания
            close_time_str = market.get('close_time')
            time_left_str = 'N/A'
            if close_time_str:
                try:
                    close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    time_left = close_time - now
                    
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
                except:
                    pass
            
            # Цены
            yes_bid = market.get('yes_bid', 0)
            yes_ask = market.get('yes_ask', 0)
            no_bid = market.get('no_bid', 0)
            no_ask = market.get('no_ask', 0)
            last_price = market.get('last_price', 0)
            
            # Лучшая цена
            best_price = max(yes_bid, no_bid, yes_ask, no_ask)
            
            # Спред
            if yes_ask > 0 and yes_bid > 0:
                spread_yes = ((yes_ask - yes_bid) / yes_ask) * 100
            else:
                spread_yes = 100
            
            if no_ask > 0 and no_bid > 0:
                spread_no = ((no_ask - no_bid) / no_ask) * 100
            else:
                spread_no = 100
            
            spread = min(spread_yes, spread_no)
            
            # Ликвидность и объем
            liquidity = market.get('liquidity', 0)
            volume_24h = market.get('volume_24h', 0)
            
            # Формируем сообщение
            response = f"📊 Рынок #{index}\n"
            response += "─" * 40 + "\n"
            response += f"📌 {title}\n\n"
            
            response += f"🆔 Ticker: {ticker}\n"
            response += f"⏰ До окончания: {time_left_str}\n\n"
            
            # Цены
            response += "💰 Текущие цены:\n"
            response += f"  ✅ YES: bid {yes_bid}¢ / ask {yes_ask}¢\n"
            response += f"  ❌ NO: bid {no_bid}¢ / ask {no_ask}¢\n"
            response += f"  💱 Последняя цена: {last_price}¢\n"
            response += f"  🎯 Лучшая цена: {best_price}¢\n\n"
            
            # Спред
            response += f"📈 Спред: {spread:.2f}¢\n\n"
            
            # Ликвидность и объем
            response += "💵 Объем и ликвидность:\n"
            response += f"  💧 Ликвидность: ${liquidity:,}\n"
            if volume_24h:
                response += f"  📊 24ч объем: {volume_24h:,}\n"
            
            response += "\n" + "─" * 40
            
            await message.answer(response)
            
        except Exception as e:
            logger.error(f"Error sending market info #{index}: {e}", exc_info=True)
            # Минимальная информация
            try:
                basic_info = (
                    f"📊 Рынок #{index}\n"
                    f"📌 {market.get('title', 'Без названия')}\n"
                    f"🆔 Ticker: {market.get('ticker', 'N/A')}\n"
                )
                await message.answer(basic_info)
            except Exception as e2:
                logger.error(f"Error sending minimal info: {e2}")
                await message.answer(f"⚠️ Ошибка при отображении рынка #{index}")
    
    async def run(self):
        """Запускает бота"""
        logger.info("Starting Kalshi Bot...")
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
        print("  2. Или запустите: python kalshi_bot.py ваш_токен")
        sys.exit(1)
    
    # Создаем и запускаем бота
    bot = KalshiBot(bot_token)
    
    try:
        # Запуск бота
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
