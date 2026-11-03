import os


def env_bool(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "si")


# Con INSECURE_MODE=true se apagan los controles. Lo uso solo para sacar
# la evidencia de "antes" de cada correccion.
INSECURE_MODE = env_bool("INSECURE_MODE")

APP_PROFILE = os.getenv("APP_PROFILE", "prod").lower()   # dev / prod

OIDC_ISSUER = os.getenv("OIDC_ISSUER", "http://localhost:8080/realms/lab")
OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL",
                          "http://keycloak:8080/realms/lab/protocol/openid-connect/certs")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "orders-api")
JWT_ALGORITHMS = ["RS256"]  # solo RS256, nada de none ni HS256

RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW_S = float(os.getenv("RATE_LIMIT_WINDOW_S", "10"))

GQL_MAX_DEPTH = int(os.getenv("GQL_MAX_DEPTH", "3"))
GQL_MAX_LIST = int(os.getenv("GQL_MAX_LIST", "20"))
GQL_MAX_COST = int(os.getenv("GQL_MAX_COST", "500"))
GQL_INTROSPECTION = APP_PROFILE == "dev"
