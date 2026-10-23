# Kiểm tra giấy phép nguồn mở

Ngày kiểm tra: 2026-10-22. OSI phê duyệt **giấy phép**, không phê duyệt sản phẩm hay image. Mỗi kết luận bên dưới áp dụng cho đúng phiên bản/phạm vi được nêu và phải kiểm tra lại khi nâng cấp.

Các tệp mã Python, Dockerfile, Compose và SQL trong repo có thông báo `SPDX-License-Identifier: Apache-2.0`; JSON cấu hình và tài liệu được cấp phép bởi `LICENSE` ở gốc repo. Thay đổi này giúp người đọc xác định giấy phép ngay tại tệp mã.

## Thành phần do đội chọn trực tiếp

| Thành phần | Phiên bản trong repo | Giấy phép dự án công bố | Đối chiếu OSI |
| --- | --- | --- | --- |
| Mã `dxos-core` do đội viết | commit hiện tại | Apache-2.0 (`LICENSE`) | Có |
| Keycloak (identity/SSO) | 26.4.0 | [Apache-2.0](https://github.com/keycloak/keycloak/blob/26.4.0/LICENSE.txt) | Có |
| PostgreSQL (dữ liệu giao dịch) | 16-alpine | [PostgreSQL License](https://www.postgresql.org/about/licence/) | Có |
| SeaweedFS (lưu trữ đối tượng) | 4.48 | [Apache-2.0](https://github.com/seaweedfs/seaweedfs/blob/4.48/LICENSE) | Có ở cấp dự án |
| Python runtime / image nền | `python:3.12-slim` | [Bộ giấy phép Python](https://docs.python.org/3.12/license.html) và các gói Debian trong image | Chưa kết luận ở cấp toàn image |
| FastAPI, PyJWT, SQLAlchemy | theo `requirements.txt` | MIT | Có |
| Uvicorn, HTTPX | theo `requirements.txt` | BSD-3-Clause | Có |
| boto3, python-multipart | theo `requirements.txt` | Apache-2.0 | Có |
| psycopg / psycopg-binary | theo `requirements.txt` | LGPL-3.0-only | Có |
| GitHub Actions `checkout`, `setup-python` (chỉ CI) | v7 | [MIT](https://github.com/actions/checkout/blob/main/LICENSE), [MIT](https://github.com/actions/setup-python/blob/main/LICENSE) | Có |

Các mã giấy phép trên được đối chiếu với [danh sách chính thức của OSI](https://opensource.org/licenses). Chữ `-only` trong metadata của LGPL chỉ rõ biến thể phiên bản 3, tương ứng giấy phép LGPL 3.0 mà OSI liệt kê.

CI chạy `scripts/check_direct_licenses.py` để buộc rà soát lại khi thêm/xóa/đổi phiên bản một thư viện Python được khai báo trực tiếp. Script so metadata của bản cài với danh sách đã duyệt; nó không chứng minh mọi dependency gián tiếp hay tệp bên trong image có giấy phép OSI.

SeaweedFS từng có vấn đề giấy phép ở icon giao diện quản trị; upstream đã [thay Font Awesome bằng icon MIT trong PR #11364](https://github.com/seaweedfs/seaweedfs/pull/11364) trước bản 4.48. Việc này không tự chứng minh rằng mọi tệp bên trong Docker image đều chỉ mang giấy phép OSI.

## Thư viện Python gián tiếp

Đã lấy metadata từ môi trường Python cài toàn bộ ba `requirements.txt` và `pytest` vào ngày kiểm tra. Các nhóm sau xuất hiện:

| Giấy phép trong metadata | Gói tiêu biểu | Đối chiếu OSI |
| --- | --- | --- |
| Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, MIT-0, MPL-2.0, LGPL-3.0-only | Phần lớn gói, gồm FastAPI, boto3, certifi, psycopg | Có |
| `Apache-2.0 OR BSD-3-Clause`, `Apache-2.0 OR BSD-2-Clause` | cryptography, packaging | Cả hai lựa chọn đều có |
| `Apache License 2.0` | s3transfer | Có; tên metadata không theo cú pháp SPDX |
| Metadata trống | colorama 0.4.6 | [Dự án công bố BSD-3-Clause](https://github.com/tartley/colorama/blob/master/pyproject.toml), có |
| `Dual License` | python-dateutil 2.9.0.post0 | [BSD-3-Clause / Apache-2.0](https://github.com/dateutil/dateutil/blob/master/LICENSE), đều có |
| `PSF-2.0` | typing_extensions 4.16.0 | **Chưa thể ghi là OSI approved**: [SPDX đánh dấu PSF-2.0 là `false`](https://spdx.org/licenses/PSF-2.0.html); [LICENSE của phiên bản này](https://github.com/python/typing_extensions/blob/4.16.0/LICENSE) chứa bộ giấy phép Python đầy đủ, nhưng metadata không khớp mã `Python-2.0` trong [danh sách OSI](https://opensource.org/licenses). Cần rà soát khi chốt bản phát hành. |

Vì ngoại lệ `typing_extensions`, hiện **chưa thể tuyên bố toàn bộ dependency tree đều mang giấy phép OSI approved**. Điều này không phủ định kết quả của các thành phần được chọn trực tiếp ở bảng đầu.

## Quét SBOM của image

Đã dùng `docker sbom` 0.6.0 (Syft 0.43.0) với định dạng `syft-json` cho các image đã kéo về ngày 2026-10-22. Các digest dưới đây được khóa trong Compose/Dockerfile:

| Image | Digest SHA-256 (12 ký tự đầu) | Gói phát hiện | Gói không có metadata giấy phép trong SBOM |
| --- | --- | ---: | ---: |
| `python:3.12-slim` | `cb33f7f771ec` | 88 | 1 |
| `postgres:16-alpine` | `721873c34ceb` | 48 | 4 (gồm một giá trị rỗng) |
| `quay.io/keycloak/keycloak:26.4.0` | `5f3fb534cde6` | 820 | 820 |
| `chrislusf/seaweedfs:4.48` | `4e61d15fd359` | 282 | 253 |

Tổng số gói chỉ là kết quả nhận diện của phiên bản scanner này, không phải danh mục pháp lý đầy đủ. Keycloak JAR và phần lớn module Go trong SeaweedFS không có nhãn giấy phép mà scanner lấy ra được. Một số gói Debian tổng hợp cả giấy phép của tài liệu/asset như GFDL hoặc CC; không thể suy ra giấy phép của từng tệp chỉ từ dòng metadata đó. Vì vậy SBOM **không chứng minh toàn bộ image đạt OSI approved**. Bốn image đã được quét và tóm tắt; file SBOM thô nằm trong thư mục tạm cục bộ, không chứa trong repo.

## Phạm vi còn phải kiểm tra trước khi nộp/phân phối

- Rà soát thủ công giấy phép của thư viện hệ điều hành, Java/Go và asset đi kèm, đặc biệt những gói SBOM thiếu metadata. Bảng đầu chỉ xác minh giấy phép **dự án cấp cao** của image.
- Khóa toàn bộ thư viện Python gián tiếp trước bản demo/nộp. Các thư viện trực tiếp và image đã khóa phiên bản/digest, nhưng dependency Python gián tiếp vẫn có thể nhận bản mới và đổi inventory.
- Lưu notice/license của phụ thuộc khi đóng gói hoặc phân phối image. Apache-2.0 và LGPL-3.0 có nghĩa vụ kèm theo giấy phép và thông báo thích hợp.
- Kiểm tra lại giấy phép của mỗi thành phần mới trước khi thêm vào Compose hoặc requirements. Ví dụ công nghệ trong [đề OLP](https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html) không phải chứng nhận OSI cho từng sản phẩm.
