FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/codestorm-official/telegram-bot-studio" \
      org.opencontainers.image.description="Telegram Bot Studio — easily manage commands and buttons for a Telegram bot." \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/start.sh \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Admin panel listens on $PORT (Railway injects this; defaults to 8080 locally).
EXPOSE 8080

CMD ["sh", "start.sh"]
