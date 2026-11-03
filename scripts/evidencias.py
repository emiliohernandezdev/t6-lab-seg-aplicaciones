# Saca las evidencias de antes/despues: cada peticion con su respuesta.
# Se corre dentro del contenedor tests (lo lanza scripts/evidencias.sh):
#
#   python /work/scripts/evidencias.py antes      <- con INSECURE_MODE=true
#   python /work/scripts/evidencias.py despues
#
# Deja evidencias/<carpeta>/<antes|despues>.txt (para leer) y .json (lo mismo,
# estructurado). Los tokens se recortan a "eyJ…[OCULTO]".
import base64
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

GATEWAY = os.getenv("GATEWAY_URL", "https://gateway:8443")
KEYCLOAK = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
ORDERS_API = os.getenv("ORDERS_API_URL", "https://orders-api:8443")
CERTS = os.getenv("CERTS_DIR", "/certs")
OUT = Path(os.getenv("EVIDENCE_DIR", "/work/evidencias"))
PASSWORDS = {"usuarioa": "LabUsuarioA-2026!", "usuariob": "LabUsuarioB-2026!", "admin": "LabAdmin-2026!"}

api = httpx.Client(base_url=GATEWAY, verify=ssl.create_default_context(cafile=f"{CERTS}/ca.crt"), timeout=15)


def get_token(user, password=None, scope="openid orders:read orders:write", realm="lab",
              client="lab-cli", field="access_token"):
    r = httpx.post(f"{KEYCLOAK}/realms/{realm}/protocol/openid-connect/token", timeout=15, data={
        "grant_type": "password", "client_id": client, "username": user,
        "password": password or PASSWORDS[user], "scope": scope})
    r.raise_for_status()
    return r.json()[field]


def oculto(tok):
    return tok[:3] + "…[OCULTO]" if tok else "(vacío)"


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def parse_body(text):
    try:
        return json.loads(text)
    except ValueError:
        return text


class Evidencia:
    def __init__(self, carpeta, etapa, titulo):
        self.dir = OUT / carpeta
        self.dir.mkdir(parents=True, exist_ok=True)
        self.etapa = etapa
        self.fecha = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.titulo = titulo
        self.casos = []
        self.lineas = [f"# {titulo} - {etapa.upper()}", f"# {self.fecha}",
                       "# tokens recortados, cuentas y datos ficticios", ""]

    def pedir(self, titulo, metodo, url, token=None, body=None, esperado="", cliente=None):
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        caso = {"caso": titulo, "metodo": metodo, "url": url,
                "authorization": f"Bearer {oculto(token)}" if token is not None else None,
                "body": body, "esperado": esperado or None}
        try:
            r = (cliente or api).request(metodo, url, headers=headers, json=body)
            caso["status"] = r.status_code
            caso["retry_after"] = r.headers.get("retry-after")
            caso["respuesta"] = parse_body(r.text)
            texto = r.text
        except httpx.HTTPError as e:
            caso["status"] = None
            caso["error"] = f"{type(e).__name__}: {e}"
            texto = caso["error"]
        self.casos.append(caso)

        self.lineas += [f"## {titulo}", f"> {metodo} {url}"]
        if token is not None:
            self.lineas.append(f"> Authorization: {caso['authorization']}")
        if body is not None:
            self.lineas.append(f"> {json.dumps(body, ensure_ascii=False)}")
        if esperado:
            self.lineas.append(f"# esperado: {esperado}")
        self.lineas.append(f"< HTTP {caso['status']}" if caso["status"] else "< sin respuesta")
        if caso.get("retry_after"):
            self.lineas.append(f"< Retry-After: {caso['retry_after']}")
        self.lineas += [texto[:1200] + ("…" if len(texto) > 1200 else ""), ""]

    def nota(self, texto):
        self.casos.append({"nota": texto})
        self.lineas += [texto, ""]

    def guardar(self):
        (self.dir / f"{self.etapa}.txt").write_text("\n".join(self.lineas), encoding="utf-8")
        data = {"titulo": self.titulo, "etapa": self.etapa, "fecha": self.fecha, "casos": self.casos}
        (self.dir / f"{self.etapa}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {self.dir.name}/{self.etapa}.txt + .json")


