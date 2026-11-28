# Hướng dẫn Đóng góp Dự án (DX-OS Core)

Xin chân thành cảm ơn sự quan tâm và đóng góp của bạn cho **DX-OS Core** (`HouHackathon-CHP`).
Chúng tôi luôn chào đón mọi hình thức đóng góp, bao gồm báo cáo lỗi, đề xuất cải tiến và gửi Pull Request.

## Thông báo Lỗi & Đề xuất Cải tiến

- Kiểm tra tab **Issues** để xác minh vấn đề chưa được báo cáo trước đó.
- Sử dụng tiêu đề cụ thể, rõ ràng theo đúng module (`gateway`, `identity`, `data`, `workflow`, `insight`).
- Cung cấp đầy đủ thông tin: môi trường (Docker / Python), các bước tái tạo lỗi, kết quả mong muốn và kết quả thực tế.

## Quy trình Pull Request

1. Fork repository này về tài khoản cá nhân.
2. Tạo nhánh làm việc mới từ `dev` (hoặc `main`): `git checkout -b fix/ten-loi` hoặc `feature/ten-tinh-nang`.
3. Chia nhỏ commit theo từng thay đổi có ý nghĩa (khuyến khích chuẩn Conventional Commits để `git-cliff` phân loại tự động vào `CHANGELOG.md`).
4. Đảm bảo tệp mã nguồn mới có dòng `# SPDX-License-Identifier: Apache-2.0` ở đầu tệp.
5. Chạy kiểm thử (`python -m pytest -q` và `python scripts/smoke.py`) trước khi mở Pull Request.
6. Push lên fork cá nhân và tạo Pull Request kèm mô tả rõ phạm vi thay đổi.

## Tiêu chuẩn Mã nguồn & Giấy phép

- Giữ `dxos-core` hoàn toàn *headless*, không đưa quy tắc nghiệp vụ riêng của ứng dụng tầng trên vào lõi.
- Mọi thư viện phụ thuộc trực tiếp phải thuộc giấy phép nguồn mở được OSI công nhận (đã kiểm tra qua `docs/license-audit.md`).

## Nguyên tắc Cộng đồng

- Tôn trọng mọi thành viên và tuân thủ [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Giữ thái độ trao đổi xây dựng, minh bạch và chuyên nghiệp.

## Liên hệ Hỗ trợ

Khi cần hỗ trợ, bạn có thể tạo Issue mới trên repository hoặc liên hệ nhóm phát triển qua:
- **Email**: trantrongchien05@gmail.com
