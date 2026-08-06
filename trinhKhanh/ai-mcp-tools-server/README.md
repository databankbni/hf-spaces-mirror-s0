---
title: AI Robot MCP Tools Server
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# AI Robot MCP Tools Server

Backend AI cho robot trò chuyện với trẻ em, kết hợp FastAPI + Gemini 2.5 Flash + MCP tools.

## WebSocket

Kết nối: `wss://<space-url>/ws/robot/{user_id}`

## Endpoints

- `GET /health` — kiểm tra trạng thái server
- `GET /api/tools` — danh sách MCP tools đã đăng ký
- `POST /api/tools/run` — gọi tool trực tiếp

## Environment Variables (set trong Space Settings → Secrets)

| Tên | Bắt buộc | Mô tả |
|-----|----------|-------|
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |
| `SEARXNG_URL` | ✅ | URL SearXNG (ví dụ: `https://ai-robot-searxng.onrender.com`) |
| `DB_HOST` | ❌ | PostgreSQL host (nếu không set, app chạy không có DB) |
| `DB_PORT` | ❌ | PostgreSQL port |
| `DB_USER` | ❌ | PostgreSQL user |
| `DB_PASSWORD` | ❌ | PostgreSQL password |
| `DB_NAME` | ❌ | PostgreSQL database name |
| `SMARTLIGHT_API_URL` | ❌ | Smart light API URL |

## Media sync qua Cloudflare R2

Chức năng media bắt buộc PostgreSQL và một R2 private bucket. Các API admin hiện không
có xác thực; chỉ triển khai server ở môi trường mà rủi ro này đã được chấp nhận.

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `R2_ENDPOINT_URL` | ✅ | `https://<account-id>.r2.cloudflarestorage.com` |
| `R2_BUCKET` | ✅ | Tên private bucket |
| `R2_ACCESS_KEY_ID` | ✅ | R2 access key |
| `R2_SECRET_ACCESS_KEY` | ✅ | R2 secret key |
| `MEDIA_PUBLIC_BASE_URL` | ✅ | Base URL mà ESP32 truy cập được, không có dấu `/` cuối; production phải dùng HTTPS |
| `MEDIA_API_BASE_URL` | ❌ | Base URL nội bộ cho MCP server, mặc định `http://127.0.0.1:7860` |
| `MEDIA_SIGNED_URL_TTL_SECONDS` | ❌ | TTL signed URL, mặc định 3600 giây |
| `MEDIA_TRANSFER_TTL_SECONDS` | ❌ | TTL ACK ticket, mặc định 3600 giây |
| `MEDIA_TTL_HOURS` | ❌ | Thời gian giữ object chưa tải, mặc định 24 giờ |

Giới hạn mặc định: ảnh đầu vào 10 MB/PNG đầu ra 1 MB, audio MP3 đầu ra 30 MB,
video AVI đầu ra 100 MB. Có thể đổi bằng các biến `MEDIA_*_MAX_BYTES` trong
`app/media.py`, nhưng firmware vẫn từ chối file vượt các giới hạn này.

Trong Cloudflare R2, cấu hình lifecycle rule xóa object có prefix `media/` sau 1 ngày.
Đây là lớp bảo vệ cuối; bình thường server xóa object ngay sau ACK đúng size và SHA-256,
đồng thời job cleanup chạy khi startup và mỗi giờ.

Khi test trong cùng LAN, chạy Uvicorn với `--host 0.0.0.0` và đặt
`MEDIA_PUBLIC_BASE_URL=http://<IP-LAN-của-laptop>:7860`; không dùng `127.0.0.1`
vì địa chỉ đó trên ESP trỏ về chính ESP. Mở port 7860 trên firewall Windows nếu cần.
