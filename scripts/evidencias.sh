#!/usr/bin/env bash
# Corre todo para sacar las evidencias: primero la API en modo inseguro (antes),
# luego en modo normal (despues), luego pytest y unas comprobaciones desde el host.
#   bash scripts/evidencias.sh
set -euo pipefail
export MSYS_NO_PATHCONV=1   # si no, Git Bash cambia /work/... por C:/Program Files/Git/work/...
cd "$(dirname "$0")/.."

# --no-deps importa: sin eso compose recrea orders-api con INSECURE_MODE=false
en_tests() { docker compose --profile test run --rm --no-deps -T tests "$@"; }
esperar_api() { sleep 5; }

echo "== antes (INSECURE_MODE=true)"
INSECURE_MODE=true docker compose up -d --build --force-recreate orders-api
esperar_api
en_tests python /work/scripts/evidencias.py antes

echo "== despues"
INSECURE_MODE=false docker compose up -d --force-recreate orders-api
docker compose restart gateway > /dev/null
esperar_api
en_tests python /work/scripts/evidencias.py despues

echo "== pytest"
en_tests pytest -v -p no:cacheprovider /work/tests 2>&1 | grep -v '^ Container' | tee evidencias/pytest_resultado.txt

echo "== comprobaciones desde el host"
{
  echo "# desde el host, $(date -u +%FT%TZ)"
  echo; echo '$ docker compose ps'
  docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
  echo; echo '$ docker compose port orders-api 8443'
  docker compose port orders-api 8443 2>&1 || true
  echo '(":0" o vacio = el puerto no esta publicado en el host)'
  echo; echo '$ curl -sk https://127.0.0.1:8443/healthz'
  curl -sk -o /dev/null -w 'HTTP %{http_code}\n' https://127.0.0.1:8443/healthz || true
  echo; echo '$ curl --cacert certs/ca.crt https://localhost:8443/api/orders   (sin token)'
  curl -s --ssl-no-revoke --cacert certs/ca.crt -w '\nHTTP %{http_code}\n' https://localhost:8443/api/orders || true
  echo; echo '$ docker network inspect t6-orders_backend'
  docker network inspect t6-orders_backend --format 'internal={{.Internal}}'
} 2>&1 | tee evidencias/gateway_mTLS/host_segmentacion.txt

docker compose logs gateway --no-log-prefix 2>/dev/null | grep -E '^[0-9]' | tail -40 > evidencias/gateway_mTLS/gateway_access_log.txt
echo "listo, todo quedo en evidencias/"
