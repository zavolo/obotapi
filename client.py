import os
from telethon import TelegramClient
from telethon.crypto import rsa
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.updates import GetStateRequest
from typing import Optional, Dict
from config import Config
from logger import logger

class TelegramClientManager:
    def __init__(self, loop):
        self.loop = loop
        self.cache: Dict[str, TelegramClient] = {}
        self._setup_rsa_keys()
    
    def _setup_rsa_keys(self):
        rsa._server_keys = {}
        keys = [Config.PUBLIC_KEY for _ in range(4)]
        for key in keys:
            rsa.add_key(key, old=False)
            rsa.add_key(key, old=True)
    
    def _create_client(self, session_name: str) -> TelegramClient:
        client = TelegramClient(
            session=f"{Config.SESSIONS_DIR}/{session_name}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            connection=ConnectionTcpAbridged,
            loop=self.loop,
            receive_updates=True
        )
        client.session.set_dc(2, Config.DOMAIN, Config.PORT)
        return client
    
    async def get_client(self, session_name: str) -> TelegramClient:
        if session_name in self.cache:
            client = self.cache[session_name]
            if client.is_connected():
                try:
                    me = await client.get_me()
                    if me:
                        logger.debug(f"Используется кэшированный клиент для {session_name}")
                        return client
                except:
                    pass
        client = self._create_client(session_name)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise Exception("Session is not authorized")
            me = await client.get_me()
            if not me:
                raise Exception("Failed to get user info")
            try:
                await client(GetStateRequest())
            except Exception as e:
                logger.warning(f"Не удалось получить state: {e}")
            self.cache[session_name] = client
            await client.catch_up()
            logger.info(f"Клиент инициализирован: {session_name} (ID: {me.id})")
            return client
        except Exception as e:
            if client.is_connected():
                await client.disconnect()
            raise Exception(f"Ошибка инициализации клиента: {str(e)}")
    
    async def authorize_botfather(self, phone: str) -> bool:
        session_path = f'{Config.SESSIONS_DIR}/botfather.session'
        if os.path.exists(session_path):
            logger.info("Сессия BotFather найдена")
            return True
        logger.info("Авторизация BotFather...")
        client = self._create_client('botfather')
        try:
            await client.connect()
            await client.send_code_request(phone)
            logger.info(f"Код отправлен на {phone}")
            code = input("Введите код: ")
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input("Введите 2FA пароль: ")
                await client.sign_in(password=password)
            me = await client.get_me()
            logger.info(f"Авторизован: {me.first_name} (ID: {me.id})")
            await client.disconnect()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            await client.disconnect()
            return False
    
    async def disconnect_all(self):
        for client in self.cache.values():
            if client.is_connected():
                await client.disconnect()
        self.cache.clear()