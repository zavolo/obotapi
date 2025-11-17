import secrets
import string
import asyncio
from concurrent.futures import Future
from typing import Any, Coroutine

def generate_token(length: int = 45) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def normalize_params(params: dict) -> dict:
    normalized = {}
    for key, value in params.items():
        if isinstance(value, list) and len(value) == 1:
            normalized[key] = value[0]
        else:
            normalized[key] = value
    return normalized

class AsyncRunner:
    def __init__(self, loop):
        self.loop = loop
    
    def run(self, coro: Coroutine) -> Any:
        future = Future()
        async def wrapped():
            try:
                result = await coro
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
        asyncio.run_coroutine_threadsafe(wrapped(), self.loop)
        return future.result(timeout=60)