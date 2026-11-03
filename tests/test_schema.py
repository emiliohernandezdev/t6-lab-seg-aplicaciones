# Punto 7 - contrato de POST /api/orders. Lo invalido da 422 y no crea nada.
import pytest

from conftest import auth, count_orders

OK = {"product_id": "P-200", "quantity": 2, "shipping_address": "Calle Ficticia 123, Ciudad Lab"}

MALOS = {
    "quantity_0": {**OK, "quantity": 0},
    "quantity_11": {**OK, "quantity": 11},
    "quantity_texto": {**OK, "quantity": "5"},
    "quantity_decimal": {**OK, "quantity": 2.5},
    "quantity_bool": {**OK, "quantity": True},
    "sin_product_id": {k: v for k, v in OK.items() if k != "product_id"},
    "product_id_en_blanco": {**OK, "product_id": "   "},
    "product_id_inexistente": {**OK, "product_id": "P-999"},
    "direccion_corta": {**OK, "shipping_address": "Calle"},
    "direccion_larga": {**OK, "shipping_address": "x" * 201},
    "extra_price": {**OK, "price": 0},
    "extra_owner_id": {**OK, "owner_id": "b2b2b2b2-0000-4000-8000-00000000000b"},
    "extra_status": {**OK, "status": "entregado"},
}


def test_pedido_valido(api, token_a):
    antes = count_orders(api, token_a)
    r = api.post("/api/orders", headers=auth(token_a), json=OK)
    assert r.status_code == 201, r.text
    # el precio lo pone el servidor, no el cliente
    assert r.json()["items"][0]["unit_price"] == 45.0 and r.json()["total"] == 90.0
    assert count_orders(api, token_a) == antes + 1


@pytest.mark.parametrize("caso", list(MALOS))
def test_pedido_invalido(api, token_a, caso):
    antes = count_orders(api, token_a)
    r = api.post("/api/orders", headers=auth(token_a), json=MALOS[caso])
    assert r.status_code == 422, f"{caso}: {r.status_code} {r.text}"
    assert count_orders(api, token_a) == antes, f"{caso} creo un pedido"


def test_body_que_no_es_json(api, token_a):
    antes = count_orders(api, token_a)
    r = api.post("/api/orders", headers={**auth(token_a), "Content-Type": "application/json"},
                 content=b"product_id=P-100&quantity=1")
    assert r.status_code == 422
    assert count_orders(api, token_a) == antes


def test_body_gigante_lo_corta_el_gateway(api, token_a):
    r = api.post("/api/orders", headers=auth(token_a), json={**OK, "shipping_address": "x" * 20000})
    assert r.status_code == 413
