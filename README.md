# TAREA #6 – Auditoría y Endurecimiento de APIs y microservicios

> **Estudiante:** Emilio Andrés Hernández · **Carné:** 1593-20-19375 · **Correo:** ehernandez10@miumg.edu.gt
> **Curso:** Seguridad en Aplicaciones · **Catedrático:** Luis Enrique Rivas Ventura
> **Portada:** [PORTADA.md](PORTADA.md) · **Repositorio:** https://github.com/emiliohernandezdev/t6-lab-seg-aplicaciones

Laboratorio local con dos partes:

- **Bloque A:** auditoría de OWASP crAPI. Inventario y hallazgos en [hallazgos.md](hallazgos.md), evidencias en `evidencias/crAPI/`. Para reproducirlo: clonar crAPI en `C:\labs\crAPI`, `docker compose -f docker-compose.yml --compatibility up -d` y luego `bash scripts/evidencias_crapi.sh` (registra los dos usuarios, da de alta sus vehículos leyendo el pincode de MailHog y captura las pruebas). La captura del navegador está en `evidencias/crAPI/crapi_funcionando.png`.
- **Bloque B:** servicio de pedidos propio (`orders-api`), con Keycloak, un gateway Nginx, mTLS y GraphQL. Es lo que levanta este `docker-compose.yml`.

```
cliente ──HTTPS──> gateway (nginx, 127.0.0.1:8443) ──mTLS──> orders-api (FastAPI + Strawberry)
                                                                  │
                         keycloak (127.0.0.1:8080) <── JWKS ──────┘
```

`orders-api` no publica ningún puerto. Vive en la red `backend` (internal) y solo acepta conexiones con un certificado de cliente firmado por la CA del laboratorio.

## Requisitos

- Docker Desktop (con Compose v2)
- Git Bash, para correr los scripts `.sh` (trae `openssl`)
- No hace falta tener Python instalado: las pruebas corren en un contenedor.

## Cómo levantarlo

```bash
bash scripts/gen_certs.sh          # 1. CA y certificados (solo la primera vez)
docker compose up -d --build       # 2. keycloak + orders-api + gateway
```

Keycloak tarda unos 30 s en arrancar. `orders-api` espera a que esté listo.

## Pruebas

```bash
docker compose --profile test run --rm tests
```

Desde **Git Bash**, si se le pasan rutas al contenedor, hay que anteponer `MSYS_NO_PATHCONV=1`. Desde PowerShell funciona tal cual.

Son 75 pruebas y tardan alrededor de 1 minuto, porque algunas esperan a que venzan la ventana del rate limit o un token.

Para regenerar todas las evidencias (antes con `INSECURE_MODE=true`, después, pytest y comprobaciones desde el host):

```bash
bash scripts/evidencias.sh
```

## Obtener un token a mano

```bash
bash scripts/get_token.sh usuarioa            # imprime el access token
TOKEN=$(bash scripts/get_token.sh usuarioa)
curl --cacert certs/ca.crt -H "Authorization: Bearer $TOKEN" https://localhost:8443/api/orders/1
```

En Windows, si `curl` da error de revocación con la CA local, agregar `--ssl-no-revoke`.

Usuarios de prueba del realm `lab` (son ficticios y solo existen en este laboratorio):

| usuario  | roles       | contraseña          |
|----------|-------------|---------------------|
| usuarioa | user        | `LabUsuarioA-2026!` |
| usuariob | user        | `LabUsuarioB-2026!` |
| admin    | user, admin | `LabAdmin-2026!`    |

Hay además un realm `otro` (usuario `intruso`), que solo sirve para la prueba de emisor incorrecto, y un cliente `lab-cli-corto` que emite tokens de 5 s para la prueba de token vencido.

## Endpoints publicados por el gateway

| Método     | Ruta               | Control                                                     |
|------------|--------------------|-------------------------------------------------------------|
| GET        | `/api/orders`      | scope `orders:read`, solo pedidos propios                   |
| POST       | `/api/orders`      | scope `orders:write`, esquema estricto                      |
| GET        | `/api/orders/{id}` | scope `orders:read`, dueño = `sub` (BOLA), 10 req/10 s por usuario |
| GET, PATCH | `/api/profile`     | lista blanca de campos de entrada y de salida               |
| GET        | `/api/admin/audit` | rol `admin` (BFLA)                                          |
| POST       | `/graphql`         | profundidad 3, `first` ≤ 20, costo ≤ 500, sin introspección en prod |

Cualquier otra ruta, incluidas `/healthz` y `/docs` de la propia API, devuelve 404 en el gateway.

## Antes / después

`INSECURE_MODE=true` apaga los controles del servicio: no valida la firma del JWT, no revisa dueño ni rol, devuelve el perfil completo, acepta cualquier campo y no aplica ni rate limit ni límites de GraphQL. Se usa solo para la evidencia de "antes":

```bash
INSECURE_MODE=true docker compose up -d --force-recreate orders-api
```

## Mapa de evidencias

| Punto | Carpeta | Pruebas |
|---|---|---|
| 1–3 crAPI | `evidencias/crAPI/` | `scripts/evidencias_crapi.sh` (inventario, BOLA, exposición de datos) |
| 5 BOLA/BFLA/propiedades | `evidencias/BOLA_BFLA/` | `tests/test_bola_bfla.py` |
| 6 OIDC/JWT | `evidencias/JWT_OIDC/` | `tests/test_jwt.py` |
| 7 esquema y rate limit | `evidencias/esquema_rate_limit/` | `tests/test_schema.py`, `tests/test_rate_limit.py` |
| 8–9 gateway y mTLS | `evidencias/gateway_mTLS/` | `tests/test_mtls.py` |
| 10 GraphQL | `evidencias/graphql/` | `tests/test_graphql.py` |
| 11 ejecución completa | `evidencias/pytest_resultado.txt` | todas |

Cada carpeta tiene `antes.txt` / `despues.txt` (solicitud y respuesta en formato legible) y su versión `.json` con los mismos datos. Los tokens aparecen recortados (`eyJ…[OCULTO]`).

## Notas

- Las claves privadas (`certs/*.key`) no se entregan. Se regeneran con `scripts/gen_certs.sh`.
- Los datos viven en memoria: al recrear `orders-api` vuelven a su estado inicial.
- Para apagar todo: `docker compose down -v`.
