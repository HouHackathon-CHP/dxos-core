# DX-OS Core — Layer 1

Headless open-source core for the HouHackathon-CHP OLP 2026 project. This repository groups four separately deployed capabilities in one place so their API contracts and local setup stay synchronized. Separate OpenCity backend, web frontend and citizen mobile repositories consume these APIs.

| Module | Implementation | First usable capability |
| --- | --- | --- |
| `identity/` | Keycloak realm | OIDC sign-in and application roles |
| `gateway/` | FastAPI + Keycloak JWKS | JWT validation and routing to internal APIs |
| `data/` | FastAPI + PostgreSQL + SeaweedFS S3 | Tenant-scoped JSON records, change history and object upload/download |
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

The smoke script registers the managed `tenant_id` Keycloak user attribute, checks the browser client and CORS settings, creates three local users from passwords in `.env`, obtains OIDC tokens, verifies tenant isolation, sends a structured report through the gateway, uploads and downloads an object, and advances a workflow using an operator role. It prints no passwords or tokens. It can be rerun.

For fast checks without Docker: install the three `requirements.txt` files plus `pytest`, then run `python -m pytest -q`.

The only published development ports are `127.0.0.1:8000` (API gateway) and `127.0.0.1:8081` (Keycloak). PostgreSQL, SeaweedFS and internal APIs stay on the Compose network. `/health` is public. Generic `/api/{data|workflow}/...` routes accept only the local `dxos-cli` client. Web and mobile clients use application APIs such as `/api/opencity/...`, whose backend enforces feature permissions before delegating to the core.

`dxos-web` is a separate local public OIDC client for a browser app at `http://localhost:3000`. It enables Authorization Code with mandatory PKCE S256, accepts only local redirect URIs, and receives the `dxos-api` audience and `tenant_id` claim. The gateway allows that origin for browser API requests. Change the origin and redirects together when the frontend is deployed elsewhere.

`dxos-mobile` is a separate public OIDC client for the citizen Android app. It requires Authorization Code with PKCE S256 and allows only `opencity://auth` as a redirect. For an Android emulator, run `adb reverse tcp:8081 tcp:8081` and `adb reverse tcp:8000 tcp:8000` so the app and browser resolve the same localhost issuer and gateway. The smoke script adds this client to an existing local realm.

## API sketch

- `POST /api/data/records`, `GET /api/data/records`, `GET /api/data/records/{id}`, `PATCH /api/data/records/{id}`, `GET /api/data/records/{id}/history`
- `POST /api/data/objects?record_id={id}`, `GET /api/data/objects/{id}`
- `GET /api/workflow/definitions`, `POST /api/workflow/instances`, `GET /api/workflow/instances/{id}`
- `POST /api/workflow/instances/{id}/actions/{action}`

Application backends can be mounted behind the same authenticated edge with `EXTRA_UPSTREAMS`, a JSON object mapping a short route name to an internal HTTP URL (for example `{"opencity":"http://opencity-backend:8000"}`). These services receive only gateway-generated identity headers and the internal secret. The optional [OpenCity Backend](https://github.com/HouHackathon-CHP/opencity-backend) shows this integration; the core itself does not include city business rules.

The gateway validates token signature, issuer, audience and authorized client, then derives the caller's user ID, tenant, optional `unit_id`, and roles from the signed token and injects internal headers. Tokens without a valid `tenant_id` claim or with a malformed `unit_id` are rejected. Data and workflow endpoints reject calls without the shared internal gateway secret. The generic `operator` role remains available to the core CLI smoke test; OpenCity uses `reports_dispatcher` for tenant-wide intake, `reports_operator` plus an admin-managed unit claim for report handlers, and separate feature roles for bulletins and surveys.

## Development boundary

This is a first runnable slice of Layer 1. The local `dxos-cli` client enables password grants for an automated test; browser applications use `dxos-web` and the citizen mobile app uses `dxos-mobile`. The workflow engine accepts validated JSON state graphs; BPMN import, migrations, audit export, antivirus scanning, production secrets, backups and deployment hardening are subsequent work. Do not expose this Compose setup directly to the Internet.

The contest requirement is the headless core's four capabilities, not four Git repositories: [OLP 2026 DX-OS prompt](https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html).

## License

Apache-2.0. The container images and Python dependencies retain their own licenses. See the [component license audit](docs/license-audit.md) for OSI checks, the transitive dependency exception, and the remaining image audit.
