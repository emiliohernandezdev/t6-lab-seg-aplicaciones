# Cosas compartidas por todas las pruebas: pedir tokens a Keycloak y el
# cliente HTTP contra el gateway. Las contraseñas son de los usuarios de
# prueba del realm (keycloak/realm-lab.json), no son reales.
import os
import ssl
import time
from pathlib import Path

import httpx
import pytest

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://localhost:8443")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
ORDERS_API_URL = os.getenv("ORDERS_API_URL", "https://orders-api:8443")
CERTS_DIR = Path(os.getenv("CERTS_DIR", Path(__file__).resolve().parent.parent / "certs"))
CA_CERT = str(CERTS_DIR / "ca.crt")
CA_CTX = ssl.create_default_context(cafile=CA_CERT)   # solo confio en la CA del lab

USERS = {
    "usuarioa": os.getenv("LAB_PASS_A", "LabUsuarioA-2026!"),
    "usuariob": os.getenv("LAB_PASS_B", "LabUsuarioB-2026!"),
    "admin": os.getenv("LAB_PASS_ADMIN", "LabAdmin-2026!"),
}
FULL_SCOPE = "openid orders:read orders:write"

# pedidos sembrados en src/app/db.py
ORDER_A, ORDER_A2, ORDER_B, ORDER_B2 = 1, 2, 3, 4


def token_response(username, password=None, scope=FULL_SCOPE, realm="lab", client_id="lab-cli"):
    r = httpx.post(f"{KEYCLOAK_URL}/realms/{realm}/protocol/openid-connect/token", timeout=15, data={
        "grant_type": "password", "client_id": client_id, "username": username,
        "password": password or USERS[username], "scope": scope,
    })
    assert r.status_code == 200, f"keycloak no dio token para {username}: {r.status_code} {r.text}"
    return r.json()


def get_token(username, **kw):
    return token_response(username, **kw)["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def count_orders(api, token):
    r = api.get("/api/orders", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["count"]


@pytest.fixture(scope="session", autouse=True)
def esperar_ventana_rate_limit():
    # si alguien uso la API justo antes (otra corrida, el script de evidencias)
    # la cuota de usuarioa puede estar gastada; espero a que pase la ventana
    time.sleep(float(os.getenv("RATE_LIMIT_WINDOW_S", "10")) + 0.5)


@pytest.fixture(scope="session")
def api():
    with httpx.Client(base_url=GATEWAY_URL, verify=CA_CTX, timeout=15) as c:
        yield c


@pytest.fixture(scope="session")
def token_a():
    return get_token("usuarioa")


@pytest.fixture(scope="session")
def token_b():
    return get_token("usuariob")


@pytest.fixture(scope="session")
def token_admin():
    return get_token("admin")
