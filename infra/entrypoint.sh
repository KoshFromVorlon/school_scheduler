#!/bin/sh

# Останавливаем скрипт при любой ошибке
set -e

echo "Waiting for PostgreSQL..."
# Цикл ждет, пока база данных (хост db, порт 5432) не станет доступна
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

# На всякий случай накатываем миграции при старте
echo "Running Migrations..."
flask db upgrade

# Запускаем команду, переданную в аргументах (gunicorn или celery)
echo "Starting Application..."
exec "$@"