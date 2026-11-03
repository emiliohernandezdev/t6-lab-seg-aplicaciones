# Punto 7 - rate limit de 10 peticiones cada 10 s por usuario en GET /api/orders/{id}.
# usuarioa y usuariob salen de la misma IP (este contenedor), asi que si B sigue
# entrando cuando A ya tiene 429, el contador va por sub y no por IP.
import time

import httpx

from conftest import CA_CTX, GATEWAY_URL, ORDER_A, ORDER_B, auth


def test_la_peticion_11_da_429_y_b_sigue_entrando(api, token_a, token_b):
    time.sleep(10.5)   # otras pruebas usan este endpoint, arranco con la ventana limpia
    codigos = [api.get(f"/api/orders/{ORDER_A}", headers=auth(token_a)).status_code for _ in range(10)]
    assert codigos == [200] * 10

    r = api.get(f"/api/orders/{ORDER_A}", headers=auth(token_a))
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1

    assert api.get(f"/api/orders/{ORDER_B}", headers=auth(token_b)).status_code == 200


def test_pasada_la_ventana_vuelve_a_entrar(api, token_a):
    time.sleep(10.5)
    assert api.get(f"/api/orders/{ORDER_A}", headers=auth(token_a)).status_code == 200


def test_limit_req_del_gateway():
    # el gateway deja 30 r/s con rafaga de 100 por IP. Con 300 seguidas tiene que
    # saltar el 429 antes de que lleguen a la API (uso /api/orders sin token -> 401)
    with httpx.Client(base_url=GATEWAY_URL, verify=CA_CTX, timeout=10) as c:
        codigos = [c.get("/api/orders").status_code for _ in range(300)]
    assert codigos[0] == 401
    assert 429 in codigos
    assert set(codigos) <= {401, 429}
    time.sleep(5)
