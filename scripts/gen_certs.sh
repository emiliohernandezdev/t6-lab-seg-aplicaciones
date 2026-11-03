#!/usr/bin/env bash
# Genera la CA del laboratorio y los certificados. Correr en Git Bash:
#   bash scripts/gen_certs.sh
#
# Crea en certs/: la CA (ca), el cert TLS del gateway, el cert de cliente que
# usa el gateway para hablar con la API (gateway-client), el cert TLS de
# orders-api, y una segunda CA "de atacante" con su propio cliente para la
# prueba negativa de mTLS. Los .key estan en .gitignore y no se entregan.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # si no, Git Bash convierte "/CN=..." en una ruta de Windows

cd "$(dirname "$0")/.."
OUT=certs
DAYS=365
TMP="$OUT/.tmp"   # el openssl de Windows no entiende el /tmp de Git Bash
mkdir -p "$TMP"
trap 'rm -f "$TMP"/*; rmdir "$TMP" 2>/dev/null || true' EXIT

# openssl es muy ruidoso, solo muestro la salida si falla
q() { "$@" 2>"$TMP/last.err" || { cat "$TMP/last.err" >&2; exit 1; }; }

new_ca() {   # $1=nombre $2=CN
  q openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days "$DAYS" \
    -keyout "$OUT/$1.key" -out "$OUT/$1.crt" -subj "/O=T6 Lab/CN=$2" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
}

new_cert() { # $1=nombre $2=CN $3=CA $4=serverAuth|clientAuth $5=SAN (opcional)
  local name=$1 cn=$2 ca=$3 eku=$4 san=${5:-}
  q openssl req -newkey rsa:2048 -nodes -sha256 \
    -keyout "$OUT/$name.key" -out "$TMP/$name.csr" -subj "/O=T6 Lab/CN=$cn"
  {
    echo "basicConstraints=critical,CA:FALSE"
    echo "keyUsage=critical,digitalSignature,keyEncipherment"
    echo "extendedKeyUsage=$eku"
    if [ -n "$san" ]; then echo "subjectAltName=$san"; fi
  } > "$TMP/$name.ext"
  q openssl x509 -req -in "$TMP/$name.csr" -CA "$OUT/$ca.crt" -CAkey "$OUT/$ca.key" \
    -CAcreateserial -CAserial "$TMP/$ca.srl" -days "$DAYS" -sha256 \
    -extfile "$TMP/$name.ext" -out "$OUT/$name.crt"
}

echo "[1/6] CA local del laboratorio"
new_ca ca "T6 Lab Root CA"
echo "[2/6] Certificado TLS del gateway"
new_cert gateway localhost ca serverAuth "DNS:localhost,DNS:gateway,IP:127.0.0.1"
echo "[3/6] Certificado de cliente del gateway (mTLS)"
new_cert gateway-client gateway ca clientAuth
echo "[4/6] Certificado TLS de orders-api"
new_cert orders-api orders-api ca serverAuth "DNS:orders-api"
echo "[5/6] CA NO confiable"
new_ca untrusted-ca "Untrusted Attacker CA"
echo "[6/6] Cliente firmado por la CA no confiable (mismo CN 'gateway')"
new_cert untrusted-client gateway untrusted-ca clientAuth

chmod 644 "$OUT"/*.crt "$OUT"/*.key   # los contenedores corren como usuario no-root

echo
for c in ca gateway gateway-client orders-api untrusted-ca untrusted-client; do
  printf '%-22s ' "$c.crt"; openssl x509 -in "$OUT/$c.crt" -noout -subject -issuer | tr '\n' ' '; echo
done
echo
echo "Verificación de cadena contra la CA del laboratorio:"
openssl verify -CAfile "$OUT/ca.crt" "$OUT/gateway.crt" "$OUT/gateway-client.crt" "$OUT/orders-api.crt"
openssl verify -CAfile "$OUT/ca.crt" "$OUT/untrusted-client.crt" 2>&1 | tail -1 || true
