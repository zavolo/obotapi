import time
from telethon import events
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