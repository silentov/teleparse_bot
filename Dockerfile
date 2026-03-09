FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем uv и зависимости
RUN pip install --no-cache-dir uv && \
    uv sync --no-dev

# Копируем исходный код
COPY src/ ./src/

# Создаём директорию для session-файлов
RUN mkdir -p /app/sessions

# Запускаем бота
CMD ["uv", "run", "python", "src/main.py"]
