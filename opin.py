import asyncio
import logging
import aiohttp
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
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
    waiting_for_volume_filter = State()
    waiting_for_price_filter = State()
    waiting_for_spread_filter = State()

class OpinionBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.user_filters = {}
        self.base_api_url = "https://proxy.opinion.trade:8443/api/bsc/api/v2/topic"
        
        # Регистрация обработчиков
        self.register_handlers()
    
    def register_handlers(self):
        """Регистрируем все обработчики команд"""
        @self.dp.message(Command("start"))
        async def cmd_start(message: types.Message):
            await message.answer(
                "👋 Добро пожаловать в Opinion Trade Scanner Bot!\n\n"
                "Я помогу найти подходящие рынки на Opinion Trade по вашим критериям.\n\n"
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
                "💰 Объем торгов (TVL):\n"
                "• '1000-5000' - объем от 1000 до 5000\n"
                "• '5000+' - объем более 5000\n"
                "• '100-1000' - небольшой объем\n"
                "• Или введите свой диапазон\n\n"
                "💵 Диапазон цены (в центах):\n"
                "• '80-95' - цена от 80 до 95 центов\n"
                "• '5-20' - цена от 5 до 20 центов\n"
                "• '30-70' - цена от 30 до 70 центов\n\n"
                "📈 Спред (разница между bid и ask в центах):\n"
                "• '0.1-1' - спред от 0.1 до 1\n"
                "• '1-3' - спред от 1 до 3\n"
                "• '3-10' - спред от 3 до 10\n\n"
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
                self._parse_filter_input(user_input)
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
            
            await state.set_state(FilterStates.waiting_for_volume_filter)
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="100-1000"), KeyboardButton(text="1000-5000")],
                    [KeyboardButton(text="5000+"), KeyboardButton(text="10000+")],
                    [KeyboardButton(text="100000+"), KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await message.answer(
                "✅ Фильтр времени сохранен!\n\n"
                "💰 Шаг 2/4: Введите фильтр объема торгов (TVL):\n\n"
                "Примеры:\n"
                "• '100-1000' - небольшой объем\n"
                "• '1000-5000' - средний объем\n"
                "• '5000+' - большой объем\n"
                "• '100000+' - очень большой объем\n\n"
                "Объем торгов (TVL) - это общая заблокированная стоимость в долларах.\n"
                "Или введите свой диапазон/условие:",
                reply_markup=keyboard
            )
        
        @self.dp.message(FilterStates.waiting_for_volume_filter)
        async def process_volume_filter(message: types.Message, state: FSMContext):
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
                    f"❌ Неверный формат объема. Пожалуйста, введите корректное значение.\n"
                    f"Примеры: '1000-5000', '5000+', '1000-'\n",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                return
            
            self.user_filters[user_id]['volume'] = user_input
            
            await state.set_state(FilterStates.waiting_for_price_filter)
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="80-95"), KeyboardButton(text="5-20")],
                    [KeyboardButton(text="30-70"), KeyboardButton(text="10-40")],
                    [KeyboardButton(text="45-55"), KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await message.answer(
                "✅ Фильтр объема сохранен!\n\n"
                "💵 Шаг 3/4: Введите диапазон цены YES (в центах):\n\n"
                "Примеры:\n"
                "• '80-95' - высокая вероятность (цена YES от 80 до 95 центов)\n"
                "• '5-20' - низкая вероятность (цена YES от 5 до 20 центов)\n"
                "• '30-70' - средняя вероятность\n"
                "• '45-55' - примерно 50/50\n\n"
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
                    [KeyboardButton(text="10-20"), KeyboardButton(text="Отмена")],
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            
            await message.answer(
                "✅ Фильтр цены сохранен!\n\n"
                "📈 Шаг 4/4: Введите диапазон спреда (в центах):\n\n"
                "Примеры:\n"
                "• '0.1-1' - очень маленький спред\n"
                "• '1-3' - маленький спред\n"
                "• '3-5' - средний спред\n"
                "• '5-10' - большой спред\n\n"
                "Спред - это разница между ценой покупки и продажи в процентах.",
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
            required_filters = ['time', 'volume', 'price', 'spread']
            missing_filters = [f for f in required_filters if f not in filters]
            
            if missing_filters:
                filter_names = {
                    'time': '⏰ время',
                    'volume': '💰 объем',
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
            required_filters = ['time', 'volume', 'price', 'spread']
            missing_filters = [f for f in required_filters if f not in filters]
            
            if missing_filters:
                filter_names = {
                    'time': 'время',
                    'volume': 'объем', 
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
                f"Поиск может занять до 2 минут..."
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
                name = "⏰ Время до окончания"
                unit = "ч"
            elif filter_name == 'volume':
                name = "💰 Объем торгов"
                unit = "$"
            elif filter_name == 'price':
                name = "💵 Цена YES"
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
        """Получает все активные рынки через API Opinion Trade"""
        all_child_markets = []  # Будем собирать все childList элементы
        page = 1
        limit = 12
        
        async with aiohttp.ClientSession() as session:
            while True:
                params = {
                    'labelId': '',
                    'keywords': '',
                    'sortBy': '5',  # Сортировка
                    'chainId': '56',  # BSC
                    'limit': str(limit),
                    'status': '2',  # Активные рынки
                    'isShow': '1',
                    'topicType': '2',
                    'page': str(page),
                    'indicatorType': '0',
                    'excludePin': '1'
                }
                
                try:
                    async with session.get(self.base_api_url, params=params, ssl=False) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Получаем список событий
                            events = []
                            if isinstance(data, dict):
                                if 'result' in data and 'list' in data['result']:
                                    events = data['result']['list']
                                elif 'list' in data:
                                    events = data['list']
                            
                            if not events:
                                logger.info(f"Page {page}: No events found")
                                break
                            
                            # Собираем все childList элементы из каждого события
                            for event in events:
                                if 'childList' in event and isinstance(event['childList'], list):
                                    # Добавляем информацию о родительском событии в каждый child
                                    for child in event['childList']:
                                        # Добавляем информацию о родительском событии
                                        child_with_parent = child.copy()
                                        child_with_parent['parent_event'] = {
                                            'topicId': event.get('topicId'),
                                            'parent_title': event.get('title', ''),
                                            'parent_rules': event.get('rules', ''),
                                            'parent_cutoffTime': event.get('cutoffTime', 0),
                                            'parent_labelName': event.get('labelName', []),
                                            'parent_totalPrice': event.get('totalPrice', 0),
                                            'parent_volume': event.get('volume', 0),
                                            'parent_volume24h': event.get('volume24h', 0)
                                        }
                                        #print(child_with_parent)
                                        all_child_markets.append(child_with_parent)
                                else:
                                    child_with_parent = event.copy()
                                    child_with_parent['parent_event'] = {
                                        'topicId': event.get('topicId'),
                                        'parent_title': event.get('title', ''),
                                        'parent_rules': event.get('rules', ''),
                                        'parent_cutoffTime': event.get('cutoffTime', 0),
                                        'parent_labelName': event.get('labelName', []),
                                        'parent_totalPrice': event.get('totalPrice', 0),
                                        'parent_volume': event.get('volume', 0),
                                        'parent_volume24h': event.get('volume24h', 0)
                                    }
                                    #print(child_with_parent)
                                    all_child_markets.append(child_with_parent)
                            logger.info(f"Page {page}: Found {len(events)} events, total child markets: {len(all_child_markets)}")
                            
                            # Если получили меньше лимита событий, значит это последняя страница
                            if len(events) < limit:
                                break
                            
                            page += 1
                            await asyncio.sleep(0.5)  # Небольшая задержка между запросами
                            
                        else:
                            logger.error(f"API error: {response.status}")
                            break
                except Exception as e:
                    logger.error(f"Error fetching markets from page {page}: {e}")
                    break
        
        logger.info(f"Total fetched {len(all_child_markets)} child markets from {page-1} pages")
        return all_child_markets
    
    def extract_market_data(self, child_market: Dict) -> Dict:
        """Извлекает нужные данные из childList элемента"""
        try:
            # Основные данные
            market_id = child_market.get('topicId', 'N/A')
            title = child_market.get('title', '')
            
            # Если title короткий, используем его, иначе создаем комбинацию
            parent_title = child_market.get('parent_event', {}).get('parent_title', '')
            full_title = f"{parent_title}: {title}" if parent_title and title else title or parent_title
            
            # Цены (конвертируем в центы)
            yes_buy_price_str = child_market.get('yesBuyPrice', '0')
            #yes_market_price_str = child_market.get('yesMarketPrice', '0')
            no_buy_price_str = child_market.get('noBuyPrice', '0')
            
            # Парсим цены
            try:
                yes_buy_price = float(yes_buy_price_str) * 100  # В центы
            except:
                yes_buy_price = 0
            
            try:
                yes_market_price = float(yes_buy_price_str) * 100  # В центы
            except:
                yes_market_price = 0
                
            try:
                no_buy_price = float(no_buy_price_str) * 100  # В центы
            except:
                no_buy_price = 0
            
            # Лучшая цена YES (используем market price если есть, иначе buy price)
            best_yes_price = yes_market_price if yes_market_price > 0 else yes_buy_price
            
            # Рассчитываем спред между YES и NO
            # Для бинарных рынков спред = (цена NO - цена YES) / цена NO * 100
            if no_buy_price > 0 and yes_buy_price > 0:
                spread = no_buy_price + yes_buy_price - 100
            else:
                spread = 100  # Максимальный спред по умолчанию
            
            # Объемы
            try:
                volume = float(child_market.get('volume', '0'))
            except:
                volume = 0
                
            try:
                volume24h = float(child_market.get('volume24h', '0'))
            except:
                volume24h = 0
                
            try:
                total_price = float(child_market.get('totalPrice', '0'))
            except:
                total_price = volume  # Используем volume как fallback
            
            # Время окончания (из родительского события)
            cutoff_time = child_market.get('parent_event', {}).get('parent_cutoffTime', 0)
            #print(cutoff_time)
            hours_left = None
            
            if cutoff_time and cutoff_time > 0:
     #           print(cutoff_time)
                try:
                    # Предполагаем, что это Unix timestamp
                    end_time = datetime.fromtimestamp(cutoff_time).replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
           #         .replace(tzinfo=timezone.utc)
                    time_left = end_time - now
        #            print(end_time)
         #           print(now)
         #           print(time_left)
            #        print("==================================================")
                    hours_left = time_left.total_seconds() / 3600
          #          print(hours_left)
          #          print("==================================================")
                except Exception as e:
                    print(e)
                    hours_left = None
            
            # Дополнительная информация
            category = ', '.join(child_market.get('parent_event', {}).get('parent_labelName', [])) or 'Без категории'
            rules = child_market.get('parent_event', {}).get('parent_rules', '')
            
            # Информация о изменениях цены
            inc_rate_str = child_market.get('incRate', '0')
            try:
                inc_rate = float(inc_rate_str) * 100  # В проценты
            except:
                inc_rate = 0
            
            return {
                'id': market_id,
                'title': full_title,
                'short_title': title,
                'parent_title': parent_title,
                'category': category,
                'rules': rules,
                
                # Цены в центах
                'yes_buy_price': yes_buy_price,
                'yes_market_price': yes_market_price,
                'best_yes_price': best_yes_price,
                'no_buy_price': no_buy_price,
                
                # Спред и изменения
                'spread': spread,
                'price_change': inc_rate,
                
                # Объемы
                'volume': volume,
                'volume24h': volume24h,
                'total_price': total_price,
                
                # Время
                'hours_left': hours_left,
                'cutoff_time': cutoff_time,
                
                # Дополнительно
                'question_id': child_market.get('questionId', ''),
                'create_time': child_market.get('createTime', 0),
                'status': child_market.get('status', 0),
                
                # Для отображения
                'yes_label': child_market.get('yesLabel', 'YES'),
                'no_label': child_market.get('noLabel', 'NO'),
                'thumbnail_url': child_market.get('thumbnailUrl', ''),
            }
            
        except Exception as e:
            logger.error(f"Error extracting market data: {e}")
            # Возвращаем минимальные данные
            return {
                'id': child_market.get('topicId', 'N/A'),
                'title': child_market.get('title', 'Без названия'),
                'category': 'Ошибка',
                'best_yes_price': 0,
                'no_buy_price': 0,
                'spread': 100,
                'volume': 0,
                'volume24h': 0,
                'hours_left': None,
                'price_change': 0
            }
    
    def filter_markets(self, markets: List[Dict], filters: Dict) -> List[Dict]:
        """Фильтрует рынки по заданным критериям"""
        filtered_markets = []
        
        # Парсим фильтры
        time_filter = self._parse_filter_input(filters['time'])
        volume_filter = self._parse_filter_input(filters['volume'])
        price_filter = self._parse_filter_input(filters['price'])
        spread_filter = self._parse_filter_input(filters['spread'])
        
        for market in markets:
            try:
                # Проверка времени до окончания
                hours_left = market.get('hours_left')
                if hours_left is None:
                    continue  # Пропускаем рынки без времени окончания
                
                if not self._check_value(hours_left, time_filter):
                    continue
                
                # Проверка объема
                volume = market.get('volume', 0)
                
                if not self._check_value(volume, volume_filter):
                    continue
                
                # Проверка цены YES
                best_yes_price = market.get('best_yes_price', 0)
                
                if not self._check_value(best_yes_price, price_filter):
                    continue
                
                # Проверка спреда
                spread = market.get('spread', 100)
                
                if not self._check_value(spread, spread_filter):
                    continue
                
                filtered_markets.append(market)
                
            except Exception as e:
                logger.error(f"Error filtering market {market.get('id')}: {e}")
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
            status_msg = await message.answer("1️⃣ Получаю список всех активных рынков с Opinion Trade...")
            all_child_markets = await self.fetch_all_markets()
            
            if not all_child_markets:
                await status_msg.edit_text("❌ Не удалось получить список рынков. Попробуйте позже.")
                return
            
            total_markets = len(all_child_markets)
            await status_msg.edit_text(f"✅ Найдено {total_markets} активных рынков")
            
            # Шаг 2: Извлекаем данные и фильтруем по времени
            status_msg = await message.answer("2️⃣ Обрабатываю данные и фильтрую по времени окончания...")
            
            # Извлекаем данные
            processed_markets = []
            for child_market in all_child_markets:
                market = self.extract_market_data(child_market)
                if market.get('hours_left') is not None:  # Только рынки с известным временем окончания
                    processed_markets.append(market)
            
            # Фильтруем по времени
            time_filter = self._parse_filter_input(filters['time'])
            time_filtered = []
            
            for market in processed_markets:
                hours_left = market.get('hours_left')
                if hours_left is not None and self._check_value(hours_left, time_filter):
                    time_filtered.append(market)
            
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
            
            # Шаг 3: Фильтруем по объему
            status_msg = await message.answer("3️⃣ Фильтрую по объему торгов...")
            volume_filter = self._parse_filter_input(filters['volume'])
            volume_filtered = []
            
            for market in time_filtered:
                volume = market.get('volume', 0)
                
                if self._check_value(volume, volume_filter):
                    volume_filtered.append(market)
            
            if not volume_filtered:
                await status_msg.edit_text("❌ Нет рынков, подходящих под фильтр объема")
                await message.answer(
                    "🔍 Хотите найти другие рынки?\n"
                    "Используйте /filters для изменения критериев поиска\n"
                    "Используйте /search для повторного поиска с текущими фильтрами"
                )
                return
            
            volume_filtered_count = len(volume_filtered)
            await status_msg.edit_text(f"✅ Осталось {volume_filtered_count} рынков после фильтрации по объему")
            
            # Шаг 4: Фильтруем по цене
            status_msg = await message.answer("4️⃣ Фильтрую по цене...")
            price_filter = self._parse_filter_input(filters['price'])
            price_filtered = []
            
            for market in volume_filtered:
                best_yes_price = market.get('best_yes_price', 0)
                no_buy_price = market.get('no_buy_price', 0)
                if self._check_value(best_yes_price, price_filter):
                    price_filtered.append(market)
                elif self._check_value(no_buy_price, price_filter):
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
            spread_filter = self._parse_filter_input(filters['spread'])
            final_markets = []
            
            for market in price_filtered:
                spread = market.get('spread', 100)
                print(spread)
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
            final_markets.sort(key=lambda x: x.get('hours_left', float('inf')))
            
            # Отправляем сводку
            filters_text = self._format_filters_text(filters)
            
            await message.answer(
                f"📊 Результаты поиска на Opinion Trade:\n"
                f"🔍 Всего проверено: {total_markets} рынков\n"
                f"⏰ После фильтра времени: {time_filtered_count}\n"
                f"💰 После фильтра объема: {volume_filtered_count}\n"
                f"💵 После фильтра цены: {price_filtered_count}\n"
                f"✅ Итоговых результатов: {final_count}\n\n"
                f"{filters_text}\n"
                f"Вот лучшие результаты (макс. 10):"
            )
            
            # Выводим результаты (максимум 10)
            for i, market in enumerate(final_markets[:10]):
                await self.send_market_info_simple(message, market, i+1)
                await asyncio.sleep(0.3)
            
            if final_count > 10:
                await message.answer(f"\n📈 ... и еще {final_count - 10} рынков не показаны.")
            
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
            category = market.get('category', '')
            market_id = market.get('id', 'N/A')
            
            # Время до окончания
            hours_left = market.get('hours_left')
            time_left_str = 'N/A'
            if hours_left is not None:
                if hours_left > 0:
                    hours = int(hours_left)
                    days = hours // 24
                    remaining_hours = hours % 24
                    
                    if days > 0:
                        time_left_str = f"{days}д {remaining_hours}ч"
                    else:
                        time_left_str = f"{hours}ч"
                else:
                    time_left_str = "Завершено"
            
            # Цены
            best_yes_price = market.get('best_yes_price', 0)
            no_buy_price = market.get('no_buy_price', 0)
            
            # Спред
            spread = market.get('spread', 100)
            
            # Изменение цены
            price_change = market.get('price_change', 0)
            price_change_str = f"{price_change:+.1f}%" if price_change != 0 else "0%"
            
            # Объем
            volume = market.get('volume', 0)
            volume24h = market.get('volume24h', 0)
            
            # Формируем сообщение
            response = f"📊 Рынок #{index}\n"
            response += "─" * 40 + "\n"
            
            if category:
                response += f"🏷️ {category}\n\n"
            
            response += f"📌 {title}\n\n"
            
            response += f"🆔 ID: {market_id}\n"
            response += f"⏰ До окончания: {time_left_str}\n\n"
            
            # Цены и спред
            response += "💰 Цены:\n"
            response += f"  ✅ {market.get('yes_label', 'YES')}: {best_yes_price:.1f}¢\n"
            response += f"  ❌ {market.get('no_label', 'NO')}: {no_buy_price:.1f}¢\n"
            response += f"  📈 Спред: {spread:.2f}\n"
            response += f"  📊 Изменение: {price_change_str}\n\n"
            
            # Объемы
            response += "📊 Объемы торгов:\n"
            if volume > 0:
                if volume >= 1000000:
                    response += f"  💰 Общий объем: ${volume/1000000:.1f}M\n"
                elif volume >= 1000:
                    response += f"  💰 Общий объем: ${volume/1000:.1f}K\n"
                else:
                    response += f"  💰 Общий объем: ${volume:.0f}\n"
            
            if volume24h > 0:
                if volume24h >= 1000000:
                    response += f"  📈 24ч объем: ${volume24h/1000000:.1f}M\n"
                elif volume24h >= 1000:
                    response += f"  📈 24ч объем: ${volume24h/1000:.1f}K\n"
                else:
                    response += f"  📈 24ч объем: ${volume24h:.0f}\n"
            
            # Время создания
            create_time = market.get('create_time', 0)
            if create_time > 0:
                try:
                    create_date = datetime.fromtimestamp(create_time)
                    response += f"  🕐 Создан: {create_date.strftime('%d.%m.%Y')}\n"
                except:
                    pass
            
            response += "\n" + "─" * 40
            
            await message.answer(response)
            
        except Exception as e:
            logger.error(f"Error sending market info #{index}: {e}", exc_info=True)
            # Минимальная информация
            try:
                basic_info = (
                    f"📊 Рынок #{index}\n"
                    f"📌 {market.get('title', 'Без названия')}\n"
                    f"🆔 ID: {market.get('id', 'N/A')}\n"
                    f"💰 Цена YES: {market.get('best_yes_price', 0):.1f}¢\n"
                    f"📈 Спред: {market.get('spread', 100):.2f}\n"
                )
                mid = market.get('topicId', '0')
                if mid == 2382:
                    print('==========================================')
                    print('topicId')
                    print(mid)
                    print('==========================================')
                mid = market.get('id', '0')
                if mid == 2382:
                    print('==========================================')
                    print('Id')
                    print(mid)
                    print('==========================================')
                await message.answer(basic_info)
            except Exception as e2:
                logger.error(f"Error sending minimal info: {e2}")
                await message.answer(f"⚠️ Ошибка при отображении рынка #{index}")
    
    async def run(self):
        """Запускает бота"""
        logger.info("Starting Opinion Trade Bot...")
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
        print("  2. Или запустите: python opinion_bot.py ваш_токен")
        sys.exit(1)
    
    # Создаем и запускаем бота
    bot = OpinionBot(bot_token)
    
    try:
        # Запуск бота
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
