import time
import json
import asyncio
import aiohttp
from typing import Dict, Any
from config import Config
from logger import logger

class BotAPIMethods:
    def __init__(self, client, updates_manager):
        self.client = client
        self.updates = updates_manager
    
    async def get_me(self) -> Dict[str, Any]:
        try:
            me = await self.client.get_me()
            if not me:
                return {"ok": False, "error_code": 401, "description": "Unauthorized"}
            return {
                "ok": True,
                "result": {
                    "id": me.id,
                    "is_bot": me.bot,
                    "first_name": me.first_name or "",
                    "username": me.username or "",
                    "can_join_groups": True,
                    "can_read_all_group_messages": False,
                    "supports_inline_queries": False,
                    "can_connect_to_business": False,
                    "has_main_web_app": False
                }
            }
        except Exception as e:
            logger.error(f"Ошибка getMe: {e}")
            return {"ok": False, "error_code": 500, "description": str(e)}
    
    async def send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if 'chat_id' not in params or 'text' not in params:
            return {"ok": False, "error_code": 400, "description": "Missing required parameters"}
        try:
            chat_id = int(params['chat_id'])
        except (ValueError, TypeError):
            chat_id = params['chat_id']
        text = params['text']
        reply_markup = params.get('reply_markup')
        try:
            me = await self.client.get_me()
            if chat_id == me.id:
                return {"ok": False, "error_code": 400, "description": "Bot can't send messages to itself"}
            entity = await self.client.get_entity(chat_id)
            payload = {
                "fromUserId": me.id,
                "toUserId": chat_id,
                "message": text,
                "silent": params.get('disable_notification', False)
            }
            buttons_for_response = None
            if reply_markup:
                if isinstance(reply_markup, str):
                    reply_markup = json.loads(reply_markup)
                if 'inline_keyboard' in reply_markup:
                    buttons = []
                    buttons_for_response = []
                    for row in reply_markup['inline_keyboard']:
                        button_row = []
                        response_row = []
                        for btn in row:
                            button_data = {"text": btn['text']}
                            response_btn = {"text": btn['text']}
                            if 'url' in btn:
                                button_data['url'] = btn['url']
                                response_btn['url'] = btn['url']
                            elif 'callback_data' in btn:
                                button_data['callbackData'] = btn['callback_data']
                                response_btn['callback_data'] = btn['callback_data']
                            button_row.append(button_data)
                            response_row.append(response_btn)
                        buttons.append(button_row)
                        buttons_for_response.append(response_row)
                    payload['buttons'] = buttons
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{Config.ADMIN_API_URL}/send-message",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=Config.REQUEST_TIMEOUT)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return {"ok": False, "error_code": 400, "description": error_text}
                    result_data = await resp.json()
                    real_message_id = result_data.get('messageId', int(time.time()))
            result = {
                "ok": True,
                "result": {
                    "message_id": real_message_id,
                    "from": {
                        "id": me.id,
                        "is_bot": me.bot,
                        "first_name": me.first_name or "",
                        "username": me.username or ""
                    },
                    "chat": {
                        "id": entity.id,
                        "first_name": getattr(entity, 'first_name', ''),
                        "username": getattr(entity, 'username', ''),
                        "type": "private" if hasattr(entity, 'first_name') else "group"
                    },
                    "date": int(time.time()),
                    "text": text
                }
            }
            if buttons_for_response:
                result["result"]["reply_markup"] = {"inline_keyboard": buttons_for_response}
            return result
        except Exception as e:
            logger.error(f"Ошибка sendMessage: {e}")
            return {"ok": False, "error_code": 400, "description": str(e)}
    
    async def delete_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if 'chat_id' not in params or 'message_id' not in params:
            return {"ok": False, "error_code": 400, "description": "Missing required parameters"}
        try:
            chat_id = int(params['chat_id'])
            message_id = int(params['message_id'])
            await self.client.delete_messages(chat_id, [message_id])
            return {"ok": True, "result": True}
        except Exception as e:
            logger.error(f"Ошибка deleteMessage: {e}")
            return {"ok": False, "error_code": 400, "description": str(e)}
    
    async def edit_message_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if 'chat_id' not in params or 'message_id' not in params or 'text' not in params:
            return {"ok": False, "error_code": 400, "description": "Missing required parameters"}
        try:
            chat_id = int(params['chat_id'])
            message_id = int(params['message_id'])
            new_text = params['text']
            messages = await self.client.get_messages(chat_id, ids=message_id)
            if not messages:
                return {"ok": False, "error_code": 400, "description": "Message not found"}
            if messages.message == new_text:
                return {"ok": False, "error_code": 400, "description": "Message is not modified"}
            edited_message = await self.client.edit_message(chat_id, message_id, new_text)
            me = await self.client.get_me()
            entity = await self.client.get_entity(chat_id)
            return {
                "ok": True,
                "result": {
                    "message_id": edited_message.id,
                    "from": {
                        "id": me.id,
                        "is_bot": me.bot,
                        "first_name": me.first_name or "",
                        "username": me.username or ""
                    },
                    "chat": {
                        "id": entity.id,
                        "first_name": getattr(entity, 'first_name', ''),
                        "username": getattr(entity, 'username', ''),
                        "type": "private" if hasattr(entity, 'first_name') else "group"
                    },
                    "date": int(edited_message.date.timestamp()),
                    "edit_date": int(edited_message.edit_date.timestamp()) if edited_message.edit_date else int(edited_message.date.timestamp()),
                    "text": new_text
                }
            }
        except Exception as e:
            logger.error(f"Ошибка editMessageText: {e}")
            return {"ok": False, "error_code": 400, "description": str(e)}
    
    async def get_updates(self, params: Dict[str, Any], bot_id: int) -> Dict[str, Any]:
        offset = int(params.get('offset', 0))
        limit = min(int(params.get('limit', 100)), Config.MAX_UPDATES_LIMIT)
        timeout = min(int(params.get('timeout', 0)), Config.MAX_TIMEOUT)
        start_time = time.time()
        while time.time() - start_time < timeout:
            updates = self.updates.get_updates(bot_id, offset, limit)
            if updates:
                return {"ok": True, "result": updates}
            if timeout > 0:
                await asyncio.sleep(1)
            else:
                break
        return {"ok": True, "result": []}
    
    async def answer_callback_query(self, params: Dict[str, Any], database) -> Dict[str, Any]:
        if 'callback_query_id' not in params:
            return {"ok": False, "error_code": 400, "description": "Missing callback_query_id"}
        query_id = str(params['callback_query_id'])
        await database.save_callback_answer({
            'query_id': query_id,
            'alert': params.get('show_alert', False),
            'message': params.get('text'),
            'url': params.get('url'),
            'cache_time': params.get('cache_time', 0),
            'created_at': time.time()
        })
        logger.info(f"Ответ сохранен для query_id: {query_id}")
        return {"ok": True, "result": True}