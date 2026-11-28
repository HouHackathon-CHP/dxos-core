<div align="center">

# DX-OS Core — Layer 1

**Lõi Hệ điều hành Chuyển đổi số Mở (Headless Open-Core) cho OLP 2026**

<p>
  <a href="#gioi-thieu">Giới thiệu</a> &bull;
  <a href="#kien-truc">Kiến trúc &amp; Module</a> &bull;
  <a href="#cong-nghe">Công nghệ</a> &bull;
  <a href="#cai-dat">Cài đặt</a> &bull;
  <a href="#api">API Lõi</a> &bull;
  <a href="#thanh-vien">Đội ngũ</a> &bull;
  <a href="#dong-gop">Đóng góp</a>
</p>

<p>
  <img src="https://img.shields.io/badge/License-Apache_2.0-0f172a?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.158-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Keycloak-26.4-4D4D4D?style=flat-square&logo=keycloak&logoColor=white" alt="Keycloak">
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
</p>

</div>

---

## Giới thiệu <a id="gioi-thieu"></a>

**DX-OS Core** là tầng hạ tầng lõi *headless* được thiết kế cho bài toán **OLP 2026 — DX-OS Open-Core**. Thay vì để mỗi ứng dụng chuyển đổi số phải xây dựng lại từ đầu hệ thống đăng nhập, phân quyền, cổng API, lưu trữ dữ liệu hay quy trình xử lý hồ sơ, `dxos-core` tách riêng toàn bộ năng lực nền tảng dùng chung vào một lõi độc lập.

