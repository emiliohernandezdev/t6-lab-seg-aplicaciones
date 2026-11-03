# orders-api - servicio de pedidos para la T6.
# Solo se llega a el a traves del gateway (red interna + mTLS).
import logging

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from strawberry.fastapi import GraphQLRouter

from . import config, db
from .auth import User, current_user, require_role, require_scope
from .graphql_schema import build_schema
from .models import AuditEntry, OrderCreate, OrderList, OrderOut, ProfileOut, ProfileUpdate
from .ratelimit import limited_read

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orders-api")

dev = config.APP_PROFILE == "dev"
app = FastAPI(title="orders-api", docs_url="/docs" if dev else None, redoc_url=None,
              openapi_url="/openapi.json" if dev else None)

if config.INSECURE_MODE:
    log.warning("INSECURE_MODE activo - los controles estan apagados")


@app.exception_handler(RequestValidationError)
async def on_validation_error(request, exc):
    # devuelvo donde fallo y por que, pero no el valor que mandaron
    errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok", "insecure_mode": config.INSECURE_MODE, "profile": config.APP_PROFILE}


@app.get("/api/orders", response_model=OrderList)
def list_orders(user: User = Depends(require_scope("orders:read"))):
    orders = sorted(db.orders_of(user.sub), key=lambda o: o["id"])
    return {"count": len(orders), "orders": orders}


@app.post("/api/orders", status_code=201, response_model=OrderOut)
def create_order(payload: dict = Body(...), user: User = Depends(require_scope("orders:write"))):
    if config.INSECURE_MODE:
        # sin contrato: convierte tipos como pueda y deja pasar campos extra (price incluido)
        extra = {k: v for k, v in payload.items() if k not in ("product_id", "quantity", "shipping_address")}
        product = str(payload.get("product_id", "P-100"))
        if product not in db.PRODUCTS:
            product = "P-100"
        return db.create_order(user.sub, product, int(payload.get("quantity", 1)),
                               str(payload.get("shipping_address", "")), extra)

    # valido a mano (y no en la firma) para que la autenticacion vaya primero
    try:
        data = OrderCreate.model_validate(payload)
    except ValidationError as e:
        raise RequestValidationError(e.errors())
    if data.product_id not in db.PRODUCTS:
        raise HTTPException(422, [{"loc": ["body", "product_id"], "msg": "producto inexistente", "type": "value_error"}])

    order = db.create_order(user.sub, data.product_id, data.quantity, data.shipping_address)
    db.audit(user.sub, "pedido_creado", f"pedido {order['id']}")
    return order


@app.get("/api/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user: User = Depends(limited_read)):
    order = db.ORDERS.get(order_id)
    if order is None:
        raise HTTPException(404, "pedido no encontrado")
    if not config.INSECURE_MODE and order["owner_id"] != user.sub:
        # BOLA: el pedido tiene que ser del sub del token.
        # Respondo 404 igual que si no existiera, para no confirmar que el id es valido.
        db.audit(user.sub, "bola_denegado", f"pedido {order_id}")
        raise HTTPException(404, "pedido no encontrado")
    return order


@app.get("/api/profile")
def get_profile(user: User = Depends(current_user)):
    profile = db.USERS[user.sub]
    if config.INSECURE_MODE:
        return dict(profile)   # devuelve todo, hash y tarjeta incluidos
    return ProfileOut.model_validate(profile).model_dump()


@app.patch("/api/profile")
def update_profile(payload: dict = Body(...), user: User = Depends(current_user)):
    profile = db.USERS[user.sub]
    if config.INSECURE_MODE:
        with db.lock:
            profile.update(payload)   # asignacion masiva: role, is_admin, lo que sea
        return dict(profile)

    try:
        data = ProfileUpdate.model_validate(payload)
    except ValidationError as e:
        db.audit(user.sub, "asignacion_masiva_rechazada", ",".join(sorted(payload))[:200])
        raise RequestValidationError(e.errors())
    changes = data.model_dump(exclude_none=True)
    with db.lock:
        profile.update(changes)
    db.audit(user.sub, "perfil_actualizado", ",".join(sorted(changes)))
    return ProfileOut.model_validate(profile).model_dump()


@app.get("/api/admin/audit", response_model=list[AuditEntry])
def admin_audit(user: User = Depends(require_role("admin"))):
    with db.lock:
        return list(reversed(db.AUDIT[-100:]))


def graphql_context(user: User = Depends(current_user)):
    return {"user": user}


app.include_router(
    GraphQLRouter(build_schema(), context_getter=graphql_context,
                  graphql_ide="graphiql" if dev else None,
                  allow_queries_via_get=False),
    prefix="/graphql",
)