def bola_bfla(etapa, ta, tb, tadmin):
    e = Evidencia("BOLA_BFLA", etapa, "BOLA, BFLA y propiedades")
    e.pedir("A pide su pedido 1", "GET", "/api/orders/1", ta, esperado="200")
    e.pedir("A pide el pedido 3, que es de B", "GET", "/api/orders/3", ta, esperado="404")
    e.pedir("admin pide la auditoria", "GET", "/api/admin/audit", tadmin, esperado="200")
    e.pedir("usuarioa pide la auditoria", "GET", "/api/admin/audit", ta, esperado="403")
    e.pedir("A pide su perfil", "GET", "/api/profile", ta,
            esperado="200 solo con username, full_name, email y address")
    e.pedir("A intenta ponerse role=admin con PATCH", "PATCH", "/api/profile", ta,
            body={"address": "Calle Escalada 1, Ciudad Lab", "role": "admin", "is_admin": True}, esperado="422")
    e.pedir("A relee su perfil", "GET", "/api/profile", ta, esperado="sin cambios")
    e.pedir("B cambia solo su direccion", "PATCH", "/api/profile", tb,
            body={"address": "Avenida Actualizada 99, Pueblo Lab"}, esperado="200")
    e.guardar()


def jwt_oidc(etapa, ta):
    e = Evidencia("JWT_OIDC", etapa, "OAuth 2.0 / OIDC y JWT")
    h, p, s = ta.split(".")
    claims = json.loads(unb64(p))
    resumen = {k: claims.get(k) for k in ("iss", "aud", "typ", "azp", "scope", "realm_access", "exp")}
    e.nota("claims del access token de usuarioa (decodificado, NO validado):\n" + json.dumps(resumen, ensure_ascii=False))

    e.pedir("token valido", "GET", "/api/orders", ta, esperado="200")
    e.pedir("sin token", "GET", "/api/orders", esperado="401")

    con_admin = {**claims, "realm_access": {"roles": ["user", "admin"]}}
    falso = f"{h}.{b64(json.dumps(con_admin).encode())}.{s}"
    e.pedir("payload cambiado para meter rol admin (misma firma)", "GET", "/api/admin/audit", falso, esperado="401")
    e.pedir("firma alterada", "GET", "/api/orders", f"{h}.{p}.{s[:-4]}AAAA", esperado="401")
    sin_firma = b64(json.dumps({"alg": "none", "typ": "JWT"}).encode()) + "." + b64(json.dumps(con_admin).encode()) + "."
    e.pedir("alg=none con rol admin", "GET", "/api/admin/audit", sin_firma, esperado="401")
    e.pedir("token del realm 'otro' (rol admin, aud orders-api)", "GET", "/api/admin/audit",
            get_token("intruso", password="LabIntruso-2026!", realm="otro"), esperado="401")
    e.pedir("ID token en vez de access token", "GET", "/api/orders", get_token("usuarioa", field="id_token"), esperado="401")
    e.pedir("token sin scope orders:read", "GET", "/api/orders", get_token("usuarioa", scope="openid"), esperado="403")
    e.pedir("token solo con orders:read intenta crear", "POST", "/api/orders",
            get_token("usuarioa", scope="openid orders:read"),
            body={"product_id": "P-100", "quantity": 1, "shipping_address": "Calle Ficticia 123, Ciudad Lab"},
            esperado="403")
    corto = get_token("usuarioa", client="lab-cli-corto")
    e.pedir("token de 5 s recien emitido", "GET", "/api/orders", corto, esperado="200")
    time.sleep(7)
    e.pedir("el mismo token 7 s despues", "GET", "/api/orders", corto, esperado="401 token vencido")
    e.guardar()


def gateway_mtls(etapa, ta):
    e = Evidencia("gateway_mTLS", etapa, "Gateway, segmentacion y mTLS")
    e.pedir("cliente -> gateway por HTTPS", "GET", "/api/orders", ta, esperado="200")
    for ruta in ("/healthz", "/docs", "/api/internal"):
        e.pedir(f"ruta no publicada {ruta}", "GET", ruta, ta, esperado="404")
    e.pedir("token valido pidiendo pedido ajeno por el gateway", "GET", "/api/orders/3", ta, esperado="404")

    def directo(cert):
        ctx = ssl.create_default_context(cafile=f"{CERTS}/ca.crt")
        if cert:
            ctx.load_cert_chain(f"{CERTS}/{cert}.crt", f"{CERTS}/{cert}.key")
        return httpx.Client(verify=ctx, timeout=5)

    e.pedir("directo a orders-api con el cert de cliente del gateway", "GET", f"{ORDERS_API}/api/orders/1", ta,
            cliente=directo("gateway-client"), esperado="200")
    e.pedir("directo a orders-api sin cert de cliente", "GET", f"{ORDERS_API}/api/orders/1", ta,
            cliente=directo(None), esperado="falla el handshake")
    e.pedir("directo a orders-api con cert de otra CA", "GET", f"{ORDERS_API}/api/orders/1", ta,
            cliente=directo("untrusted-client"), esperado="falla el handshake")
    try:
        ultimas = Path(os.getenv("GATEWAY_LOG", "/gateway-logs/access.log")).read_text().splitlines()[-8:]
        e.nota("ultimas lineas del log del gateway:\n" + "\n".join(ultimas))
    except OSError as err:
        e.nota(f"no pude leer el log del gateway: {err}")
    e.guardar()


