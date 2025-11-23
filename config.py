import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
    TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')
    TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE', '')
    SESSION_NAME = os.getenv('SESSION_NAME', 'leak_data_session')

    
    BOT_USERNAMES = [
        'TTMlogsBot',
        'dead_handbot',
        'qoihfuoa_bot',
        'hydralog_bot',
        'octoberslog_bot',
        'perimeterlog_bot'
    ]
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'TTMlogsBot')
    SESSION_NAME = os.getenv('SESSION_NAME', 'leak_data_session')
    
    DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    PORT = int(os.getenv('FLASK_PORT', '5000'))
    
    DOWNLOAD_FOLDER = os.getenv('DOWNLOAD_FOLDER', 'downloads')
    BASE_URL = os.getenv('BASE_URL', 'http://localhost:5000')
    
    @staticmethod
    def create_download_dir():
        if not os.path.exists(Config.DOWNLOAD_FOLDER):

            os.makedirs(Config.DOWNLOAD_FOLDER)
