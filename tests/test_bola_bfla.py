# Punto 5 - BOLA, BFLA y propiedades. Todo pasa por el gateway.
from conftest import ORDER_A, ORDER_B, ORDER_B2, auth

CAMPOS_SENSIBLES = {"password_hash", "role", "is_admin", "internal_notes", "payment_card", "id"}
CAMPOS_PERFIL = {"username", "full_name", "email", "address"}


def test_a_lee_su_pedido(api, token_a):
    r = api.get(f"/api/orders/{ORDER_A}", headers=auth(token_a))
    assert r.status_code == 200
    assert r.json()["id"] == ORDER_A
    assert "owner_id" not in r.json()


def test_a_no_lee_pedido_de_b(api, token_a):
    r = api.get(f"/api/orders/{ORDER_B}", headers=auth(token_a))
    assert r.status_code in (403, 404)
    assert "items" not in r.text and "Avenida" not in r.text


def test_b_no_lee_pedido_de_a(api, token_b):
    r = api.get(f"/api/orders/{ORDER_A}", headers=auth(token_b))
    assert r.status_code in (403, 404)


def test_ajeno_e_inexistente_responden_igual(api, token_a):
    # si respondieran distinto se podria enumerar que ids existen
    ajeno = api.get(f"/api/orders/{ORDER_B2}", headers=auth(token_a))
    no_existe = api.get("/api/orders/999999", headers=auth(token_a))
    assert ajeno.status_code == no_existe.status_code == 404
    assert ajeno.json() == no_existe.json()


def test_listado_solo_trae_lo_propio(api, token_a, token_b):
    ids_a = {o["id"] for o in api.get("/api/orders", headers=auth(token_a)).json()["orders"]}
    ids_b = {o["id"] for o in api.get("/api/orders", headers=auth(token_b)).json()["orders"]}
    assert ORDER_A in ids_a and ORDER_B in ids_b
    assert not ids_a & ids_b


def test_admin_puede_ver_auditoria(api, token_admin):
    r = api.get("/api/admin/audit", headers=auth(token_admin))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_usuario_comun_no_puede_ver_auditoria(api, token_a):
    assert api.get("/api/admin/audit", headers=auth(token_a)).status_code == 403


def test_auditoria_sin_token(api):
    assert api.get("/api/admin/audit").status_code == 401


def test_perfil_no_expone_campos_internos(api, token_a):
    r = api.get("/api/profile", headers=auth(token_a))
    assert r.status_code == 200
    assert set(r.json()) == CAMPOS_PERFIL
    assert not CAMPOS_SENSIBLES & set(r.json())
    assert "4111" not in r.text and "FAKEHASH" not in r.text


def test_patch_perfil_direccion(api, token_a):
    nueva = "Calle Nueva 789, Ciudad Lab"
    r = api.patch("/api/profile", headers=auth(token_a), json={"address": nueva})
    assert r.status_code == 200
    assert api.get("/api/profile", headers=auth(token_a)).json()["address"] == nueva


def test_patch_perfil_con_role_admin_se_rechaza(api, token_a):
    antes = api.get("/api/profile", headers=auth(token_a)).json()
    r = api.patch("/api/profile", headers=auth(token_a),
                  json={"address": "Intento de escalada 1", "role": "admin", "is_admin": True})
    assert r.status_code == 422
    # releo: no cambio nada, ni siquiera la direccion que iba en la misma peticion
    assert api.get("/api/profile", headers=auth(token_a)).json() == antes
    assert api.get("/api/admin/audit", headers=auth(token_a)).status_code == 403


def test_intentos_quedan_en_auditoria(api, token_admin):
    acciones = {e["action"] for e in api.get("/api/admin/audit", headers=auth(token_admin)).json()}
    assert {"bola_denegado", "bfla_denegado", "asignacion_masiva_rechazada"} <= acciones
