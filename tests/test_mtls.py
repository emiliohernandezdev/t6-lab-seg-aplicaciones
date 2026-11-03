# Puntos 8 y 9 - gateway, segmentacion y mTLS entre gateway y orders-api.
import os
import ssl
import uuid
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import CA_CERT, CERTS_DIR, GATEWAY_URL, ORDER_A, ORDER_B, ORDERS_API_URL, auth

GATEWAY_LOG = os.getenv("GATEWAY_LOG", "/gateway-logs/access.log")
COMPOSE_FILE = os.getenv("COMPOSE_FILE_PATH", str(Path(__file__).resolve().parent.parent / "docker-compose.yml"))

# las pruebas directas contra orders-api solo funcionan desde la red interna
en_red_interna = pytest.mark.skipif(
    not (Path(CERTS_DIR, "gateway-client.crt").exists() and os.getenv("ORDERS_API_URL")),
    reason="hay que correrlas desde el contenedor tests")

ERRORES_TLS = (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)


def cliente_tls(cert=None):
    ctx = ssl.create_default_context(cafile=CA_CERT)
    if cert:
        ctx.load_cert_chain(f"{CERTS_DIR}/{cert}.crt", f"{CERTS_DIR}/{cert}.key")
    return httpx.Client(verify=ctx, timeout=5)


def test_https_al_gateway(api, token_a):
    r = api.get("/api/orders", headers=auth(token_a))
    assert r.status_code == 200
    assert r.url.scheme == "https"
    assert "strict-transport-security" in r.headers
    assert "nginx/" not in r.headers.get("server", "")


def test_http_plano_al_gateway(token_a):
    # nginx contesta 400 y no reenvia nada a la API
    r = httpx.get(GATEWAY_URL.replace("https://", "http://") + "/api/orders", headers=auth(token_a), timeout=5)
    assert r.status_code == 400
    assert "orders" not in r.text


def test_cert_del_gateway_no_valida_con_otra_ca():
    otra_ca = ssl.create_default_context(cafile=f"{CERTS_DIR}/untrusted-ca.crt")
    with pytest.raises(httpx.ConnectError):
        httpx.get(GATEWAY_URL + "/api/orders", verify=otra_ca, timeout=5)


@pytest.mark.parametrize("ruta", ["/healthz", "/docs", "/openapi.json", "/api/internal",
                                  "/api/orders/../admin", "/api/orders/abc", "/"])
def test_rutas_no_publicadas(api, token_a, ruta):
    assert api.get(ruta, headers=auth(token_a)).status_code == 404


def test_metodo_no_permitido(api, token_a):
    assert api.delete(f"/api/orders/{ORDER_A}", headers=auth(token_a)).status_code in (403, 405)


def test_bola_se_sigue_validando_en_el_servicio(api, token_a):
    # el gateway deja pasar el token valido, pero el pedido de B lo frena la API
    assert api.get(f"/api/orders/{ORDER_B}", headers=auth(token_a)).status_code in (403, 404)


def test_log_del_gateway_sin_token(api, token_a):
    marca = uuid.uuid4().hex
    api.get(f"/api/orders?marca={marca}", headers=auth(token_a))
    log = Path(GATEWAY_LOG).read_text()
    assert "GET /api/orders HTTP/" in log
    assert token_a not in log and token_a.split(".")[1] not in log
    assert "Bearer" not in log and "eyJ" not in log
    assert marca not in log   # la query string tampoco se guarda


@en_red_interna
def test_api_acepta_cert_del_gateway(token_a):
    with cliente_tls("gateway-client") as c:
        assert c.get(f"{ORDERS_API_URL}/api/orders/{ORDER_A}", headers=auth(token_a)).status_code == 200
        # y aun con mTLS correcto, sin token no hay nada
        assert c.get(f"{ORDERS_API_URL}/api/orders").status_code == 401


@en_red_interna
def test_api_rechaza_sin_cert_de_cliente(token_a):
    with pytest.raises(ERRORES_TLS):
        with cliente_tls() as c:
            c.get(f"{ORDERS_API_URL}/api/orders", headers=auth(token_a))


@en_red_interna
def test_api_rechaza_cert_de_otra_ca(token_a):
    # mismo CN "gateway", pero firmado por otra CA
    with pytest.raises(ERRORES_TLS):
        with cliente_tls("untrusted-client") as c:
            c.get(f"{ORDERS_API_URL}/api/orders", headers=auth(token_a))


@en_red_interna
def test_api_no_habla_http_plano():
    with pytest.raises(httpx.HTTPError):
        httpx.get(ORDERS_API_URL.replace("https://", "http://") + "/healthz", timeout=5)


def test_orders_api_no_publica_puertos():
    compose = yaml.safe_load(Path(COMPOSE_FILE).read_text())
    servicios = compose["services"]
    assert "ports" not in servicios["orders-api"]
    assert servicios["orders-api"]["networks"] == ["backend"]
    assert compose["networks"]["backend"].get("internal") is True
    for nombre, svc in servicios.items():
        for p in svc.get("ports", []):
            assert str(p).startswith("127.0.0.1:"), f"{nombre} publica {p} fuera de loopback"
