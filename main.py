import os
import time
import asyncio
import threading
from datetime import datetime
from config import Config
from logger import logger
from database import Database
from client import TelegramClientManager
from updates import UpdatesManager
from processor import RequestProcessor
from botfather import BotFatherManager
from router import create_app
from utils import AsyncRunner

class BotAPIServer:
    def __init__(self):
        self.main_loop = None
        self.loop_thread = None
        self.async_runner = None
        self.db = None
        self.clients = None
        self.updates = None
        self.processor = None
        self.botfather = None
        self.app = None
        self.server_start_time = int(time.time())
    
    def _run_event_loop(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.main_loop = asyncio.get_event_loop()
        self.main_loop.run_forever()
    
    async def _init_async(self):
        self.db = Database(Config.MONGODB_URI, self.main_loop)
        self.clients = TelegramClientManager(self.main_loop)
        self.updates = UpdatesManager()
        self.processor = RequestProcessor(self.db, self.clients, self.updates)
        self.botfather = BotFatherManager(self.db, self.clients)
        self.async_runner = AsyncRunner(self.main_loop)
        await self.botfather.ensure_token()
    
    def _create_directories(self):
        for directory in [Config.SESSIONS_DIR, Config.TEMPLATES_DIR]:
            if not os.path.exists(directory):
                os.makedirs(directory)
                logger.info(f"Создана директория: {directory}")
   
    def initialize(self):
        try:
            Config.validate()
        except ValueError as e:
            logger.error(str(e))
            raise     
        self._create_directories()
        self.loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.loop_thread.start()
        while self.main_loop is None:
            time.sleep(0.01)
        future = asyncio.run_coroutine_threadsafe(self._init_async(), self.main_loop)
        future.result(timeout=30)
        self.app = create_app(self.async_runner, self.processor)
        logger.info(f"{Config.BRAND}")
        logger.info(f"Запущен: {datetime.fromtimestamp(self.server_start_time).strftime('%Y-%m-%d %H:%M:%S')}")
    
    def run(self):
        self.app.run(
            host='0.0.0.0',
            port=5449,
            debug=False,
            threaded=True
        )

def main():
    server = BotAPIServer()
    server.initialize()
    server.run()

if __name__ == "__main__":
    main()