import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGODB_URI = os.getenv('MONGODB_URI')
    DOMAIN = os.getenv('DOMAIN')
    PORT = int(os.getenv('PORT'))
    API_ID = int(os.getenv('API_ID'))
    API_HASH = os.getenv('API_HASH')
    PUBLIC_KEY = os.getenv('PUBLIC_KEY')
    ADMIN_API_URL = os.getenv('ADMIN_API_URL')
    BOTFATHER_PHONE = os.getenv('BOTFATHER_PHONE')
    BRAND = os.getenv('BRAND', 'Bot API Server')
    SESSIONS_DIR = 'sessions'
    TEMPLATES_DIR = 'templates'
    MAX_QUEUE_SIZE = 1000
    MAX_UPDATES_LIMIT = 100
    MAX_TIMEOUT = 50
    REQUEST_TIMEOUT = 30
    CALLBACK_MAX_ATTEMPTS = 20
    CALLBACK_CHECK_INTERVAL = 0.3
    CLEANUP_INTERVAL = 300
    
    @classmethod
    def validate(cls):
        required = ['MONGODB_URI', 'DOMAIN', 'PORT', 'API_ID', 'API_HASH', 'PUBLIC_KEY']
        missing = [key for key in required if not getattr(cls, key, None)]
        if missing:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing)}")