#!/usr/bin/env bash
# Pide un access token al realm lab con el usuario de prueba indicado.
#   bash scripts/get_token.sh usuarioa ["openid orders:read"]
set -euo pipefail

user=${1:-usuarioa}
scope=${2:-openid orders:read orders:write}
case "$user" in
  usuarioa) pass='LabUsuarioA-2026!' ;;
  usuariob) pass='LabUsuarioB-2026!' ;;
  admin)    pass='LabAdmin-2026!' ;;
  *) echo "usuario desconocido: $user" >&2; exit 1 ;;
esac

curl -s http://localhost:8080/realms/lab/protocol/openid-connect/token \
  -d grant_type=password -d client_id=lab-cli \
  -d "username=$user" --data-urlencode "password=$pass" --data-urlencode "scope=$scope" \
  | sed -E 's/.*"access_token":"([^"]+)".*/\1/'
