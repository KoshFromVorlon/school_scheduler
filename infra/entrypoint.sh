#!/bin/sh

# Останавливаем скрипт при любой ошибке
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

# Накатываем миграции (если база пустая или обновилась)
echo "Running Migrations..."
flask db upgrade

# Запускаем команду, переданную в аргументах (gunicorn или celery)
echo "Starting Application..."
exec "$@"