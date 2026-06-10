#!/bin/bash
set -e

SSH_RUNTIME_DIR=/tmp/tgbot-ssh
SSH_PRIVATE_KEY=${SSH_RUNTIME_DIR}/id_ed25519

mkdir -p "${SSH_RUNTIME_DIR}"
if [ ! -f "${SSH_KEY_PATH}/id_ed25519" ]; then
    echo "[entrypoint] SSH private key not found: ${SSH_KEY_PATH}/id_ed25519"
    exit 1
fi
cp "${SSH_KEY_PATH}/id_ed25519" "${SSH_PRIVATE_KEY}"
chmod 600 "${SSH_PRIVATE_KEY}"
touch "${SSH_KEY_PATH}/known_hosts"

SSH_TARGET="${SSH_HOST}"
SSH_CF_CONFIG="/tmp/ssh_cf_config"

if [ -n "${CF_TUNNEL_HOST}" ]; then
    echo "[entrypoint] Using Cloudflare Tunnel via ${CF_TUNNEL_HOST}"
    SSH_TARGET="${CF_TUNNEL_HOST}"
    cat > "${SSH_CF_CONFIG}" <<SSHEOF
Host ${CF_TUNNEL_HOST}
    ProxyCommand cloudflared access ssh --hostname %h
SSHEOF
else
    echo "[entrypoint] Using direct SSH to ${SSH_HOST}"
    : > "${SSH_CF_CONFIG}"
fi

echo "[entrypoint] Starting SSH SOCKS tunnel..."
autossh -M 0 -N -D 127.0.0.1:${SOCKS_PORT:-1080} \
  -F "${SSH_CF_CONFIG}" \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -o "UserKnownHostsFile=${SSH_KEY_PATH}/known_hosts" \
  -i "${SSH_PRIVATE_KEY}" \
  -p ${SSH_PORT:-22} \
  ${SSH_USER}@${SSH_TARGET} &
TUNNEL_PID=$!

echo "[entrypoint] Waiting for tunnel..."
TUNNEL_READY=0
for i in {1..15}; do
    if curl -sf --socks5-hostname 127.0.0.1:${SOCKS_PORT:-1080} \
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

echo "[entrypoint] Configuring proxychains for SOCKS5 tunnel..."
cat > /tmp/proxychains.conf <<PCEOF
strict_chain
quiet_mode
proxy_dns
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5 127.0.0.1 ${SOCKS_PORT:-1080}
PCEOF

echo "[entrypoint] Starting telegram-bot-api server..."
mkdir -p ${TGAPI_DIR} ${DATA_PATH}/logs
proxychains4 -f /tmp/proxychains.conf \
  telegram-bot-api \
  --local \
  --api-id="${TG_API_ID}" \
  --api-hash="${TG_API_HASH}" \
  --http-port=${TGAPI_PORT:-8081} \
  --dir="${TGAPI_DIR}" \
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
