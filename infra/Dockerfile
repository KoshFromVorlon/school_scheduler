# 1. Используем легкую версию Python 3.12 (Linux Debian Slim)
FROM python:3.12-slim

# 2. Указываем рабочую папку внутри контейнера
WORKDIR /app

# 3. Настраиваем переменные окружения
# PYTHONDONTWRITEBYTECODE=1: не создавать .pyc файлы (мусор)
# PYTHONUNBUFFERED=1: логи выводятся сразу (важно для Docker)
# PYTHONPATH=/app: чтобы Python видел нашу папку src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 4. Установка системных библиотек
# libpq-dev: нужен для PostgreSQL
# netcat-openbsd: нужен для проверки доступности порта базы (команда nc)
# gcc: нужен для компиляции некоторых python-пакетов
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# 5. Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Копируем исходный код проекта
COPY src/ ./src/

# 7. Копируем скрипт запуска и даем ему права на исполнение
COPY infra/entrypoint.sh .
RUN chmod +x entrypoint.sh

# 8. Указываем точку входа
ENTRYPOINT ["./entrypoint.sh"]