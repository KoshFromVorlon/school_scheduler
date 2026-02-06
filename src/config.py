import os
from pathlib import Path
from dotenv import load_dotenv

# Находим путь к .env файлу (на два уровня выше, в корне)
base_dir = Path(__file__).resolve().parent.parent
load_dotenv(base_dir / '.env')


class Config:
    # Секретный ключ (для сессий и защиты)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-123')

    # Настройки Базы Данных
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("DATABASE_URL не найден в .env файле!")

    SQLALCHEMY_TRACK_MODIFICATIONS = False