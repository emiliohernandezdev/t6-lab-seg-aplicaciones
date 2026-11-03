from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ProductId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20,
                                             pattern=r"^[A-Za-z0-9-]+$")]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


# Entrada. extra="forbid" -> campo que no este aqui = 422.
# strict=True -> "5" no se convierte en 5, ni True en 1.
class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    product_id: ProductId
    quantity: Annotated[int, Field(ge=1, le=10)]
    shipping_address: Address


class ProfileUpdate(BaseModel):
    # solo esto se puede editar; role, is_admin, etc. no existen aqui
    model_config = ConfigDict(extra="forbid", strict=True)
    full_name: Optional[Name] = None
    address: Optional[Address] = None


# Salida. Lo que no este declarado aqui no sale en la respuesta.
class OrderItemOut(BaseModel):
    product_id: str
    name: str
    quantity: int
    unit_price: float


class OrderOut(BaseModel):
    id: int
    status: str
    shipping_address: str
    items: list[OrderItemOut]
    total: float
    created_at: str


class OrderList(BaseModel):
    count: int
    orders: list[OrderOut]


class ProfileOut(BaseModel):
    username: str
    full_name: str
    email: str
    address: str


class AuditEntry(BaseModel):
    ts: str
    actor: str
    action: str
    detail: str
