"""JWT-validated API edge for the headless DX-OS services."""

import os
import re
from urllib.error import URLError

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from jwt import PyJWKClient


ISSUER = os.getenv("KEYCLOAK_ISSUER", "http://localhost:8081/realms/dxos")
JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL",
    "http://localhost:8081/realms/dxos/protocol/openid-connect/certs",
)
ALLOWED_CLIENT_IDS = set(os.getenv("ALLOWED_CLIENT_IDS", "dxos-cli").split(","))
CORS_ORIGINS = [origin for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin]
API_AUDIENCE = os.getenv("API_AUDIENCE", "dxos-api")
UPSTREAMS = {
    "data": os.getenv("DATA_URL", "http://localhost:8001"),
    "workflow": os.getenv("WORKFLOW_URL", "http://localhost:8002"),
}
INTERNAL_SECRET = os.getenv("INTERNAL_GATEWAY_SECRET", "")
JWK_CLIENT = PyJWKClient(JWKS_URL, cache_keys=True, timeout=5)

app = FastAPI(title="DX-OS API Gateway", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def claims_from_authorization(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        key = JWK_CLIENT.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=API_AUDIENCE,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
    except (jwt.PyJWTError, URLError, TimeoutError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    if claims.get("azp") not in ALLOWED_CLIENT_IDS:
        raise HTTPException(status_code=403, detail="Client is not allowed")
    if not isinstance(claims.get("tenant_id"), str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,64}", claims["tenant_id"]
    ):
        raise HTTPException(status_code=403, detail="Tenant claim is required")
    return claims


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "gateway"}


@app.api_route(
    "/api/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(service: str, path: str, request: Request) -> Response:
    if service not in UPSTREAMS:
        raise HTTPException(status_code=404, detail="Unknown service")
    claims = claims_from_authorization(request.headers.get("authorization"))
    roles = claims.get("realm_access", {}).get("roles", [])
    # Never trust identity headers from the caller. Only the gateway can set them.
    headers = {
        "X-DXOS-User": str(claims["sub"]),
        "X-DXOS-Tenant": claims["tenant_id"],
        "X-DXOS-Roles": ",".join(role for role in roles if isinstance(role, str)),
        "X-Internal-Secret": INTERNAL_SECRET,
    }
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    url = f"{UPSTREAMS[service].rstrip('/')}/{path}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.request(
                request.method,
                url,
                params=request.query_params,
                content=await request.body(),
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"{service} is unavailable") from exc
    response_headers = {}
    for header in ("content-type", "content-disposition"):
        if header in upstream.headers:
            response_headers[header] = upstream.headers[header]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )

