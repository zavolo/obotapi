import asyncio
import time
import aiohttp
from typing import Dict, Set
from logger import logger
from config import Config

class CallbackMonitor:
    def __init__(self, database):
        self.db = database
        self.bot_monitors: Dict[int, asyncio.Task] = {}
        self.processed_callbacks: Dict[int, Set[str]] = {}
        self.last_check: Dict[int, float] = {}
        
    async def start_monitoring(self, bot_id: int, updates_manager):
        if bot_id in self.bot_monitors:
            logger.info(f"Мониторинг callback уже запущен для бота {bot_id}")
            return
        task = asyncio.create_task(self._monitor_bot(bot_id, updates_manager))
        self.bot_monitors[bot_id] = task
        logger.info(f"Запущен мониторинг callback для бота {bot_id}")
        
    async def _monitor_bot(self, bot_id: int, updates_manager):
        if bot_id not in self.processed_callbacks:
            self.processed_callbacks[bot_id] = set()
        while True:
            try:
                current_time = time.time()
                callback_answers = await self.db.db['eventflow-botcallbackanswerreadmodel'].find({
                    'PeerId': bot_id
                }).to_list(length=100)
                for answer in callback_answers:
                    query_id = str(answer.get('QueryId'))
                    msg_id = answer.get('MsgId')
                    callback_key = f"{query_id}_{msg_id}"
                    if callback_key in self.processed_callbacks[bot_id]:
                        continue
                    self.processed_callbacks[bot_id].add(callback_key)
                    try:
                        user_id = answer.get('UserId', 0)
                        chat_id = answer.get('ChatId', user_id)
                        bot_callback = answer.get('BotCallbackAnswer', {})
                        callback_data = answer.get('Data', '')
                        update_data = {
                            "callback_query": {
                                "id": query_id,
                                "from": {
                                    "id": user_id,
                                    "is_bot": False,
                                    "first_name": "",
                                    "username": "",
                                    "language_code": "ru"
                                },
                                "message": {
                                    "message_id": msg_id,
                                    "date": int(current_time),
                                    "chat": {
                                        "id": chat_id,
                                        "type": "private"
                                    },
                                    "text": ""
                                },
                                "chat_instance": f"{chat_id}_{int(current_time)}",
                                "data": callback_data
                            }
                        }
                        updates_manager.add_update(bot_id, update_data)
                        logger.info(f"Callback добавлен из БД для бота {bot_id}: query_id={query_id}, data={callback_data}")
                        asyncio.create_task(
                            self._wait_and_answer(query_id, bot_id, msg_id, answer)
                        )
                    except Exception as e:
                        logger.error(f"Ошибка обработки callback из БД: {e}")
                self._cleanup_old_callbacks(bot_id)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка в мониторинге callback для бота {bot_id}: {e}")
                await asyncio.sleep(1)
                
    async def _wait_and_answer(self, query_id: str, bot_id: int, msg_id: int, original_answer):
        for attempt in range(Config.CALLBACK_MAX_ATTEMPTS):
            await asyncio.sleep(Config.CALLBACK_CHECK_INTERVAL)
            try:
                answer_doc = await self.db.get_callback_answer(query_id)
                if answer_doc:
                    logger.info(f"Найден ответ на callback {query_id}")
                    payload = {
                        "queryId": int(query_id),
                        "peerId": bot_id,
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
                                logger.info(f"Ответ отправлен для query_id {query_id}")
                            else:
                                error_text = await resp.text()
                                logger.error(f"Ошибка отправки ответа: {resp.status} - {error_text}")
                    await self.db.delete_callback_answer(query_id)
                    return
            except Exception as e:
                logger.error(f"Ошибка ожидания ответа callback: {e}")
        logger.debug(f"Таймаут ожидания ответа для callback {query_id}")
        
    def _cleanup_old_callbacks(self, bot_id: int):
        if len(self.processed_callbacks[bot_id]) > 10000:
            logger.info(f"Очистка старых callback для бота {bot_id}")
            self.processed_callbacks[bot_id].clear()
            
    async def stop_all(self):
        for task in self.bot_monitors.values():
            task.cancel()
        self.bot_monitors.clear()