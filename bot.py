import asyncio
import secrets
import string
import logging
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from bson import ObjectId
import os
import aiohttp
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
load_dotenv()
BOTFATHER_TOKEN = os.getenv('BOTFATHER_TOKEN')
MONGODB_URI = os.getenv('MONGODB_URI')
DOMAIN = os.getenv('DOMAIN')
PORT = int(os.getenv('PORT'))
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
ADMIN_API_URL = os.getenv('ADMIN_API_URL')
BOT_API_BASE = os.getenv('BOT_API_BASE')
mongo_client = AsyncIOMotorClient(MONGODB_URI)
db = mongo_client['tg']
tokens_collection = db['tokens']
eventflow_users = db['eventflow-userreadmodel']
session = AiohttpSession(api=TelegramAPIServer.from_base(BOT_API_BASE))
bot = Bot(token=BOTFATHER_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

class BotCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_username = State()

def generate_token():
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(45))

async def check_username_available(username):
    username_lower = username.lower()
    user = await eventflow_users.find_one({
        '$or': [
            {'UserName': {'$regex': f'^{username_lower}$', '$options': 'i'}},
            {'Usernames': {'$elemMatch': {'$regex': f'^{username_lower}$', '$options': 'i'}}}
        ]
    })
    if user:
        logger.info(f"Никнейм {username} уже занят в eventflow_users")
        return False
    bot_token = await tokens_collection.find_one({'bot_username': {'$regex': f'^{username_lower}$', '$options': 'i'}})
    if bot_token:
        logger.info(f"Никнейм {username} уже занят в tokens_collection")
        return False
    return True

async def create_bot_via_admin(bot_name, username):
    bot_id = secrets.randbelow(9000000000) + 1000000000
    access_hash = secrets.randbelow(9223372036854775807)
    phone = str(bot_id)
    logger.info(f"Создаём бота: name={bot_name}, username={username}, id={bot_id}")
    async with aiohttp.ClientSession() as session:
        params = {
            'userId': bot_id,
            'phoneNumber': phone,
            'code': ''.join(secrets.choice(string.digits) for _ in range(5))
        }
        try:
            logger.info(f"Отправляю код верификации для {bot_id}")
            async with session.post(
                f"{ADMIN_API_URL}/send-verification-code",
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Ошибка отправки кода: {resp.status} - {error_text}")
                    return None
                result = await resp.json()
                phone_code_hash = result.get('phoneCodeHash')
                if not phone_code_hash:
                    logger.error("phoneCodeHash не получен")
                    return None
                logger.info(f"Код верификации отправлен успешно, hash={phone_code_hash}")
        except Exception as e:
            logger.error(f"Исключение при отправке кода: {e}", exc_info=True)
            return None
        payload = {
            "userId": bot_id,
            "accessHash": access_hash,
            "phoneNumber": phone,
            "firstName": bot_name,
            "lastName": None,
            "userName": username,
            "bot": True,
            "phoneCodeHash": phone_code_hash
        }
        try:
            logger.info(f"Создаю пользователя через API с payload: {payload}")
            async with session.post(
                f"{ADMIN_API_URL}/create-user",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    logger.info(f"Бот создан успешно: {bot_id}")
                    return bot_id
                else:
                    error_text = await resp.text()
                    logger.error(f"Ошибка создания бота: {resp.status} - {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Исключение при создании пользователя: {e}", exc_info=True)
            return None

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать бота", callback_data="create_bot")],
        [InlineKeyboardButton(text="📋 Мои боты", callback_data="my_bots")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
    ])

def get_mybots_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить список", callback_data=f"refresh_bots:{user_id}")],
        [InlineKeyboardButton(text="« Главное меню", callback_data="main_menu")]
    ])

