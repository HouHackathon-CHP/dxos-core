# Nhật ký thay đổi

Tất cả các thay đổi đáng chú ý của dự án này sẽ được ghi lại trong file này.

Định dạng dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
và dự án này tuân thủ [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Chưa phát hành

### Đã sửa

- Thêm `httpx>=0.27.0` vào `insight/requirements.txt` và bật `allow_headers=["*"]` trong Gateway `CORSMiddleware`.
- Mở public GET route cho `docs`, `redoc` và `openapi.json` trên Gateway để truy cập Swagger UI.

## [1.0.0] - 2026-11-27

### Đã thêm

- Configure citizen self-registration in Keycloak - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [80ca1f9](https://github.com/HouHackathon-CHP/dxos-core/commit/80ca1f9fa2232c32637389236d09170965af90d8)
- Configure citizen self-registration in Keycloak - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [4c8cb31](https://github.com/HouHackathon-CHP/dxos-core/commit/4c8cb3168ff8352e746a2aa92800460a04baea74)
- Keep civic AI outside DX-OS core - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [69a8ad1](https://github.com/HouHackathon-CHP/dxos-core/commit/69a8ad1325ca5783b876c50201caf89644e935d7)
- Allow configured anonymous GET routes through gateway - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [91d42cd](https://github.com/HouHackathon-CHP/dxos-core/commit/91d42cdb255a03ac68a4f0ab21953e290067cb17)
- Add internal insight service for text triage - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [568f7da](https://github.com/HouHackathon-CHP/dxos-core/commit/568f7da6e3b88d8ff30e22abfc405c8756cca679)
- Add OpenCity report dispatcher role - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [aad3810](https://github.com/HouHackathon-CHP/dxos-core/commit/aad3810e8b562dc0c52c1ad8ea36c08cdc05ba01)
- Forward verified unit scope to application APIs - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [f5801fa](https://github.com/HouHackathon-CHP/dxos-core/commit/f5801fa2911e972013e9ceae5e7b716193f56e6f)
- Restrict browser clients to application APIs - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [65d3f60](https://github.com/HouHackathon-CHP/dxos-core/commit/65d3f604d00bc407f89f5a133a73f9970953f160)
- Add native OIDC client for OpenCity mobile - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [064d837](https://github.com/HouHackathon-CHP/dxos-core/commit/064d837a8123f8efcb697e10129216a18ba94b27)
- Allow domain API upstreams and add source license notices - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [2bdfd79](https://github.com/HouHackathon-CHP/dxos-core/commit/2bdfd798760b840453e1ebfae879e5c2e7b917b9)
- Track structured record change history - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [f69f4ea](https://github.com/HouHackathon-CHP/dxos-core/commit/f69f4eaaa70b6973182498cb2ac6eccd845a2e1e)
- Prepare browser OIDC client with PKCE and scoped CORS - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [6e1cebc](https://github.com/HouHackathon-CHP/dxos-core/commit/6e1cebc058d554e09f20b266ac65f2aa8412d48d)
- Bootstrap headless DX-OS core - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [aa3f25a](https://github.com/HouHackathon-CHP/dxos-core/commit/aa3f25aa239a5b87d5f20d58057f3b560c60344b)

### Kiểm thử

- Run full Compose smoke test in CI - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [0ceaddc](https://github.com/HouHackathon-CHP/dxos-core/commit/0ceaddc771ec291740695a93d6bec898e685f2da)
- Expand tenant isolation smoke checks and update CI actions - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [43dafc9](https://github.com/HouHackathon-CHP/dxos-core/commit/43dafc95c53b38362a558ac34c8fc6c121f4d133)

### Tài liệu

- Document per-role demo credentials in core env - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [ace8408](https://github.com/HouHackathon-CHP/dxos-core/commit/ace8408b85a93a6e14c9d41697bed2e9a4ffa9cb)
- Document optional WAQI token in core env example - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [25c3ab5](https://github.com/HouHackathon-CHP/dxos-core/commit/25c3ab5d775fe66db9eab22525f5fdce1faf611d)
- docs: update OpenCity setup and feature guides - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [9da52dc](https://github.com/HouHackathon-CHP/dxos-core/commit/9da52dc85c884c39dcf0b8502e820dc0408ad982)
- Enforce tenant claims and document OSI license audit - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [74a9da2](https://github.com/HouHackathon-CHP/dxos-core/commit/74a9da2ce30a1c02168af7fe972db15a5b7c244d)

### Các thay đổi khác

- Merge pull request #6 from HouHackathon-CHP/dev - Nguyễn Hà Phương in [73af7cd](https://github.com/HouHackathon-CHP/dxos-core/commit/73af7cd650835da742c376f05ec2b99de9896170)
- Merge pull request #7 from HouHackathon-CHP/feature/citizen-registration - Nguyễn Hà Phương in [69e3953](https://github.com/HouHackathon-CHP/dxos-core/commit/69e39533610e57f26fe320f87f4426aa0e8280c9)
- Merge pull request #5 from HouHackathon-CHP/dev - Trần Trọng Chiến in [4a55495](https://github.com/HouHackathon-CHP/dxos-core/commit/4a55495b09834e4602fb136f779706070c41882c)
- Merge pull request #2 from HouHackathon-CHP/dev - Trần Trọng Chiến in [726d94c](https://github.com/HouHackathon-CHP/dxos-core/commit/726d94cc4f560117411c60990dea2c2626daf10d)
- Merge pull request #1 from HouHackathon-CHP/dev - Trần Trọng Chiến in [049a484](https://github.com/HouHackathon-CHP/dxos-core/commit/049a484cb2a929d248d8216866e0fb3014181b03)
- Ignore unseen words in insight ranking - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [149cc82](https://github.com/HouHackathon-CHP/dxos-core/commit/149cc82f1a1db04244400c39a2d9f9f77d2ab691)
- Update OpenCity backend integration references - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [c70ffc0](https://github.com/HouHackathon-CHP/dxos-core/commit/c70ffc0348bd87f14fe1f6ecd6f21e10fe7f4b14)
- Pin scanned container digests and record SBOM limits - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [fb97688](https://github.com/HouHackathon-CHP/dxos-core/commit/fb976884e255e6b4e32952e4f98b30988afc8183)
- Gate direct Python dependency updates on license review - Chien Tran ([@blueMonkey23](https://github.com/blueMonkey23)) in [a31a9dd](https://github.com/HouHackathon-CHP/dxos-core/commit/a31a9dda8ec08e5188f6faa43817e198e83d2cbd)

---
*Changelog được tạo tự động bởi [git-cliff](https://git-cliff.org). Xem hướng dẫn tại [docs/GIT_CLIFF_GUIDE.md](docs/GIT_CLIFF_GUIDE.md)*
