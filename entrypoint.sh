#!/bin/bash
set -e

echo "[entrypoint] Starting SSH SOCKS tunnel..."
autossh -M 0 -N -D 127.0.0.1:${SOCKS_PORT:-1080} \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -o "UserKnownHostsFile=${SSH_KEY_PATH}/known_hosts" \
  -i ${SSH_KEY_PATH}/id_ed25519 \
  -p ${SSH_PORT:-22} \
  ${SSH_USER}@${SSH_HOST} &
TUNNEL_PID=$!

echo "[entrypoint] Waiting for tunnel..."
TUNNEL_READY=0
for i in {1..15}; do
    if curl -sf --socks5 127.0.0.1:${SOCKS_PORT:-1080} \
        --max-time 5 https://api.telegram.org > /dev/null; then
        echo "[entrypoint] Tunnel is up."
        TUNNEL_READY=1
        break
    fi
    sleep 2
done

if [ "$TUNNEL_READY" != "1" ]; then
    echo "[entrypoint] Tunnel failed to start."
    exit 1
fi

echo "[entrypoint] Starting telegram-bot-api server..."
mkdir -p ${TGAPI_DIR} ${DATA_PATH}/logs
telegram-bot-api \
  --local \
  --api-id="${TG_API_ID}" \
  --api-hash="${TG_API_HASH}" \
  --http-port=${TGAPI_PORT:-8081} \
  --dir="${TGAPI_DIR}" \
  --proxy="socks5://127.0.0.1:${SOCKS_PORT:-1080}" \
  --log="${DATA_PATH}/logs/tgapi.log" \
  --verbosity=2 &
TGAPI_PID=$!

echo "[entrypoint] Waiting for bot-api server..."
TGAPI_READY=0
for i in {1..30}; do
    if curl -s http://127.0.0.1:${TGAPI_PORT:-8081}/ > /dev/null 2>&1; then
        echo "[entrypoint] bot-api server is up."
        TGAPI_READY=1
        break
    fi
    sleep 1
done

if [ "$TGAPI_READY" != "1" ]; then
    echo "[entrypoint] bot-api server failed to start."
    exit 1
fi

echo "[entrypoint] Starting bot + web..."
python -m app.run &
APP_PID=$!

trap "kill $TUNNEL_PID $TGAPI_PID $APP_PID 2>/dev/null" EXIT
wait -n $TUNNEL_PID $TGAPI_PID $APP_PID
EXIT_CODE=$?
echo "[entrypoint] One process exited (code=$EXIT_CODE), shutting down."
exit $EXIT_CODE
