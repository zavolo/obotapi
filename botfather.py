import time
from typing import Optional
from logger import logger
from utils import generate_token
from config import Config

class BotFatherManager:
    def __init__(self, database, client_manager):
        self.db = database
        self.clients = client_manager
    
    async def ensure_token(self) -> Optional[str]:
        if not Config.BOTFATHER_PHONE:
            logger.warning("BOTFATHER_PHONE не указан")
            return None
        authorized = await self.clients.authorize_botfather(Config.BOTFATHER_PHONE)
        if not authorized:
            logger.error("Не удалось авторизовать BotFather")
            return None
        botfather_user_id = await self._get_botfather_id()
        if not botfather_user_id:
            logger.error("Не удалось получить ID BotFather")
            return None
        existing_token = await self.db.get_token_data(str(botfather_user_id))
        if existing_token:
            full_token = existing_token.get('full_token')
            if not full_token:
                token = existing_token['token']
                full_token = f"{botfather_user_id}:{token}"
                await self.db.update_token(botfather_user_id, {'full_token': full_token})
            logger.info(f"Токен BotFather: {full_token}")
            return full_token
        token = generate_token()
        full_token = f"{botfather_user_id}:{token}"
        await self.db.create_token({
            'session_file': 'botfather.session',
            'user_id': botfather_user_id,
            'token': token,
            'full_token': full_token,
            'owner_id': 0,
            'bot_username': 'BotFather',
            'bot_name': 'BotFather',
            'verified': True,
            'created_at': time.time()
        })
        logger.info(f"Создан токен для BotFather: {full_token}")
        return full_token
    
    async def _get_botfather_id(self) -> Optional[int]:
        try:
            client = await self.clients.get_client('botfather')
            me = await client.get_me()
            return me.id
        except Exception as e:
            logger.warning(f"Не удалось получить ID BotFather: {e}")
            return 600000000000