Điểm cốt lõi của `dxos-core` là **hoàn toàn không chứa nghiệp vụ cụ thể** (không giao diện người dùng, không quy tắc đô thị cứng). Mọi domain backend bên ngoài — như [`opencity-backend`](https://github.com/HouHackathon-CHP/opencity-backend), cổng web [`opencity-frontend`](https://github.com/HouHackathon-CHP/opencity-frontend) và ứng dụng [`opencity-mobile`](https://github.com/HouHackathon-CHP/opencity-mobile) — đều gắn vào qua `EXTRA_UPSTREAMS` của API Gateway.

---

## Kiến trúc & 5 Module Lõi <a id="kien-truc"></a>

```text
dxos-core/
├── identity/          # Keycloak 26.4 realm config (OIDC + PKCE, tenant_id, unit_id, roles)
├── gateway/           # FastAPI API Edge (verify RS256 JWKS, CORS, routing, X-DXOS-* headers)
├── data/              # Structured JSON records (PostgreSQL) & S3 objects (SeaweedFS)
├── workflow/          # JSON State-Graph workflow engine & transition history (PostgreSQL)
├── insight/           # Internal text classification & similarity ranking (Naive Bayes + TF-IDF)
├── postgres-init/     # Khởi tạo 3 database độc lập: dxos_identity, dxos_data, dxos_workflow
├── scripts/smoke.py   # Kiểm thử tự động Keycloak, Gateway, Data, Object Store & Workflow
├── docs/              # Kiểm toán giấy phép OSI (license-audit.md)
└── compose.yaml       # Đóng gói toàn bộ Layer 1 với image digest cố định
```

| Module | Thành phần triển khai | Vai trò trong hệ thống |
| --- | --- | --- |
| `identity/` | Keycloak `26.4.0` + PostgreSQL | Quản lý đăng nhập SSO (OIDC + PKCE S256 cho `dxos-web`, `dxos-mobile`, `dxos-cli`) và phân quyền vai trò theo `tenant_id`, `unit_id`. |
| `gateway/` | FastAPI + PyJWT + httpx | Cửa ngõ duy nhất tại `:8000`. Xác thực chữ ký `RS256` qua Keycloak JWKS, kiểm soát CORS, mở Public GET allowlist (`PUBLIC_GET_ROUTES`), tiêm `X-DXOS-*` và `X-Internal-Secret`. |
| `data/` | FastAPI + PostgreSQL 16 + SeaweedFS | Lưu trữ bản ghi JSON phân tách theo tenant kèm lịch sử thay đổi (`history`) và upload/download tệp đính kèm chuẩn S3 (`dxos-objects`). |
| `workflow/` | FastAPI + PostgreSQL 16 | Thực thi máy trạng thái định nghĩa bằng JSON (ví dụ `report-handling`), chặn chuyển bước sai quyền/sai trạng thái và ghi nhật ký chuyển bước. |

---

## Công nghệ Sử dụng <a id="cong-nghe"></a>

| Lớp thành phần | Công nghệ | Lý do lựa chọn |
| --- | --- | --- |
| **SSO & RBAC** | Keycloak `26.4.0` | Chuẩn mở OIDC / OAuth 2.0, hỗ trợ PKCE S256, custom claim `tenant_id` và `unit_id`. |
| **API Edge & Microservices** | Python `3.12` + FastAPI + Uvicorn | Nhẹ, hiệu năng cao, dễ mở rộng upstream qua `EXTRA_UPSTREAMS`. |
| **Structured Storage** | PostgreSQL `16-alpine` + SQLAlchemy + psycopg | Đảm bảo toàn vẹn giao dịch cho định danh, bản ghi JSON và nhật ký workflow. |
| **Object Storage** | SeaweedFS `4.48` (S3) + boto3 | Lưu trữ tệp đính kèm chuẩn S3 nhẹ, giấy phép Apache-2.0. |
| **JWT & Security** | PyJWT `[crypto]` (`RS256` JWKS) | Xác thực token tập trung tại Gateway; dịch vụ nội bộ chỉ nhận traffic có `INTERNAL_GATEWAY_SECRET`. |

---

## Hướng dẫn Cài đặt & Khởi chạy <a id="cai-dat"></a>

Yêu cầu: **Docker** (Linux engine) và **Python 3.10+**.

### 1. Chạy độc lập `dxos-core`

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Thay thế các secret mặc định trong .env nếu triển khai thực tế
docker compose up --build -d
python scripts/smoke.py
python scripts/configure_registration.py
```

<<<<<<< Updated upstream
The smoke script registers the managed `tenant_id` Keycloak user attribute, checks the browser client and CORS settings, creates three local users from the `DEMO_CITIZEN_*`, `DEMO_OPERATOR_*`, and `DEMO_OUTSIDER_*` pairs in `.env`, obtains OIDC tokens, verifies tenant isolation, sends a structured report through the gateway, uploads and downloads an object, and advances a workflow using an operator role. It prints no passwords or tokens. It can be rerun.

`configure_registration.py` enables citizen self-registration in both fresh and existing local Keycloak realms. New accounts get the `citizen` role and inherit the local `demo` tenant from a default Keycloak group. Explicit tenant attributes on managed users take precedence. Keycloak's built-in registration form is used by web and Android via OIDC `prompt=create`. This local demo has no outbound mail verification; configure email verification and abuse protection before Internet deployment.

The remaining `DEMO_*_USERNAME` and `DEMO_*_PASSWORD` pairs in `.env.example` are OpenCity staff and portal admin demo accounts. `opencity-backend/scripts/provision_roles.py` creates or updates them in the same Keycloak realm. Keep real passwords only in ignored `.env`; never commit that file. `DEMO_ADMIN_*` signs in to the OpenCity `/admin` page, while `KEYCLOAK_ADMIN_PASSWORD` belongs to the separate Keycloak master administrator.
=======
Script `smoke.py` có thể chạy lặp lại an toàn (*idempotent*), tự động cấu hình mapper `tenant_id` trên Keycloak, tạo 3 tài khoản test và kiểm tra đầy đủ các luồng Gateway $\rightarrow$ Data / Object Store / Workflow.
>>>>>>> Stashed changes

### 2. Chạy kết hợp toàn bộ Hệ sinh thái OpenCity

Để chạy kèm API nghiệp vụ `opencity-backend`, khởi động từ thư mục anh em `opencity-backend` bằng file `compose.stack.yaml`:

```powershell
cd ..\opencity-backend
docker compose --env-file ..\dxos-core\.env -f ..\dxos-core\compose.yaml -f compose.stack.yaml up --build -d
python ..\dxos-core\scripts\smoke.py
python scripts\smoke_app.py
```

* **Cổng công khai duy nhất**: `127.0.0.1:8000` (API Gateway) và `127.0.0.1:8081` (Keycloak). PostgreSQL, SeaweedFS và các API nội bộ nằm hoàn toàn trong mạng Docker Compose.
* **Kiểm thử nhanh không cần Docker**: Cài `requirements.txt` của từng module cùng `pytest` và chạy `python -m pytest -q`.

---

## Sơ lược API & Cơ chế Mở rộng <a id="api"></a>

* **Data API**: `POST /api/data/records`, `GET /api/data/records`, `GET /api/data/records/{id}`, `PATCH /api/data/records/{id}`, `GET /api/data/records/{id}/history`, `POST /api/data/objects?record_id={id}`, `GET /api/data/objects/{id}`.
* **Workflow API**: `GET /api/workflow/definitions`, `POST /api/workflow/instances`, `GET /api/workflow/instances/{id}`, `POST /api/workflow/instances/{id}/actions/{action}`.
* **Gắn Domain Backend & AI riêng**: Khai báo `EXTRA_UPSTREAMS='{"opencity":"http://opencity-backend:8000"}'` và `PUBLIC_GET_ROUTES` trên Gateway. Các dịch vụ AI chuyên biệt (như [OpenCity AI](https://github.com/HouHackathon-CHP/opencity-ai)) chạy tách rời ngoài lõi để giữ `dxos-core` hoàn toàn *headless*.

> **Phạm vi nguyên mẫu**: Đây là tầng lõi đầu tiên phục vụ cuộc thi [OLP 2026 DX-OS](https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html). Không mở trực tiếp cấu hình Compose phát triển này ra Internet khi chưa bổ sung quét mã độc tệp tải lên, rate limiting, cơ chế backup và quản lý secret production.

---

## Thành viên Dự án <a id="thanh-vien"></a>

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/hieutnago">
        <img src="https://github.com/hieutnago.png" width="96px" alt="Trương Ngọc Hiểu"/><br>
        <sub><b>Trương Ngọc Hiểu</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/HouHackathon-CHP">
        <img src="https://avatars.githubusercontent.com/u/168514215?v=4" width="96px" alt="Trần Trọng Chiến"/><br>
        <sub><b>Trần Trọng Chiến</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/HouHackathon-CHP">
        <img src="https://avatars.githubusercontent.com/u/100331812?v=4" width="96px" alt="Nguyễn Hà Phương"/><br>
        <sub><b>Nguyễn Hà Phương</b></sub>
      </a>
    </td>
  </tr>
</table>

---

## Đóng góp & Giấy phép <a id="dong-gop"></a>

1. Fork repository này và tạo nhánh mới từ `dev`: `git checkout -b feature/ten-tinh-nang`.
2. Commit thay đổi theo chuẩn rõ ràng, chạy `python -m pytest -q` trước khi mở Pull Request.
3. Gửi Pull Request kèm mô tả phạm vi thay đổi.

Phát hành theo giấy phép **Apache License 2.0** — xem [LICENSE](LICENSE), [docs/license-audit.md](docs/license-audit.md) và [CHANGELOG.md](CHANGELOG.md).
