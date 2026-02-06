from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Создаем объекты, но пока не привязываем их к приложению
db = SQLAlchemy()
migrate = Migrate()