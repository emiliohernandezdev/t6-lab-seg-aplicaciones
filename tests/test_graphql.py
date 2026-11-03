# Punto 10 - GraphQL: profundidad 3, listas de 20, costo e introspeccion apagada en prod.
import time

from conftest import ORDER_A, ORDER_B, auth


def gql(api, token, query, variables=None):
    return api.post("/graphql", headers=auth(token), json={"query": query, "variables": variables or {}})


def test_consulta_normal(api, token_a):
    q = "{ me { id nombre pedidos(first: 5) { id estado total articulos(first: 5) { nombre cantidad precioUnitario } } } }"
    body = gql(api, token_a, q).json()
    assert "errors" not in body, body
    pedidos = body["data"]["me"]["pedidos"]
    ids = {p["id"] for p in pedidos}
    assert ORDER_A in ids and ORDER_B not in ids
    assert pedidos[0]["articulos"][0]["nombre"]


def test_paginacion(api, token_a):
    q = "query($after: Int) { me { pedidos(first: 1, after: $after) { id } } }"
    p1 = gql(api, token_a, q).json()["data"]["me"]["pedidos"]
    p2 = gql(api, token_a, q, {"after": p1[0]["id"]}).json()["data"]["me"]["pedidos"]
    assert len(p1) == len(p2) == 1
    assert p2[0]["id"] > p1[0]["id"]


def test_a_no_ve_pedido_de_b_por_graphql(api, token_a, token_b):
    q = "query($id: Int!) { pedido(id: $id) { id total } }"
    assert gql(api, token_a, q, {"id": ORDER_B}).json()["data"]["pedido"] is None
    assert gql(api, token_b, q, {"id": ORDER_B}).json()["data"]["pedido"]["id"] == ORDER_B


def test_profundidad_6(api, token_a):
    q = "{ me { pedidos { articulos { pedido { propietario { pedidos { id } } } } } } }"
    t0 = time.monotonic()
    body = gql(api, token_a, q).json()
    assert body.get("data") is None
    assert "depth" in body["errors"][0]["message"].lower()
    assert time.monotonic() - t0 < 2


def test_first_50(api, token_a):
    body = gql(api, token_a, "{ me { pedidos(first: 50) { id } } }").json()
    assert body.get("data") is None
    assert "first" in body["errors"][0]["message"]


def test_first_500_por_variable(api, token_a):
    body = gql(api, token_a, "query($n: Int!) { me { pedidos(first: $n) { id } } }", {"n": 500}).json()
    assert body["errors"] and "first" in body["errors"][0]["message"]


def test_consulta_demasiado_costosa(api, token_a):
    # profundidad 3, pero con alias repetidos y listas de 20 x 20
    campos = "articulos(first: 20) { nombre cantidad precioUnitario productId }"
    q = "{ me { " + " ".join(f"p{i}: pedidos(first: 20) {{ {campos} }}" for i in range(3)) + " } }"
    t0 = time.monotonic()
    body = gql(api, token_a, q).json()
    assert body.get("data") is None
    assert "costosa" in body["errors"][0]["message"]
    assert time.monotonic() - t0 < 2


def test_introspeccion_apagada_en_prod(api, token_a):
    body = gql(api, token_a, "{ __schema { types { name } } }").json()
    assert body.get("data") is None
    assert "introspection" in body["errors"][0]["message"].lower()


def test_graphql_sin_token(api):
    assert api.post("/graphql", json={"query": "{ me { id } }"}).status_code == 401


def test_graphql_por_get_no(api, token_a):
    r = api.get("/graphql", params={"query": "{ me { id } }"}, headers=auth(token_a))
    assert r.status_code in (403, 405)