def get_bot_actions_keyboard(bot_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Сменить токен", callback_data=f"regenerate_token:{bot_id}")],
        [InlineKeyboardButton(text="✅ Верифицировать", callback_data=f"verify_bot:{bot_id}")],
        [InlineKeyboardButton(text="🗑 Удалить бота", callback_data=f"delete_bot_confirm:{bot_id}")],
        [InlineKeyboardButton(text="« Назад к списку", callback_data="back_to_bots")]
    ])

def get_delete_confirm_keyboard(bot_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить", callback_data=f"delete_bot:{bot_id}")],
        [InlineKeyboardButton(text="« Отмена", callback_data=f"bot_info:{bot_id}")]
    ])

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} выполнил /start")
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать! Здесь можно создать и управлять ботами.\n\n"
        "Выбери действие:",
        reply_markup=get_main_menu_keyboard()
    )

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} выполнил /cancel")
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять.")
        return
    logger.info(f"Отменяю состояние {current_state} для пользователя {message.from_user.id}")
    await state.clear()
    await message.answer(
        "✅ Действие отменено.",
        reply_markup=get_main_menu_keyboard()
    )

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} выполнил /help")
    await state.clear()
    await message.answer(
        "📚 Доступные команды:\n\n"
        "/newbot - создать нового бота\n"
        "/mybots - список ботов\n"
        "/cancel - отменить текущее действие\n"
        "/start - главное меню\n"
        "/help - показать эту справку\n\n"
        "Или используй кнопки ниже:",
        reply_markup=get_main_menu_keyboard()
    )

@router.message(Command("newbot"))
async def cmd_newbot(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} выполнил /newbot")
    await message.answer(
        "Выберите имя для нового бота.\n\n"
        "Используй /cancel для отмены."
    )
    await state.set_state(BotCreation.waiting_for_name)
    logger.info(f"Установлено состояние waiting_for_name для пользователя {message.from_user.id}")

