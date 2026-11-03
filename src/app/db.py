# "Base de datos" en memoria con datos inventados. Se reinicia cada vez que
# se recrea el contenedor, que para el lab es justo lo que quiero.
import threading
from datetime import datetime, timezone

# mismos ids que en keycloak/realm-lab.json, asi el sub del token coincide
USER_A = "a1a1a1a1-0000-4000-8000-00000000000a"
USER_B = "b2b2b2b2-0000-4000-8000-00000000000b"
ADMIN = "adadadad-0000-4000-8000-0000000000ad"

lock = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


PRODUCTS = {
    "P-100": {"name": "Filtro de aceite", "price": 12.50},
    "P-200": {"name": "Pastillas de freno", "price": 45.00},
    "P-300": {"name": "Batería 12V", "price": 120.00},
    "P-400": {"name": "Limpiaparabrisas", "price": 9.90},
}

# password_hash, role, is_admin, internal_notes y payment_card estan aqui a
# proposito: son los campos que NO deberian salir nunca en /api/profile
USERS = {
    USER_A: {
        "id": USER_A, "username": "usuarioa", "full_name": "Usuario A",
        "email": "usuarioa@lab.local", "address": "Calle Ficticia 123, Ciudad Lab",
        "password_hash": "$2b$12$FAKEHASHusuarioaXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "role": "user", "is_admin": False,
        "internal_notes": "Cliente con reclamo abierto #4411",
        "payment_card": "4111-1111-1111-1111",
    },
    USER_B: {
        "id": USER_B, "username": "usuariob", "full_name": "Usuario B",
        "email": "usuariob@lab.local", "address": "Avenida Inventada 456, Pueblo Lab",
        "password_hash": "$2b$12$FAKEHASHusuariobXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "role": "user", "is_admin": False,
        "internal_notes": "VIP - descuento manual 15%",
        "payment_card": "5500-0000-0000-0004",
    },
    ADMIN: {
        "id": ADMIN, "username": "admin", "full_name": "Admin Lab",
        "email": "admin@lab.local", "address": "Oficina Central, Ciudad Lab",
        "password_hash": "$2b$12$FAKEHASHadminXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "role": "admin", "is_admin": True,
        "internal_notes": "Cuenta de administración",
        "payment_card": "N/A",
    },
}


def _order(oid, owner, items, address):
    lines = []
    for pid, qty in items:
        lines.append({"product_id": pid, "name": PRODUCTS[pid]["name"],
                      "quantity": qty, "unit_price": PRODUCTS[pid]["price"]})
    total = round(sum(l["quantity"] * l["unit_price"] for l in lines), 2)
    return {"id": oid, "owner_id": owner, "status": "pagado", "shipping_address": address,
            "items": lines, "total": total, "created_at": now()}


# ids secuenciales (1,2 de A y 3,4 de B): asi es facil probar BOLA cambiando el numero
ORDERS = {
    1: _order(1, USER_A, [("P-100", 2), ("P-400", 1)], USERS[USER_A]["address"]),
    2: _order(2, USER_A, [("P-300", 1)], USERS[USER_A]["address"]),
    3: _order(3, USER_B, [("P-200", 4)], USERS[USER_B]["address"]),
    4: _order(4, USER_B, [("P-100", 1), ("P-200", 1), ("P-300", 1)], USERS[USER_B]["address"]),
}
_next_id = 5

AUDIT = []


def audit(actor, action, detail=""):
    # ojo: aqui nunca se guarda el token ni datos de pago
    with lock:
        AUDIT.append({"ts": now(), "actor": actor, "action": action, "detail": detail})
        del AUDIT[:-500]


def ensure_user(sub, username=None, email=None):
    # si llega un usuario valido que no tengo sembrado, le creo un perfil vacio
    with lock:
        if sub not in USERS:
            USERS[sub] = {"id": sub, "username": username or sub, "full_name": username or "",
                          "email": email or "", "address": "", "password_hash": "",
                          "role": "user", "is_admin": False, "internal_notes": "",
                          "payment_card": ""}
        return USERS[sub]


def create_order(owner, product_id, quantity, address, extra=None):
    global _next_id
    with lock:
        oid = _next_id
        _next_id += 1
        order = _order(oid, owner, [(product_id, quantity)], address)
        if extra:
            # solo pasa en modo inseguro: el cliente puede meter "price" y lo respeto (mal)
            order.update(extra)
            if "price" in extra:
                order["items"][0]["unit_price"] = extra["price"]
                order["total"] = round(quantity * float(extra["price"]), 2)
        ORDERS[oid] = order
        return order


def orders_of(owner):
    with lock:
        return [o for o in ORDERS.values() if o["owner_id"] == owner]