def graphql(etapa, ta):
    e = Evidencia("graphql", etapa, "GraphQL")

    def q(titulo, query, esperado):
        e.pedir(titulo, "POST", "/graphql", ta, body={"query": query}, esperado=esperado)

    q("consulta normal (profundidad 3)",
      "{ me { nombre pedidos(first: 5) { id total articulos(first: 5) { nombre cantidad } } } }", "datos de A")
    q("A pide el pedido 3 (de B)", "{ pedido(id: 3) { id total direccionEnvio } }", "pedido: null")
    t0 = time.monotonic()
    q("profundidad 6", "{ me { pedidos { articulos { pedido { propietario { pedidos { id } } } } } } }",
      "error de profundidad")
    e.nota(f"tiempo de respuesta: {time.monotonic() - t0:.3f} s")
    q("lista con first: 50", "{ me { pedidos(first: 50) { id } } }", "error por first")
    campos = "articulos(first: 20) { nombre cantidad precioUnitario productId }"
    q("consulta costosa (3 alias x 20 x 20)",
      "{ me { " + " ".join(f"p{i}: pedidos(first: 20) {{ {campos} }}" for i in range(3)) + " } }", "error de costo")
    q("introspeccion en prod", "{ __schema { queryType { name } types { name } } }", "rechazada")
    e.guardar()


def esquema_rate_limit(etapa, ta, tb):
    e = Evidencia("esquema_rate_limit", etapa, "Validacion de esquema y rate limit")
    ok = {"product_id": "P-300", "quantity": 1, "shipping_address": "Calle Ficticia 123, Ciudad Lab"}
    contar = lambda: api.get("/api/orders", headers={"Authorization": f"Bearer {ta}"}).json()["count"]

    antes = contar()
    e.nota(f"pedidos de A antes: {antes}")
    e.pedir("pedido valido", "POST", "/api/orders", ta, body=ok, esperado="201")
    malos = [("quantity 0", {**ok, "quantity": 0}),
             ("quantity 11", {**ok, "quantity": 11}),
             ('quantity "5" como texto', {**ok, "quantity": "5"}),
             ("sin product_id", {k: v for k, v in ok.items() if k != "product_id"}),
             ("direccion de 5 caracteres", {**ok, "shipping_address": "Calle"}),
             ("campo extra price=0", {**ok, "price": 0})]
    for nombre, body in malos:
        e.pedir(nombre, "POST", "/api/orders", ta, body=body, esperado="422")
    e.nota(f"pedidos de A despues: {contar()} (deberia ser {antes + 1}, solo el valido)")

    time.sleep(10.5)
    codigos = [api.get("/api/orders/1", headers={"Authorization": f"Bearer {ta}"}).status_code for _ in range(11)]
    e.nota("11 GET /api/orders/1 seguidos de usuarioa: " + " ".join(f"#{i}:{c}" for i, c in enumerate(codigos, 1)))
    e.pedir("peticion 12 de usuarioa", "GET", "/api/orders/1", ta, esperado="429")
    e.pedir("usuariob en el mismo momento", "GET", "/api/orders/3", tb, esperado="200 (tiene su propia cuota)")
    e.guardar()


if __name__ == "__main__":
    etapa = sys.argv[1] if len(sys.argv) > 1 else "despues"
    print(f"evidencias '{etapa}':")
    ta, tb, tadmin = get_token("usuarioa"), get_token("usuariob"), get_token("admin")
    bola_bfla(etapa, ta, tb, tadmin)
    jwt_oidc(etapa, ta)
    gateway_mtls(etapa, ta)
    graphql(etapa, ta)
    esquema_rate_limit(etapa, ta, tb)   # va al final porque gasta la cuota de usuarioa
