from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Dict, Any
from logger import logger

class Database:
    def __init__(self, uri: str, loop):
        self.client = AsyncIOMotorClient(uri, io_loop=loop)
        self.db = self.client['tg']
        self.tokens = self.db['tokens']
        self.offsets = self.db['offsets']
        self.auth_sessions = self.db['auth_sessions']
        self.callback_answers = self.db['callback_answers']
    
    async def get_token_data(self, token: str) -> Optional[Dict[str, Any]]:
        result = await self.tokens.find_one({'token': token})
        if not result:
            result = await self.tokens.find_one({'full_token': token})
        return result
    
    async def create_token(self, data: Dict[str, Any]) -> None:
        await self.tokens.insert_one(data)
        logger.info(f"Создан токен для пользователя {data.get('user_id')}")
    
    async def update_token(self, user_id: int, updates: Dict[str, Any]) -> None:
        await self.tokens.update_one(
            {'user_id': user_id},
            {'$set': updates}
        )
    
    async def get_callback_answer(self, query_id: str) -> Optional[Dict[str, Any]]:
        return await self.callback_answers.find_one({'query_id': str(query_id)})
    
    async def save_callback_answer(self, data: Dict[str, Any]) -> None:
        await self.callback_answers.delete_many({'query_id': data['query_id']})
        await self.callback_answers.insert_one(data)
    
    async def delete_callback_answer(self, query_id: str) -> None:
        await self.callback_answers.delete_one({'query_id': str(query_id)})
    
    async def close(self):
        self.client.close()