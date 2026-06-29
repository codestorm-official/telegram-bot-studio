FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN useradd --create-home appuser
USER appuser

# Admin panel listens on $PORT (Railway injects this; defaults to 8080 locally).
EXPOSE 8080

CMD ["sh", "start.sh"]
