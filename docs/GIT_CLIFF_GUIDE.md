# Hướng dẫn sử dụng git-cliff

Tệp `CHANGELOG.md` của dự án được cấu hình tự động hóa bằng **[git-cliff](https://git-cliff.org)** thông qua tệp `cliff.toml` và GitHub Actions workflow `.github/workflows/changelog.yml`.

## 1. Tự động cập nhật trên GitHub
Mỗi khi có commit hoặc Pull Request được merge vào nhánh `main` (hoặc tạo tag phiên bản mới), workflow `.github/workflows/changelog.yml` sẽ tự động chạy `git-cliff` và cập nhật `CHANGELOG.md`.

## 2. Chạy thủ công trên máy cá nhân (tùy chọn)

Cài đặt `git-cliff`:
```powershell
winget install orhun.git-cliff
```

Sinh lại `CHANGELOG.md`:
```powershell
git-cliff -o CHANGELOG.md
```

Sinh changelog cho một tag phát hành mới (ví dụ `1.0.1`):
```powershell
git-cliff --tag 1.0.1 -o CHANGELOG.md
```
