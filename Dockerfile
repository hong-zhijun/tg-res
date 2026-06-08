# ---------- telegram-bot-api binary ----------
FROM aiogram/telegram-bot-api:latest AS tgapi

# ---------- Python runtime ----------
FROM python:3.12-alpine

RUN apk add --no-cache \
        bash \
        openssh-client \
        autossh \
        curl \
        ca-certificates \
        libstdc++ \
        openssl \
        zlib \
        proxychains-ng

COPY --from=tgapi /usr/local/bin/telegram-bot-api /usr/local/bin/telegram-bot-api

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENV SAVE_PATH=/app/saved
ENV DATA_PATH=/app/data
ENV SSH_KEY_PATH=/app/data/ssh
ENV TGAPI_DIR=/var/lib/telegram-bot-api
ENV PYTHONUNBUFFERED=1

RUN mkdir -p ${TGAPI_DIR}

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://127.0.0.1:${TGAPI_PORT:-8081}/ > /dev/null 2>&1 \
        || curl -sf --socks5-hostname 127.0.0.1:${SOCKS_PORT:-1080} \
            --max-time 8 https://api.telegram.org > /dev/null \
        || exit 1

CMD ["./entrypoint.sh"]
