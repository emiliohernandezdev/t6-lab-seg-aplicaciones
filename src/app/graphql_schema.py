# GraphQL: usuario -> pedidos -> articulos.
#
# Los limites (profundidad, first <= 20, costo, introspeccion) se aplican como
# reglas de validacion, asi que una consulta abusiva se rechaza antes de llegar
# a los resolvers. La autorizacion por objeto va en los resolvers.
from typing import Optional

import strawberry
from graphql import (FieldNode, FragmentSpreadNode, GraphQLError, InlineFragmentNode,
                     IntValueNode, ValidationRule)
from graphql.validation import NoSchemaIntrospectionCustomRule
from strawberry.extensions import AddValidationRules, QueryDepthLimiter
from strawberry.types import Info

from . import config, db

# campos que devuelven listas y cuantos elementos asumo si no mandan "first"
LIST_FIELDS = {"pedidos": 10, "articulos": config.GQL_MAX_LIST}


def who(info):
    return info.context["user"]


def check_first(first):
    if not 1 <= first <= config.GQL_MAX_LIST:
        raise GraphQLError(f"'first' debe estar entre 1 y {config.GQL_MAX_LIST}")


@strawberry.type
class Articulo:
    product_id: str
    nombre: str
    cantidad: int
    precio_unitario: float
    order_id: strawberry.Private[int]

    @strawberry.field
    def pedido(self, info: Info) -> Optional["Pedido"]:
        return load_order(info, self.order_id)


@strawberry.type
class Pedido:
    id: int
    estado: str
    direccion_envio: str
    total: float
    owner_id: strawberry.Private[str]

    @strawberry.field
    def articulos(self, first: int = config.GQL_MAX_LIST) -> list[Articulo]:
        if not config.INSECURE_MODE:
            check_first(first)
        order = db.ORDERS.get(self.id) or {"items": []}
        return [Articulo(product_id=i["product_id"], nombre=i["name"], cantidad=i["quantity"],
                         precio_unitario=i["unit_price"], order_id=self.id)
                for i in order["items"][:first]]

    @strawberry.field
    def propietario(self, info: Info) -> Optional["Usuario"]:
        return load_user(info, self.owner_id)


@strawberry.type
class Usuario:
    id: str
    nombre: str
    correo: str

    @strawberry.field
    def pedidos(self, info: Info, first: int = 10, after: Optional[int] = None) -> list[Pedido]:
        if not config.INSECURE_MODE:
            check_first(first)
            # aunque se llegue a otro usuario por una relacion anidada, solo
            # se listan pedidos si es el mismo que hizo la consulta
            if self.id != who(info).sub:
                return []
        orders = sorted(db.orders_of(self.id), key=lambda o: o["id"])
        if after is not None:
            orders = [o for o in orders if o["id"] > after]
        return [to_pedido(o) for o in orders[:first]]


def to_pedido(o):
    return Pedido(id=o["id"], estado=o["status"], direccion_envio=o["shipping_address"],
                  total=o["total"], owner_id=o["owner_id"])


def load_order(info, order_id):
    o = db.ORDERS.get(order_id)
    if o is None:
        return None
    if not config.INSECURE_MODE and o["owner_id"] != who(info).sub:
        db.audit(who(info).sub, "bola_denegado_graphql", f"pedido {order_id}")
        return None
    return to_pedido(o)


def load_user(info, user_id):
    if not config.INSECURE_MODE and user_id != who(info).sub:
        return None
    u = db.USERS.get(user_id)
    if not u:
        return None
    return Usuario(id=u["id"], nombre=u["full_name"], correo=u["email"])


@strawberry.type
class Query:
    @strawberry.field
    def me(self, info: Info) -> Optional[Usuario]:
        return load_user(info, who(info).sub)

    @strawberry.field
    def pedido(self, info: Info, id: int) -> Optional[Pedido]:
        return load_order(info, id)


class CostLimit(ValidationRule):
    # Costo = 1 por campo, multiplicado por el tamaño de las listas que lo
    # contienen. Ej: pedidos(first:20){ articulos(first:20){ nombre } } ~ 420.
    # Tambien rechaza first > 20 cuando viene literal en la consulta.

    def enter_operation_definition(self, node, *_):
        cost = self.cost(node.selection_set, 1, frozenset())
        if cost > config.GQL_MAX_COST:
            self.report_error(GraphQLError(f"Consulta demasiado costosa: {cost} > {config.GQL_MAX_COST}", node))

    def list_size(self, field):
        if field.name.value not in LIST_FIELDS:
            return 1
        for arg in field.arguments or []:
            if arg.name.value != "first":
                continue
            if isinstance(arg.value, IntValueNode):
                n = int(arg.value.value)
                if n > config.GQL_MAX_LIST:
                    self.report_error(GraphQLError(f"'first' excede el máximo de {config.GQL_MAX_LIST}", field))
                return max(n, 1)
            return config.GQL_MAX_LIST  # viene por variable, asumo el peor caso
        return LIST_FIELDS[field.name.value]

    def cost(self, selection_set, mult, seen):
        total = 0
        for sel in selection_set.selections:
            if isinstance(sel, FieldNode):
                total += mult
                if sel.selection_set:
                    total += self.cost(sel.selection_set, mult * self.list_size(sel), seen)
            elif isinstance(sel, InlineFragmentNode):
                total += self.cost(sel.selection_set, mult, seen)
            elif isinstance(sel, FragmentSpreadNode):
                frag = self.context.get_fragment(sel.name.value)
                if frag and sel.name.value not in seen:   # evita ciclos entre fragments
                    total += self.cost(frag.selection_set, mult, seen | {sel.name.value})
        return total


def build_schema():
    if config.INSECURE_MODE:
        return strawberry.Schema(query=Query)
    rules = [CostLimit]
    if not config.GQL_INTROSPECTION:
        rules.append(NoSchemaIntrospectionCustomRule)
    return strawberry.Schema(query=Query, extensions=[
        QueryDepthLimiter(max_depth=config.GQL_MAX_DEPTH),
        AddValidationRules(rules),
    ])
