# DX-OS Core — Layer 1

Headless open-source core for the HouHackathon-CHP OLP 2026 project. This repository groups four separately deployed capabilities in one place so their API contracts and local setup stay synchronized. Application repositories (backend, frontend and mobile) will consume these APIs later.

| Module | Implementation | First usable capability |
| --- | --- | --- |
| `identity/` | Keycloak realm | OIDC sign-in, roles `citizen` and `operator` |
| `gateway/` | FastAPI + Keycloak JWKS | JWT validation and routing to internal APIs |
| `data/` | FastAPI + PostgreSQL + SeaweedFS S3 | Tenant-scoped JSON records and object upload/download |
| `workflow/` | FastAPI + PostgreSQL | File-defined JSON workflow, transitions and history |

The `report-handling` definition is only a demonstration of the generic workflow API. The core contains no end-user interface or GreenCity business rules.

## Run locally

Requires Docker Desktop with the Linux engine and Python 3.10+ for the smoke script.

```powershell
Copy-Item .env.example .env
# Replace all values in .env with local random secrets.
docker compose up --build -d
python scripts/smoke.py
```

The smoke script registers the managed `tenant_id` Keycloak user attribute, creates three local users from passwords in `.env`, obtains OIDC tokens, verifies tenant isolation, sends a structured report through the gateway, uploads and downloads an object, and advances a workflow using an operator role. It prints no passwords or tokens. It can be rerun.

For fast checks without Docker: install the three `requirements.txt` files plus `pytest`, then run `python -m pytest -q`.

The only published development ports are `127.0.0.1:8000` (API gateway) and `127.0.0.1:8081` (Keycloak). PostgreSQL, SeaweedFS and internal APIs stay on the Compose network. `/health` is public. All `/api/{data|workflow}/...` routes require a Keycloak bearer token from `dxos-cli`.

## API sketch

- `POST /api/data/records`, `GET /api/data/records`, `GET /api/data/records/{id}`, `PATCH /api/data/records/{id}`
- `POST /api/data/objects?record_id={id}`, `GET /api/data/objects/{id}`
- `GET /api/workflow/definitions`, `POST /api/workflow/instances`, `GET /api/workflow/instances/{id}`
- `POST /api/workflow/instances/{id}/actions/{action}`

The gateway validates token signature, issuer, audience and authorized client, then derives the caller's user ID, tenant and roles from the signed token and injects internal headers. Tokens without a valid `tenant_id` claim are rejected. Data and workflow endpoints reject calls without the shared internal gateway secret. Operators can see their tenant's records and workflows; citizens see their own.

## Development boundary

This is a first runnable slice of Layer 1. The local `dxos-cli` client enables password grants for an automated test; a browser app should use authorization code with PKCE and a separate client. The workflow engine accepts validated JSON state graphs; BPMN import, migrations, audit export, antivirus scanning, production secrets, backups and deployment hardening are subsequent work. The application UI required by the contest's Layer 2 is also subsequent work. Do not expose this Compose setup directly to the Internet.

The contest requirement is the headless core's four capabilities, not four Git repositories: [OLP 2026 DX-OS prompt](https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html).

## License

Apache-2.0. The container images and Python dependencies retain their own licenses. See the [component license audit](docs/license-audit.md) for OSI checks, the transitive dependency exception, and the remaining image audit.

