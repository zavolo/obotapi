import time
import asyncio
import aiohttp
from telethon import events
from telethon.tl.types import UpdateBotCallbackQuery
from config import Config
from logger import logger

class EventHandlers:
    def __init__(self, client, bot_id: int, updates_manager, database):
        self.client = client
        self.bot_id = bot_id
        self.updates = updates_manager
        self.db = database
    
    async def setup(self):
        if self.updates.is_handler_registered(self.bot_id):
            logger.info(f"Обработчики уже зарегистрированы для бота {self.bot_id}")
            return
        
        self.updates.mark_handler_registered(self.bot_id)
        logger.info(f"Регистрация обработчиков для бота {self.bot_id}")
        
        @self.client.on(events.NewMessage(incoming=True))
        async def on_new_message(event):
            await self._handle_message(event)
        
        @self.client.on(events.Raw)
        async def on_raw_callback(event):
            await self._handle_callback(event)
            
        logger.info(f"Обработчики зарегистрированы для бота {self.bot_id}")
    
    async def _handle_message(self, event):
        message = event.message
        if message.sender_id == self.bot_id or message.out:
            return
        msg_key = f"{message.chat_id}_{message.id}"
        if self.updates.is_message_processed(self.bot_id, msg_key):
            return
        self.updates.mark_message_processed(self.bot_id, msg_key)
        if not message.text and not message.message:
            return
        try:
            sender = await self.client.get_entity(message.sender_id)
            chat = await self.client.get_entity(message.chat_id)
        except Exception as e:
            logger.error(f"Ошибка получения entity: {e}")
            return
        update = {
            "message": {
                "message_id": message.id,
                "from": {
                    "id": sender.id,
                    "is_bot": getattr(sender, 'bot', False),
                    "first_name": getattr(sender, 'first_name', ''),
                    "username": getattr(sender, 'username', ''),
                    "language_code": getattr(sender, 'lang_code', 'ru'),
                    "is_premium": getattr(sender, 'premium', False)
                },
                "chat": {
                    "id": message.chat_id,
                    "first_name": getattr(chat, 'first_name', ''),
                    "username": getattr(chat, 'username', ''),
                    "type": "private" if hasattr(chat, 'first_name') else "group"
                },
                "date": int(message.date.timestamp()),
                "text": message.text or message.message or ""
            }
        }
        self.updates.add_update(self.bot_id, update)
        logger.info(f"Сообщение добавлено для бота {self.bot_id}: {(message.text or '')[:50]}")
    
    async def _handle_callback(self, event):
        if not isinstance(event, UpdateBotCallbackQuery):
            return
        try:
            real_query_id = event.query_id
            user_id = event.user_id
            msg_id = event.msg_id
            data = event.data
            if user_id == self.bot_id:
                return
            callback_data_str = data.decode('utf-8') if isinstance(data, bytes) else str(data)
            callback_key = f"cb_{user_id}_{msg_id}_{callback_data_str}"
            if self.updates.is_callback_processed(self.bot_id, callback_key):
                return
            self.updates.mark_callback_processed(self.bot_id, callback_key)
            query_id = str(real_query_id)
            await asyncio.sleep(0.1)
            sender = await self.client.get_entity(user_id)
            peer = event.peer
            chat_id = peer.user_id if hasattr(peer, 'user_id') else user_id
            original_message = await self.client.get_messages(chat_id, ids=msg_id)
            if not original_message:
                logger.warning("Не удалось получить оригинальное сообщение")
                return
            update = {
                "callback_query": {
                    "id": query_id,
                    "from": {
                        "id": sender.id,
                        "is_bot": getattr(sender, 'bot', False),
                        "first_name": getattr(sender, 'first_name', ''),
                        "username": getattr(sender, 'username', ''),
                        "language_code": getattr(sender, 'lang_code', 'ru'),
                        "is_premium": getattr(sender, 'premium', False)
                    },
                    "message": {
                        "message_id": original_message.id,
                        "date": int(original_message.date.timestamp()),
                        "chat": {
                            "id": original_message.chat_id,
                            "type": "private" if hasattr(original_message.chat, 'first_name') else "group"
                        },
                        "text": original_message.text or original_message.message or ""
                    },
                    "chat_instance": f"{chat_id}_{int(time.time())}",
                    "data": callback_data_str
                }
            }
            self.updates.add_update(self.bot_id, update)
            logger.info(f"Callback добавлен для бота {self.bot_id}, query_id: {query_id}")
            asyncio.create_task(self._process_callback_answer(query_id, user_id, msg_id, real_query_id))
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}", exc_info=True)
    
    async def _process_callback_answer(self, query_id: str, peer_id: int, msg_id: int, real_query_id: int):
        for attempt in range(Config.CALLBACK_MAX_ATTEMPTS):
            await asyncio.sleep(Config.CALLBACK_CHECK_INTERVAL)
            try:
                answer_doc = await self.db.get_callback_answer(query_id)
                if answer_doc:
                    logger.info(f"Найден ответ на callback {query_id}")
                    payload = {
                        "queryId": real_query_id,
                        "peerId": peer_id,
                        "msgId": msg_id,
                        "alert": answer_doc.get('alert', False),
                        "message": answer_doc.get('message'),
                        "url": answer_doc.get('url'),
                        "cacheTime": answer_doc.get('cache_time', 0)
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{Config.ADMIN_API_URL}/answer-callback",
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status == 200:
                                logger.info(f"Callback ответ отправлен для {query_id}")
                            else:
                                error_text = await resp.text()
                                logger.error(f"Ошибка отправки callback ответа: {error_text}")
                    await self.db.delete_callback_answer(query_id)
                    return
            except Exception as e:
                logger.error(f"Ошибка обработки callback ответа: {e}")
        logger.debug(f"Ответ на callback {query_id} не найден")