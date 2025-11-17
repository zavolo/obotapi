from typing import Dict, Any
from logger import logger
from methods import BotAPIMethods
from events import EventHandlers

class RequestProcessor:
    def __init__(self, database, client_manager, updates_manager):
        self.db = database
        self.clients = client_manager
        self.updates = updates_manager
    
    async def process(self, token: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            token_data = await self.db.get_token_data(token)
            if not token_data:
                logger.warning(f"Токен не найден: {token[:10]}...")
                return {"ok": False, "error_code": 401, "description": "Unauthorized"}
            session_name = token_data['session_file'].replace('.session', '')
            try:
                client = await self.clients.get_client(session_name)
            except Exception as e:
                logger.error(f"Ошибка инициализации клиента: {e}")
                return {"ok": False, "error_code": 401, "description": "Unauthorized"}
            me = await client.get_me()
            bot_id = me.id
            if not self.updates.is_handler_registered(bot_id):
                handlers = EventHandlers(client, bot_id, self.updates, self.db)
                await handlers.setup()
            api = BotAPIMethods(client, self.updates)
            method_lower = method.lower()
            if method_lower == 'getme':
                return await api.get_me()
            elif method_lower == 'sendmessage':
                return await api.send_message(params)
            elif method_lower == 'deletemessage':
                return await api.delete_message(params)
            elif method_lower == 'editmessagetext':
                return await api.edit_message_text(params)
            elif method_lower == 'getupdates':
                return await api.get_updates(params, bot_id)
            elif method_lower == 'answercallbackquery':
                return await api.answer_callback_query(params, self.db)
            else:
                logger.warning(f"Метод не реализован: {method}")
                return {"ok": False, "error_code": 400, "description": f"Method '{method}' not implemented"}
        except Exception as e:
            logger.error(f"Внутренняя ошибка: {e}", exc_info=True)
            return {"ok": False, "error_code": 500, "description": str(e)}