@router.message(Command("mybots"))
async def cmd_mybots(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} выполнил /mybots")
    await state.clear()
    user_bots = await tokens_collection.find({'owner_id': message.from_user.id}).to_list(length=100)
    logger.info(f"Найдено {len(user_bots)} ботов для пользователя {message.from_user.id}")
    if not user_bots:
        await message.answer(
            "У вас пока нет ботов.\n\n"
            "Используйте /newbot чтобы создать первого бота.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    response = "🤖 Ваши боты:\n\n"
    for idx, bot_data in enumerate(user_bots, 1):
        verified = "✅" if bot_data.get('verified', False) else ""
        response += f"{idx}. {bot_data.get('bot_name', 'Без имени')} {verified}\n   @{bot_data.get('bot_username', 'unknown')}\n\n"
    response += "Выберите бота, отправив его номер."
    await message.answer(response, reply_markup=get_mybots_keyboard(message.from_user.id))

@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню")
    await state.clear()
    await callback.message.edit_text(
        "👋 Добро пожаловать! Здесь можно создать и управлять ботами.\n"
        "Выбери действие:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "create_bot")
async def callback_create_bot(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} начал создание бота через кнопку")
    await callback.message.edit_text(
        "Пожалуйста, отправьте имя для бота.\n\n"
        "Используйте /cancel для отмены."
    )
    await state.set_state(BotCreation.waiting_for_name)
    logger.info(f"Установлено состояние waiting_for_name для пользователя {callback.from_user.id}")
    await callback.answer()

@router.callback_query(F.data == "my_bots")
async def callback_my_bots(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} открыл список ботов")
    await state.clear()
    user_bots = await tokens_collection.find({'owner_id': callback.from_user.id}).to_list(length=100)
    logger.info(f"Найдено {len(user_bots)} ботов для пользователя {callback.from_user.id}")
    if not user_bots:
        await callback.message.edit_text(
            "У вас пока нет ботов.\n\n"
            "Используйте /newbot чтобы создать бота.",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()
        return
    response = "🤖 Ваши боты:\n\n"
    for idx, bot_data in enumerate(user_bots, 1):
        verified = "✅" if bot_data.get('verified', False) else ""
        response += f"{idx}. {bot_data.get('bot_name', 'Без имени')} {verified}\n   @{bot_data.get('bot_username', 'unknown')}\n\n"
    response += "Выберите бота, отправив его номер."
    await callback.message.edit_text(response, reply_markup=get_mybots_keyboard(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} открыл помощь")
    await state.clear()
    await callback.message.edit_text(
        "📚 Доступные команды:\n\n"
        "/newbot - создать нового бота\n"
        "/mybots - список ботов\n"
        "/cancel - отменить текущее действие\n"
        "/start - главное меню\n"
        "/help - показать эту справку",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("refresh_bots:"))
async def refresh_bots(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    logger.info(f"Пользователь {callback.from_user.id} обновляет список ботов")
    if callback.from_user.id != user_id:
        logger.warning(f"Пользователь {callback.from_user.id} пытается обновить чужой список")
        await callback.answer("❌ Это не ващ список ботов!", show_alert=True)
        return
    user_bots = await tokens_collection.find({'owner_id': user_id}).to_list(length=100)
    if not user_bots:
        await callback.message.edit_text(
            "У вас пока нет ботов.\n\n"
            "Используйте /newbot чтобы создать первого бота.",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer("✅ Обновлено")
        return
    response = "🤖 Ваши боты:\n\n"
    for idx, bot_data in enumerate(user_bots, 1):
        verified = "✅" if bot_data.get('verified', False) else ""
        response += f"{idx}. {bot_data.get('bot_name', 'Без имени')} {verified}\n   @{bot_data.get('bot_username', 'unknown')}\n\n"
    response += "Выберите бота, отправив его номер."
    await callback.message.edit_text(response, reply_markup=get_mybots_keyboard(user_id))
    await callback.answer("✅ Обновлено")

@router.callback_query(F.data == "back_to_bots")
async def back_to_bots(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} возвращается к списку ботов")
    user_bots = await tokens_collection.find({'owner_id': callback.from_user.id}).to_list(length=100)
    if not user_bots:
        await callback.message.edit_text(
            "У тебя пока нет ботов.\n\n"
            "Используй /newbot чтобы создать бота.",
            reply_markup=get_main_menu_keyboard()
        )
        await callback.answer()
        return
    response = "🤖 Твои боты:\n\n"
    for idx, bot_data in enumerate(user_bots, 1):
        verified = "✅" if bot_data.get('verified', False) else ""
        response += f"{idx}. {bot_data.get('bot_name', 'Без имени')} {verified}\n   @{bot_data.get('bot_username', 'unknown')}\n\n"
    response += "Выберите бота, отправив его номер."
    await callback.message.edit_text(response, reply_markup=get_mybots_keyboard(callback.from_user.id))
    await callback.answer()

@router.callback_query(F.data.startswith("bot_info:"))
async def show_bot_info(callback: CallbackQuery):
    bot_id = callback.data.split(":")[1]
    logger.info(f"Пользователь {callback.from_user.id} просматривает информацию о боте {bot_id}")
    bot_data = await tokens_collection.find_one({'_id': ObjectId(bot_id)})
    if not bot_data or bot_data['owner_id'] != callback.from_user.id:
        logger.warning(f"Пользователь {callback.from_user.id} пытается просмотреть чужого бота {bot_id}")
        await callback.answer("❌ Бот не найден!", show_alert=True)
        return
    full_token = bot_data.get('full_token', f"{bot_data['user_id']}:{bot_data['token']}")
    verified = "✅ Да" if bot_data.get('verified', False) else "❌ Нет"
    response = (
        f"🤖 Информация о боте\n\n"
        f"{bot_data.get('bot_name', 'Без имени')} @{bot_data.get('bot_username', 'unknown')}\n"
        f"ID: `{bot_data['user_id']}`\n"
        f"Верифицирован: {verified}\n\n"
        f"Токен:\n`{full_token}`\n\n"
    )
    await callback.message.edit_text(response, reply_markup=get_bot_actions_keyboard(str(bot_data['_id'])))
    await callback.answer()

@router.callback_query(F.data.startswith("regenerate_token:"))
async def regenerate_token(callback: CallbackQuery):
    bot_id = callback.data.split(":")[1]
    logger.info(f"Пользователь {callback.from_user.id} регенерирует токен для бота {bot_id}")
    bot_data = await tokens_collection.find_one({'_id': ObjectId(bot_id)})
    if not bot_data or bot_data['owner_id'] != callback.from_user.id:
        logger.warning(f"Пользователь {callback.from_user.id} пытается регенерировать токен чужого бота {bot_id}")
        await callback.answer("❌ Бот не найден!", show_alert=True)
        return
    new_token = generate_token()
    new_full_token = f"{bot_data['user_id']}:{new_token}"
    await tokens_collection.update_one(
        {'_id': ObjectId(bot_id)},
        {'$set': {'token': new_token, 'full_token': new_full_token}}
    )
    logger.info(f"Токен регенерирован для бота {bot_id}")
    verified = "✅ Да" if bot_data.get('verified', False) else "❌ Нет"
    await callback.message.edit_text(
        f"✅ Токен успешно обновлён!\n\n"
        f"🤖 Информация о боте\n\n"
        f"{bot_data.get('bot_name', 'Без имени')} @{bot_data.get('bot_username', 'unknown')}\n"
        f"ID: `{bot_data['user_id']}`\n"
        f"Верифицирован: {verified}\n\n"
        f"Новый токен:\n`{new_full_token}`\n\n"
        f"⚠️ Внимание! Старый токен больше не актуален.",
        reply_markup=get_bot_actions_keyboard(bot_id)
    )
    await callback.answer("🔑 Токен обновлён!")

@router.callback_query(F.data.startswith("verify_bot:"))
async def verify_bot(callback: CallbackQuery):
    bot_id = callback.data.split(":")[1]
    logger.info(f"Пользователь {callback.from_user.id} верифицирует бота {bot_id}")
    bot_data = await tokens_collection.find_one({'_id': ObjectId(bot_id)})
    if not bot_data or bot_data['owner_id'] != callback.from_user.id:
        logger.warning(f"Пользователь {callback.from_user.id} пытается верифицировать чужого бота {bot_id}")
        await callback.answer("❌ Бот не найден!", show_alert=True)
        return
    async with aiohttp.ClientSession() as session:
        try:
            logger.info(f"Отправляю запрос на верификацию бота {bot_data['user_id']}")
            async with session.post(
                f"{ADMIN_API_URL}/set-verified",
                params={'userId': bot_data['user_id'], 'verified': True},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    await tokens_collection.update_one(
                        {'_id': ObjectId(bot_id)},
                        {'$set': {'verified': True}}
                    )
                    logger.info(f"Бот {bot_data['user_id']} успешно верифицирован")
                    await callback.answer("✅ Бот верифицирован!", show_alert=True)
                    full_token = bot_data.get('full_token', f"{bot_data['user_id']}:{bot_data['token']}")
                    await callback.message.edit_text(
                        f"🤖 Информация о боте\n\n"
                        f"{bot_data.get('bot_name', 'Без имени')} @{bot_data.get('bot_username', 'unknown')}\n"
                        f"ID: `{bot_data['user_id']}`\n"
                        f"Верифицирован: ✅ Да\n\n"
                        f"Токен: `{full_token}`\n\n",
                        reply_markup=get_bot_actions_keyboard(bot_id)
                    )
                else:
                    error_text = await resp.text()
                    logger.error(f"Ошибка верификации бота: {resp.status} - {error_text}")
                    await callback.answer("❌ Ошибка верификации", show_alert=True)
        except Exception as e:
            logger.error(f"Исключение при верификации: {e}", exc_info=True)
            await callback.answer("❌ Ошибка верификации", show_alert=True)

@router.callback_query(F.data.startswith("delete_bot_confirm:"))
async def delete_bot_confirm(callback: CallbackQuery):
    bot_id = callback.data.split(":")[1]
    logger.info(f"Пользователь {callback.from_user.id} запрашивает подтверждение удаления бота {bot_id}")
    bot_data = await tokens_collection.find_one({'_id': ObjectId(bot_id)})
    if not bot_data or bot_data['owner_id'] != callback.from_user.id:
        logger.warning(f"Пользователь {callback.from_user.id} пытается удалить чужого бота {bot_id}")
        await callback.answer("❌ Бот не найден!", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить бота @{bot_data.get('bot_username', 'unknown')}?\n\n"
        f"Это действие необратимо!",
        reply_markup=get_delete_confirm_keyboard(bot_id)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("delete_bot:"))
async def delete_bot(callback: CallbackQuery):
    bot_id = callback.data.split(":")[1]
    logger.info(f"Пользователь {callback.from_user.id} удаляет бота {bot_id}")
    bot_data = await tokens_collection.find_one({'_id': ObjectId(bot_id)})
    if not bot_data or bot_data['owner_id'] != callback.from_user.id:
        logger.warning(f"Пользователь {callback.from_user.id} пытается удалить чужого бота {bot_id}")
        await callback.answer("❌ Бот не найден!", show_alert=True)
        return
    await tokens_collection.delete_one({'_id': ObjectId(bot_id)})
    logger.info(f"Бот {bot_id} (@{bot_data.get('bot_username')}) успешно удалён")
    await callback.message.edit_text(
        f"✅ Бот @{bot_data.get('bot_username', 'unknown')} успешно удалён.\n\n"
        f"Используйте /mybots чтобы посмотреть оставшихся ботов или /newbot чтобы создать нового.",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer("🗑 Бот удалён!")

@router.message(BotCreation.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} отправил имя бота: {message.text}")
    if not message.text:
        logger.warning(f"Пользователь {message.from_user.id} отправил не текст в состоянии waiting_for_name")
        await message.answer("❌ Отправьте текстовое сообщение с именем бота.")
        return
    bot_name = message.text.strip()
    if len(bot_name) < 1:
        logger.info(f"Пользователь {message.from_user.id} отправил слишком короткое имя")
        await message.answer("❌ Имя слишком короткое.")
        return
    if len(bot_name) > 64:
        logger.info(f"Пользователь {message.from_user.id} отправил слишком длинное имя")
        await message.answer("❌ Имя слишком длинное (максимум 64 символа).")
        return
    await state.update_data(bot_name=bot_name)
    logger.info(f"Имя бота сохранено: {bot_name}")
    await message.answer(
        f"✅ Имя: {bot_name}\n\n"
        f"Пришлите никнейм для вашего бота\n"
        f"Он должен заканчиваться на `bot`. Например: TetrisBot или tetris_bot\n\n"
        f"Используй /cancel для отмены"
    )
    await state.set_state(BotCreation.waiting_for_username)
    logger.info(f"Установлено состояние waiting_for_username для пользователя {message.from_user.id}")

@router.message(BotCreation.waiting_for_username)
async def process_username(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} отправил username бота: {message.text}")
    if not message.text:
        logger.warning(f"Пользователь {message.from_user.id} отправил не текст в состоянии waiting_for_username")
        await message.answer("❌ Отправьте текстовое сообщение с никнеймом бота.")
        return
    username = message.text.strip()
    if not username.lower().endswith('bot'):
        logger.info(f"Никнейм {username} не заканчивается на bot")
        await message.answer("❌ Никнейм должен заканчиваться на 'bot'.")
        return
    if len(username) < 5:
        logger.info(f"Никнейм {username} слишком короткий")
        await message.answer("❌ Никнейм слишком короткий (минимум 5 символов).")
        return
    if len(username) > 32:
        logger.info(f"Никнейм {username} слишком длинный")
        await message.answer("❌ Никнейм слишком длинный (максимум 32 символа).")
        return
    if not username.replace('_', '').isalnum():
        logger.info(f"Никнейм {username} содержит недопустимые символы")
        await message.answer("❌ Никнейм может содержать только латинские буквы, цифры и подчёркивания.")
        return
    is_available = await check_username_available(username)
    if not is_available:
        logger.info(f"Никнейм {username} уже занят")
        await message.answer(f"❌ Никнейм @{username} уже занят.")
        return
    data = await state.get_data()
    bot_name = data['bot_name']
    logger.info(f"Начинаю создание бота: name={bot_name}, username={username}")
    status_msg = await message.answer("⏳ Создаю бота...")
    bot_id = await create_bot_via_admin(bot_name, username)
    if not bot_id:
        logger.error(f"Не удалось создать бота для пользователя {message.from_user.id}")
        await status_msg.edit_text(
            "❌ Произошла ошибка при создании бота. Попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        await state.clear()
        return
    token = generate_token()
    full_token = f"{bot_id}:{token}"
    session_name = f"bot_{message.from_user.id}_{int(time.time())}"
    await tokens_collection.insert_one({
        'session_file': f"{session_name}.session",
        'user_id': bot_id,
        'token': token,
        'full_token': full_token,
        'owner_id': message.from_user.id,
        'bot_username': username,
        'bot_name': bot_name,
        'verified': False,
        'created_at': time.time()
    })
    logger.info(f"Бот успешно создан и сохранён в БД: id={bot_id}, username={username}, owner={message.from_user.id}")
    await status_msg.edit_text(
        f"✅ Готово! Поздравляю с новым ботом!\n\n"
        f"🤖 Бот: {bot_name} @{username}\n"
        f"ID: `{bot_id}`\n\n"
        f"Токен для HTTP API:\n`{full_token}`\n\n"
        f"⚠️ Храни свой токен в безопасности! Он может быть использован для управления твоим ботом.\n\n"
        f"📖 Документация Bot API: https://core.telegram.org/bots/api",
        reply_markup=get_main_menu_keyboard()
    )
    await state.clear()

@router.message(F.text.regexp(r'^\d+$'))
async def select_bot_by_number(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        logger.debug(f"Пропускаю обработку числа {message.text} - пользователь в состоянии {current_state}")
        return
    try:
        bot_number = int(message.text) - 1
        logger.info(f"Пользователь {message.from_user.id} выбирает бота #{bot_number + 1}")
        user_bots = await tokens_collection.find({'owner_id': message.from_user.id}).to_list(length=100)
        if bot_number < 0 or bot_number >= len(user_bots):
            logger.warning(f"Неверный номер бота: {bot_number + 1}, всего ботов: {len(user_bots)}")
            return
        bot_data = user_bots[bot_number]
        full_token = bot_data.get('full_token', f"{bot_data['user_id']}:{bot_data['token']}")
        verified = "✅ Да" if bot_data.get('verified', False) else "❌ Нет"
        response = (
            f"🤖 Информация о боте\n\n"
            f"{bot_data.get('bot_name', 'Без имени')} @{bot_data.get('bot_username', 'unknown')}\n"
            f"ID: `{bot_data['user_id']}`\n"
            f"Верифицирован: {verified}\n\n"
            f"Токен:\n`{full_token}`\n\n"
            f"Что хочешь сделать с этим ботом?"
        )
        await message.answer(response, reply_markup=get_bot_actions_keyboard(str(bot_data['_id'])))
        logger.info(f"Отображена информация о боте {bot_data.get('bot_username')}")
    except Exception as e:
        logger.error(f"Ошибка выбора бота: {e}", exc_info=True)

async def main():
    if not os.path.exists('sessions'):
        os.makedirs('sessions')
        logger.info("Создана директория sessions")
    dp.include_router(router)
    logger.info("BotFather запущен")
    logger.info(f"API: {BOT_API_BASE}")
    logger.info(f"Admin API: {ADMIN_API_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())