# Validacion de los access tokens que emite Keycloak.
# Todo esto corre como dependencia de FastAPI, o sea antes de que el endpoint
# toque cualquier dato.
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from . import config, db

bearer = HTTPBearer(auto_error=False)
# las claves publicas se bajan del endpoint JWKS del realm y se cachean 5 min
jwks_client = PyJWKClient(config.OIDC_JWKS_URL, cache_keys=True, lifespan=300, timeout=5)


@dataclass
class User:
    sub: str
    username: str = ""
    email: str = ""
    roles: set = field(default_factory=set)
    scopes: set = field(default_factory=set)


def unauthorized(msg):
    return HTTPException(401, msg, headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{msg}"'})


def decode_token(token):
    if config.INSECURE_MODE:
        # version mala a proposito: decodifica y confia en lo que diga el payload
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            raise unauthorized("token ilegible")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise unauthorized("token mal formado")
    # corto aqui cualquier alg raro (none, HS256...) antes de buscar la clave
    if header.get("alg") not in config.JWT_ALGORITHMS:
        raise unauthorized("algoritmo no permitido")

    try:
        key = jwks_client.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "no se pudo contactar a Keycloak")
    except jwt.PyJWTError:
        # kid que no existe en mi realm (token de otro realm o inventado)
        raise unauthorized("clave de firma desconocida")

    try:
        claims = jwt.decode(token, key, algorithms=config.JWT_ALGORITHMS,
                            audience=config.OIDC_AUDIENCE, issuer=config.OIDC_ISSUER,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.ExpiredSignatureError:
        raise unauthorized("token vencido")
    except jwt.InvalidIssuerError:
        raise unauthorized("emisor no confiable")
    except jwt.InvalidAudienceError:
        raise unauthorized("audiencia incorrecta")
    except jwt.PyJWTError:
        raise unauthorized("token inválido")

    # el ID token de Keycloak trae typ=ID (y aud=lab-cli), asi que tambien cae aqui
    if claims.get("typ") != "Bearer":
        raise unauthorized("solo se aceptan access tokens")
    return claims


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise unauthorized("falta el token Bearer")
    claims = decode_token(creds.credentials)
    if not claims.get("sub"):
        raise unauthorized("token sin sub")
    user = User(
        sub=claims["sub"],
        username=claims.get("preferred_username", ""),
        email=claims.get("email", ""),
        roles=set(claims.get("realm_access", {}).get("roles", [])),
        scopes=set(str(claims.get("scope", "")).split()),
    )
    db.ensure_user(user.sub, user.username, user.email)
    return user


def require_scope(scope):
    def check(user: User = Depends(current_user)):
        if not config.INSECURE_MODE and scope not in user.scopes:
            db.audit(user.sub, "scope_denegado", scope)
            raise HTTPException(403, f"falta el scope {scope}")
        return user
    return check


def require_role(role):
    def check(user: User = Depends(current_user)):
        if not config.INSECURE_MODE and role not in user.roles:
            db.audit(user.sub, "bfla_denegado", role)
            raise HTTPException(403, f"se requiere el rol {role}")
        return user
    return check
