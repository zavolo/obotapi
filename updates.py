import time
from collections import defaultdict
from typing import List, Dict, Set, Tuple
from config import Config
from logger import logger

class UpdatesManager:
    def __init__(self):
        self.queues: Dict[int, List[Dict]] = defaultdict(list)
        self.counters: Dict[int, int] = defaultdict(lambda: int(time.time()) * 1000)
        self.processed_messages: Dict[int, Set[Tuple]] = defaultdict(set)
        self.processed_callbacks: Dict[int, Set[Tuple]] = defaultdict(set)
        self.handlers_registered: Set[int] = set()
    
    def add_update(self, bot_id: int, update: Dict) -> None:
        self.counters[bot_id] += 1
        update['update_id'] = self.counters[bot_id]
        self.queues[bot_id].append(update)
        if len(self.queues[bot_id]) > Config.MAX_QUEUE_SIZE:
            self.queues[bot_id] = self.queues[bot_id][-Config.MAX_QUEUE_SIZE:]
        logger.debug(f"Обновление добавлено для бота {bot_id}, update_id={update['update_id']}")
    
    def get_updates(self, bot_id: int, offset: int, limit: int) -> List[Dict]:
        if offset > 0:
            old_count = len(self.queues[bot_id])
            self.queues[bot_id] = [u for u in self.queues[bot_id] if u['update_id'] >= offset]
            removed = old_count - len(self.queues[bot_id])
            if removed > 0:
                logger.debug(f"Удалено {removed} обработанных обновлений")
        available = [u for u in self.queues[bot_id] if u['update_id'] >= offset]
        result = sorted(available, key=lambda x: x['update_id'])[:limit]
        return result
    
    def is_message_processed(self, bot_id: int, msg_key: str) -> bool:
        return any(msg_key == k for k, _ in self.processed_messages[bot_id] if isinstance(k, str))
    
    def mark_message_processed(self, bot_id: int, msg_key: str) -> None:
        self.processed_messages[bot_id].add((msg_key, time.time()))
        self._cleanup_old_processed(bot_id)
    
    def is_callback_processed(self, bot_id: int, callback_key: str) -> bool:
        return any(callback_key == k for k, _ in self.processed_callbacks[bot_id] if isinstance(k, str))
    
    def mark_callback_processed(self, bot_id: int, callback_key: str) -> None:
        self.processed_callbacks[bot_id].add((callback_key, time.time()))
        self._cleanup_old_processed(bot_id)
    
    def _cleanup_old_processed(self, bot_id: int) -> None:
        current_time = time.time()
        new_messages = {
            (k, t) for k, t in self.processed_messages[bot_id]
            if isinstance(k, str) and current_time - t < Config.CLEANUP_INTERVAL
        }
        self.processed_messages[bot_id] = new_messages
        new_callbacks = {
            (k, t) for k, t in self.processed_callbacks[bot_id]
            if isinstance(k, str) and current_time - t < Config.CLEANUP_INTERVAL
        }
        self.processed_callbacks[bot_id] = new_callbacks
    
    def is_handler_registered(self, bot_id: int) -> bool:
        return bot_id in self.handlers_registered
    
    def mark_handler_registered(self, bot_id: int) -> None:
        self.handlers_registered.add(bot_id)