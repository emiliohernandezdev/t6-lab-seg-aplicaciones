# Punto 6 - validacion de JWT. Los tokens malos tienen que dar 401/403 y no tocar datos.
import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from conftest import KEYCLOAK_URL, auth, count_orders, get_token, token_response

PEDIDO = {"product_id": "P-100", "quantity": 1, "shipping_address": "Calle Ficticia 123, Ciudad Lab"}


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def cambiar_letra(s, i):
    return s[:i] + ("B" if s[i] == "A" else "A") + s[i + 1:]


def test_token_valido(api, token_a):
    assert api.get("/api/orders", headers=auth(token_a)).status_code == 200


def test_sin_token(api):
    r = api.get("/api/orders")
    assert r.status_code == 401
    assert "Bearer" in r.headers.get("www-authenticate", "")


def test_payload_alterado(api, token_a):
    h, p, s = token_a.split(".")
    assert api.get("/api/orders", headers=auth(f"{h}.{cambiar_letra(p, 10)}.{s}")).status_code == 401


def test_payload_con_rol_admin_inyectado(api, token_a):
    # leer el JWT es facil, pero si le cambio los claims la firma ya no cuadra
    h, p, s = token_a.split(".")
    claims = json.loads(unb64(p))
    claims["realm_access"] = {"roles": ["user", "admin"]}
    falso = f"{h}.{b64(json.dumps(claims).encode())}.{s}"
    assert api.get("/api/admin/audit", headers=auth(falso)).status_code == 401


def test_firma_alterada(api, token_a):
    h, p, s = token_a.split(".")
    assert api.get("/api/orders", headers=auth(f"{h}.{p}.{cambiar_letra(s, 5)}")).status_code == 401


def test_alg_none(api, token_a):
    _, p, _ = token_a.split(".")
    h = b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    assert api.get("/api/orders", headers=auth(f"{h}.{p}.")).status_code == 401


def test_hs256_firmado_con_la_clave_publica(api, token_a):
    # ataque clasico de confusion de algoritmo: uso la clave publica RSA como secreto HMAC
    jwks = httpx.get(f"{KEYCLOAK_URL}/realms/lab/protocol/openid-connect/certs", timeout=10).json()
    jwk = next(k for k in jwks["keys"] if k.get("use") == "sig" and k["kty"] == "RSA")
    pem = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk)).public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    _, p, _ = token_a.split(".")
    h = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": jwk["kid"]}).encode())
    firma = b64(hmac.new(pem, f"{h}.{p}".encode(), hashlib.sha256).digest())
    assert api.get("/api/orders", headers=auth(f"{h}.{p}.{firma}")).status_code == 401


def test_token_vencido(api):
    # lab-cli-corto da tokens de 5 segundos
    tok = get_token("usuarioa", client_id="lab-cli-corto")
    assert api.get("/api/orders", headers=auth(tok)).status_code == 200
    time.sleep(7)
    r = api.get("/api/orders", headers=auth(tok))
    assert r.status_code == 401
    assert "vencido" in r.text


def test_token_de_otro_realm(api):
    # token bien firmado... pero por el realm "otro". Trae rol admin y aud orders-api
    tok = get_token("intruso", password="LabIntruso-2026!", realm="otro")
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert claims["iss"].endswith("/realms/otro") and "orders-api" in claims["aud"]
    assert api.get("/api/orders", headers=auth(tok)).status_code == 401
    assert api.get("/api/admin/audit", headers=auth(tok)).status_code == 401


def test_id_token_no_sirve_como_access_token(api):
    id_token = token_response("usuarioa")["id_token"]
    claims = jwt.decode(id_token, options={"verify_signature": False})
    assert claims["typ"] == "ID" and claims["aud"] == "lab-cli"
    assert api.get("/api/orders", headers=auth(id_token)).status_code == 401


def test_sin_scope_orders_read(api):
    tok = get_token("usuarioa", scope="openid")
    assert api.get("/api/orders", headers=auth(tok)).status_code == 403


def test_scope_de_lectura_no_deja_crear(api, token_a):
    tok = get_token("usuarioa", scope="openid orders:read")
    antes = count_orders(api, token_a)
    assert api.post("/api/orders", headers=auth(tok), json=PEDIDO).status_code == 403
    assert count_orders(api, token_a) == antes


def test_token_alterado_no_crea_pedido(api, token_a):
    antes = count_orders(api, token_a)
    h, p, s = token_a.split(".")
    r = api.post("/api/orders", headers=auth(f"{h}.{p}.{cambiar_letra(s, 3)}"), json=PEDIDO)
    assert r.status_code == 401
    assert count_orders(api, token_a) == antes


@pytest.mark.parametrize("valor", ["Basic dXN1YXJpb2E6eA==", "Bearer", "Bearer basura.basura.basura"])
def test_cabecera_authorization_rara(api, valor):
    assert api.get("/api/orders", headers={"Authorization": valor}).status_code == 401
