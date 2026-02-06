import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем .env файл явно, указывая путь к корню проекта
base_dir = Path(__file__).resolve().parent.parent
load_dotenv(base_dir / '.env')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-key')

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND')