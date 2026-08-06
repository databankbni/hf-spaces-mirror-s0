# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

**Run the app (local):**
```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```
> Default port is `7860` (override with `PORT` env var).

**Start infra only (DB + SearXNG) for local dev:**
```powershell
docker-compose up db searxng
```
> `docker-compose up --build` is broken — `docker-compose.yml` still references legacy services (`gateway`, `math_server`) that no longer exist. Only use it to spin up `db` and `searxng`.

**Test MCP tools trực tiếp (không cần server chạy):**
```powershell
python tests/test_tools.py
```
> `test_tools.py` imports từ các file server riêng lẻ (`weather_server.py`, `news_server.py`, `gold_server.py`). Những file này là legacy — server thực tế là `servers/combined_server.py`.

**Test WebSocket end-to-end (cần server đang chạy):**
```powershell
python tests/test_ws.py
```
> `test_ws.py` hardcode `ws://localhost:8000/...` nhưng app default là **7860** → phải sửa `URI` trong file hoặc chạy app với `PORT=8000`. Cũng hardcode UUID `fa8e2f90-9e57-4455-9dae-39c86595524f`; nếu không có DB, app vẫn chạy nhưng profile bé sẽ là anonymous. Test này đi qua path Gemini (dormant) nên cần `GEMINI_API_KEY`.

**Install dependencies:**
```powershell
pip install -r requirements.txt
```

**Tạo bảng / chạy migration trên Neon (không cần psql):**
```powershell
python scripts/run_migration.py --dry-run                        # xem sẽ chạy file nào
python scripts/run_migration.py                                  # chạy TẤT CẢ migrate_*.sql theo thứ tự
python scripts/run_migration.py scripts/migrate_005_create_su_ky.sql   # chỉ 1 file
```
> Xem "Migrations" bên dưới. Mọi migration đều `IF NOT EXISTS` → chạy lại vô hại.

**Cấp quyền admin (tài khoản đăng ký qua web luôn là role `user`):**
```powershell
python scripts/make_admin.py --list                 # xem tài khoản + role
python scripts/make_admin.py ban@email.com          # cấp admin
python scripts/make_admin.py ban@email.com --revoke # thu về 'user'
```
> `/adminctrl` đòi role `admin` → phải chạy lệnh này một lần cho tài khoản đầu tiên, không thì không ai vào được trang admin.

**Kiểm tra port bị chiếm (`[Errno 10048]`):**
```powershell
netstat -ano | findstr :7860
```

## Architecture

Backend AI cho robot trò chuyện với trẻ em, dựa trên FastAPI + MCP tools.

> **⚠️ LLM thật là DeepSeek chạy trên phần cứng (ESP32/robot), KHÔNG phải Gemini.** Trong deployment thật, thiết bị chạy DeepSeek xử lý hội thoại/phân tích và gọi tools của server này qua **outbound MCP** (device → broker → `app/mcp_outbound.py` → `combined_server.py`). Path Gemini bên dưới (`app/state.py` `genai.Client()`, `ws_handler.py` `model="gemini-2.5-flash"`, WebSocket `/ws/robot/{user_id}`, `GEMINI_API_KEY`) vẫn còn trong code nhưng **không hoạt động trong production** — coi là legacy/dormant. Khi debug "một request được xử lý thế nào", đi theo luồng outbound-MCP + tools, không phải vòng lặp Gemini trong `ws_handler`.

Sơ đồ luồng Gemini (chỉ để tham khảo — path dormant):

```
Client (WebSocket) ──► ws_handler.py ──► Gemini 2.5 Flash
                                              │
                                    (function_calls)
                                              │
                              mcp_sessions["combined-server"]
                                              │
                                    combined_server.py (stdio)
                                    [calculator, google_search,
                                     get_gold_price, get_news,
                                     get_news_detail, get_weather,
                                     search_stories, play_story,
                                     prepare_media_download,
                                     get_why_questions,
                                     show_why_image, hide_why_image,
                                     tim_su_kien, ke_su_ky,
                                     tiep_tuc_su_ky]
```
> 15 tool đang đăng ký (đúng danh sách trên). `control_light` / `control_lights_batch` **không** nằm trong đó — decorator đã bị comment out.

### Luồng chính (`app/ws_handler.py`)

Mỗi kết nối `/ws/robot/{user_id}` tạo một Gemini chat session riêng. Quy trình xử lý mỗi turn:

1. Nhận input: text hoặc audio bytes → STT qua Google Speech Recognition (chạy sync trong executor).
2. Gửi tới Gemini, nhận `response.function_calls` hoặc `response.text`.
3. Nếu có tool call:
   - `update_preferences` → xử lý thẳng qua `db.update_user_preferences()`, **không qua MCP**.
   - `google_search` → gọi MCP, gửi kết quả `{"success": true, "result": ...}` thẳng xuống client, **không đưa lại Gemini**, skip TTS.
   - Các tool khác → gọi MCP, đưa kết quả lại Gemini để tổng hợp câu trả lời.
4. Output: JSON `{"type": "text_response", "message": ...}` + audio bytes (TTS qua edge-tts, giọng `vi-VN-HoaiMyNeural`).

Rate-limit Gemini 429 được xử lý trong `_safe_send_message` (retry 3 lần, parse `retry in Xs` từ error message).

### Global state (`app/state.py`)

Module-level singletons, import trực tiếp không qua class:
- `db_pool` — asyncpg connection pool
- `mcp_sessions` — dict `server_name → ClientSession`
- `mcp_tools_registry` — list of `{"server": str, "tool": Tool}`, dùng để map tool name → server
- `outbound_connections` — dict `url → {status, task, tools_count, ...}`
- `gemini_client` — `genai.Client()`
- `exit_stack` — `AsyncExitStack` quản lý MCP stdio transports
- `preference_tool` — hardcoded `types.Tool` cho `update_preferences` (không phải MCP)
- `json_schema_to_gemini()` — chuyển JSON Schema → Gemini `types.Schema`

### MCP Servers (`servers/`)

`combined_server.py` là server **duy nhất đang chạy**. Khai báo trong `mcp_config.json`; `app/main.py` đọc file này lúc startup và spawn subprocess stdio. Gộp tất cả tools vào 1 subprocess để tiết kiệm RAM trên Render free tier.

**Để thêm tool mới:** thêm `@mcp.tool()` function vào `combined_server.py`.

Các file server riêng lẻ (`math_server.py`, `weather_server.py`, v.v.) là legacy, không được khởi động.

Smart light tools (`control_light`, `control_lights_batch`) hiện **đã tắt** — decorator bị comment (`# @mcp.tool()  # Đã ẩn`) nên không xuất hiện trong `tools/list` gửi broker. Hàm vẫn còn nguyên; muốn bật lại chỉ cần bỏ comment. `SMARTLIGHT_API_URL` default là `http://localhost:5067`.

Story (truyện cổ tích) dùng RSS từ Anchor.fm, cache in-memory 30 phút với ETag. Scraping web song song tối đa 3 URL (`SCRAPE_WORKERS`).

`play_story` có 2 chế độ:
- Khi `DEVICE_API_URL` được đặt: push audio URL trực tiếp tới thiết bị qua `POST /api/play` sau `DEVICE_PLAY_DELAY` giây (background thread, bỏ qua LLM). Trả về `{"success": True, "title": ...}` ngay.
- Khi không có `DEVICE_API_URL`: trả về URL cho LLM, LLM phải gọi `self.audio.play_url`.

### Why Questions (`get_why_questions`, `show_why_image`, `hide_why_image`)

Tính năng "1 vạn câu hỏi vì sao" dùng **Neon PostgreSQL** (cloud, schema `tools` — cùng một Neon với DB chính, xem "Chỉ 1 DB"). Bảng `tools.why_questions` chứa `id, question, answer, image_urls (jsonb), category, shown_count`. Migrations: `migrate_001_create_why_questions.sql` rồi `migrate_002_add_unique_question.sql` (unique index trên `MD5(question)` để build script chạy lại không tạo trùng lặp) — chạy bằng `python scripts/run_migration.py`, xem "Migrations".

Populate: `python scripts/build_why_db.py --sources wikipedia,nasa,wikidata --limit 5000` (mỗi source có fetcher riêng trong `scripts/fetch_*.py`; bỏ `--sources` để chạy tất cả, dùng `--limit`/`--per-cat` để test nhanh).

Luồng: `get_why_questions` → LLM gọi `show_why_image` trước mỗi câu → đọc câu hỏi + đáp án → `hide_why_image` sau câu cuối. (Phần prefetch ảnh Q1 blocking + Q2+ background trong `get_why_questions` **chỉ chạy ở local mode**, tức khi `DEVICE_API_URL` được đặt.)

`show_why_image` có 2 chế độ:
- **Local** (`DEVICE_API_URL` set): push ảnh qua `{DEVICE_API_URL}/api/display_image` trực tiếp qua LAN. `combined_server.py` khởi động thêm local HTTP server trên `IMAGE_CACHE_PORT` (default `8765`) để cache ảnh từ wsrv.nl (~0.3s vs ~2-3s).
- **Cloud** (không có `DEVICE_API_URL`): `show_why_image` POST **URL gốc** (Wikimedia…) đến `/api/internal/set_image`; app tự tải ảnh trực tiếp + convert **baseline JPEG rộng 320px** bằng Pillow (`_fetch_and_process_image`, retry 3 lần khi 429/5xx, User-Agent theo policy Wikimedia), lưu in-memory (tối đa 20 ảnh) và trả URL `{PUBLIC_URL}/api/why_image/{id}.jpg`. wsrv.nl chỉ còn là **fallback** khi tải/convert lỗi. Firmware ESP32 polls `GET /api/image_queue` (long-poll 3s) khi phát hiện `% show_why_image` trong TTS stream. `hide_why_image` cloud mode: firmware tự xóa ảnh, không cần LLM gọi API.

> Cloud mode cần **Pillow** (đã có trong `requirements.txt`); thiếu Pillow không làm sập app, chỉ rơi về wsrv.nl. Baseline (non-progressive) JPEG là bắt buộc — decoder của ESP32 không đọc được progressive JPEG.

`prepare_media_download` là MCP tool proxy đến `MEDIA_API_BASE_URL/api/media/prepare-download` (default `http://127.0.0.1:7860`) — không truy cập DB trực tiếp.

### Cửa hàng nội dung mở rộng (`tools.products` / `entitlements` / `orders`) — ĐANG LÀM

Bán nội dung mở rộng theo từng thiết bị (vd mua thêm chủ đề why_questions). **Định danh khách = `endpoint_key`** (vd `api.xiaozhi.me/agent_1886350`) lấy từ JWT trong wss URL qua `db.endpoint_key_for()` — bền vững khi broker cấp lại token.

**Cách tiêm định danh (đã làm).** Vì `combined_server.py` là subprocess **dùng chung mọi thiết bị**, tool không tự biết ai gọi. Cơ chế trong `app/mcp_outbound.py`:
- Tool nào cần định danh thì **khai báo param `endpoint_key`** (default `""`) trong signature.
- `_tool_wants_injection()` phát hiện param đó trong `inputSchema`; `_dispatch_tool_call(..., url)` tiêm `endpoint_key = db.endpoint_key_for(url)` vào `arguments` (worker biết `url` của chính nó).
- `build_tools_payload()` → `_strip_injected()` **xoá `endpoint_key` khỏi `properties` + `required`** trước khi gửi `tools/list`, nên LLM không thấy và không bịa được. `GET /api/tools` dùng chung hàm này để UI không lệch với những gì LLM thấy.
- Thêm tool cần định danh về sau: chỉ cần thêm param `endpoint_key`, **không phải sửa `mcp_outbound.py`**.
- `endpoint_key` rỗng (gọi qua `POST /api/tools/run`, hoặc wss không phải JWT) → coi như **chưa mua gì** (chỉ nội dung free). Deny-by-default là chủ ý.

Schema (migration `006`, xem "Migrations"): `products(product_code, tool, kind, ref, price_vnd, is_free, ...)` — `kind`+`ref` là cặp tổng quát để tool tự lọc (vd `kind='why_category', ref='vật lý'` → lọc `why_questions.category`); tool mới chỉ cần thêm dòng `products`, không đổi schema. `entitlements(endpoint_key, product_code, expires_at)` = quyền sở hữu. `orders` = đơn MoMo (Giai đoạn 2). Seed: `why:vũ trụ` free, còn `why:vật lý`/`sinh học`/`hóa học` phải mua.

**Quy tắc khoá nội dung** (`_locked_products()` trong `combined_server.py`): `tools.products` là **danh sách những thứ BỊ KHOÁ**, không phải whitelist. Một chủ đề bị ẩn ⟺ có dòng `products` khớp (`kind`, `ref`) với `is_active AND NOT is_free` **và** không có `entitlements` còn hiệu lực (`expires_at` NULL hoặc tương lai) cho `endpoint_key` đó. Category **không có** dòng `products` nào → mặc định mở. Chưa chạy migration 006 (`UndefinedTableError`) → log warning và không khoá gì, tính năng chạy như cũ.

**Trạng thái hiện tại (đã kiểm tra bằng test thật, 2026-07-26):**
- ✅ Migration 006 đã chạy trên Neon: `products` (4 dòng seed), `entitlements` (0 dòng), `orders` (0 dòng).
- ✅ Tiêm `endpoint_key` + ẩn khỏi `tools/list` (xem trên).
- ✅ Enforce trong `get_why_questions(count, endpoint_key)`: query thêm `WHERE category IS NULL OR category <> ALL($locked)`. Khi **mọi** chủ đề đều bị khoá → trả `{"success": false, "error": "locked", "locked_products": [...], "INSTRUCTION": "…mời mua, KHÔNG bịa câu hỏi, KHÔNG google_search thay thế"}`.
- ❌ **CHƯA nối:** **không có cách nào cấp `entitlements` ngoài chạy SQL tay** (chưa có endpoint admin-grant, chưa có MoMo) → 3 chủ đề `vật lý`/`sinh học`/`hóa học` hiện **khoá với mọi thiết bị**, chỉ `vũ trụ` chạy. UI store vẫn đọc `/api/why/categories` nên chưa hiện giá/trạng thái đã mua (`buyTopic()` vẫn là `alert` TODO). Bookmark sử ký vẫn dùng `user_id` default `"default"`, chưa theo `endpoint_key`. Checkout + IPN MoMo chưa có dòng code nào.

### Tài khoản & đăng nhập (`app/auth.py`) — ĐANG LÀM

Hệ tài khoản **riêng của server này**, hoàn toàn trong schema `tools` (migration 007). Không liên quan `public.parents` của sản phẩm khác.

- `tools.accounts` — `account_id uuid`, `email` (unique theo `LOWER(email)`), `password_hash` (**bcrypt**), `full_name`, `phone`, `role` (`user`|`admin`), `is_active`, `last_login_at`.
- `tools.sessions` — `token_hash` (PK) là **sha256 của token**, không lưu token gốc (cùng pattern với `ack_token` trong `media.py`); `account_id` FK CASCADE, `expires_at`, `last_seen_at`, `user_agent`, `ip`.
- **Không dùng JWT.** Cookie `session` (httpOnly, `SameSite=Lax`, `Secure` theo môi trường) giữ token random 32 byte → không cần thêm secret ký; thu hồi = xoá dòng DB. `cleanup_expired_sessions()` chạy một lần lúc startup.
- Cookie `Secure` auto-bật khi có `SPACE_ID` hoặc `PUBLIC_URL` là https; local http phải để tắt (không thì browser bỏ cookie). Override bằng `SESSION_COOKIE_SECURE=1|0`. **Lưu ý HF:** mở trực tiếp `*.hf.space` thì ổn; nếu nhúng iframe cross-site thì `SameSite=Lax` sẽ chặn cookie.
- Chống dò mật khẩu: đếm số lần sai theo `(email, ip)` **trong RAM** (`LOGIN_MAX_FAILED`, `LOGIN_LOCKOUT_SECONDS`) → chỉ đúng khi chạy 1 process; scale nhiều worker phải chuyển sang DB/Redis. Email sai và mật khẩu sai trả **cùng một** thông báo 401 (không lộ email nào tồn tại).
- `require_account` chặn `/api/devices/*`; `require_admin` chặn `/adminctrl` + `/api/admin/devices|device`. Tài khoản mới luôn `role='user'` → admin đầu tiên phải cấp bằng `scripts/make_admin.py` (xem "Commands").
- Frontend: `/login` (`login.html`) hỗ trợ `?next=/duong-dan` — chỉ nhận đường dẫn nội bộ (regex `^/(?!/)`) để không thành open redirect. `index.html` có thanh tài khoản góc phải tabbar (`js/account.js`): chưa đăng nhập → link Đăng nhập; đã đăng nhập → tên + link Admin (nếu role admin) + Đăng xuất.

**Chưa có:** reset mật khẩu / verify email (repo không có env SMTP nào) → quên mật khẩu = sửa DB tay. `/api/mcp/subscriptions` **vẫn public và liệt kê thiết bị của mọi người** (wss đã mask) — giữ nguyên hành vi cũ vì trang khách đang dùng để hiện "Thiết Bị Đã Kết Nối"; cần chốt lại khi siết quyền. `/api/admin/media/*` + `/api/tools/run` vẫn chưa có auth.

### Thiết bị thuộc tài khoản (claim) & quyền theo account

Migration 008 cho quyền có **2 loại chủ**, kiểm tra thì tính cả hai:
1. **Theo tài khoản** — `entitlements.account_id`. Resolve `endpoint_key → user_subscriptions.account_id → quyền`. Mua đi theo người: đổi robot / broker cấp endpoint mới vẫn còn quyền.
2. **Theo thiết bị** — `entitlements.endpoint_key` (admin cấp tay cho máy chưa có chủ). Đây là hành vi trước 008.

`entitlements` giờ có `CHECK (account_id IS NOT NULL OR endpoint_key IS NOT NULL)` + 2 partial unique index (`account_id, product_code` và `endpoint_key, product_code`) thay cho PK cũ.

Cách thiết bị có chủ:
- **Đăng ký khi đang đăng nhập** — `/api/mcp/connect` đọc session và truyền `account_id` vào `db.save_subscription`. Dùng `COALESCE(EXCLUDED.account_id, ...)` nên đăng ký lại lúc **chưa** đăng nhập sẽ **không** xoá chủ cũ.
- **Nhận thiết bị cũ** — `POST /api/devices/claim {websocket_url}` (cần đăng nhập). Sở hữu wss = bằng chứng sở hữu robot. Thiết bị đã thuộc account khác → từ chối, không cướp quyền; claim lại chính mình → `already_mine: true`.

> ⚠️ **Logic quyền bị nhân đôi ở 2 nơi, sửa là phải sửa cả hai:** `_locked_products()` trong `servers/combined_server.py` (thứ thực sự khoá nội dung) và `_products_for_endpoint()` trong `app/main.py` (thứ UI hiện). Lệch nhau = UI báo mở nhưng robot vẫn khoá.

### Đại Việt Sử Ký (`tim_su_kien`, `ke_su_ky`, `tiep_tuc_su_ky`)

Tính năng "kể Đại Việt Sử Ký Toàn Thư" cho trẻ nghe, dùng **cùng Neon** với why_questions (schema `tools`, tái dùng `_get_why_pool()` trong `combined_server.py` — không tạo pool riêng). Nguồn: bản dịch điện tử 2001 (mộc bản Nội Các Quan Bản 1697); **sử liệu chỉ tới năm 1675** — không có Quang Trung / Tây Sơn / nhà Nguyễn (nếu hỏi sẽ "không tìm thấy", đó là đúng).

Hai bảng — tạo bằng `python scripts/run_migration.py scripts/migrate_005_create_su_ky.sql` (xem "Migrations"):
- `tools.su_ky_events` — mỗi dòng là 1 đoạn ~900 ký tự đã cắt sẵn cho TTS, cột `ordinal` là thứ tự đọc tuần tự toàn bộ sách (`id, ordinal, part_index, ky, quyen, to_moc_ban, can_chi, nam, nien_hieu, label, content, char_count, shown_count`). Unique index trên `MD5(content)` để build lại không trùng; GIN `pg_trgm` trên `content` cho search nhanh.
- `tools.su_ky_bookmark` — `user_id, last_ordinal` — nhớ chỗ đang đọc theo từng user.

Ba tool:
- `tim_su_kien(keyword)` — tra cứu, trả danh sách đoạn khớp (không đọc ngay), như `search_stories`.
- `ke_su_ky(keyword?, nam?, user_id?)` — bắt đầu kể: nhảy tới điểm (từ khóa / năm / từ đầu sách nếu để trống), đọc 1 đoạn, đặt bookmark.
- `tiep_tuc_su_ky(user_id?)` — kể tiếp đoạn kế tiếp theo bookmark; trả `has_next=false` khi hết sách.

Vì tool call qua outbound-MCP **không mang định danh thiết bị** (chỉ có `name` + `arguments`), `user_id` là tham số optional default `"default"` (robot 1 nhà nhớ chung chỗ đang kể). `ke_su_ky`/`tiep_tuc_su_ky` upsert `su_ky_bookmark` và tăng `shown_count`.

Có bảng alias tên hiện đại → dạng cổ trong `combined_server.py` (`_SU_KY_ALIASES`), vì văn bản 1697 gọi "Trưng Nữ Vương"/"Hưng Đạo"/"Lam Sơn" chứ không dùng "Hai Bà Trưng"/"Trần Hưng Đạo"/"Lê Lợi". Ví dụ: `Hai Bà Trưng → Trưng Nữ Vương`, `Lê Lợi → Lam Sơn` (khởi nghĩa), `Bà Triệu → Triệu Ẩu`.

**Build DB** (chạy 1 lần, cần `PyMuPDF` — chỉ là dependency của script build, **KHÔNG cần trên server**):
```powershell
pip install PyMuPDF
python scripts/parse_dvsktt.py --dry-run --out sample.txt   # parse + thống kê, KHÔNG đụng DB
python scripts/parse_dvsktt.py                              # insert Neon (ON CONFLICT DO NOTHING)
python scripts/parse_dvsktt.py --rebuild                    # TRUNCATE rồi insert lại (khi sửa parser)
```
Parser lọc theo cỡ font (chỉ giữ body size ~10) để loại chú thích cuối trang + số ref; cắt mục theo neo năm-số-trong-ngoặc-vuông `[\d{2,4}]` (Bản Kỷ có dạng `Can-Chi, [niên hiệu] năm thứ N [năm]`); segment không có mốc năm (Hồng Bàng/Hùng Vương) fallback chunk theo kích thước; mục dài cắt nhỏ ~900 ký tự theo ranh giới câu. Hiện có ~2415 đoạn (năm 39→1675).

### Outbound MCP (`app/mcp_outbound.py`)

Hệ thống đóng vai trò **MCP server** khi kết nối ra ngoài tới broker (e.g. Xiaozhi ESP32) qua WebSocket JSON-RPC 2.0. Worker tự reconnect sau 1 giây. Quản lý qua:
- `POST /api/mcp/connect` — tạo background task `mcp_outbound_worker`
- `POST /api/mcp/disconnect` — cancel task
- `GET /api/mcp/status` — xem trạng thái kết nối (in-memory `outbound_connections`)
- `GET /api/mcp/subscriptions` — list thiết bị đã đăng ký (từ Neon), wss được mask token qua `_mask_wss`, kèm trạng thái kết nối hiện tại theo `endpoint_key`

Tool call từ broker được dispatch qua `asyncio.create_task` để không block vòng recv chính.

**Subscriptions (tự động kết nối lại):** khi `/api/mcp/connect` thành công, `device_name` + `wss_url` được lưu vào `tools.user_subscriptions` trên **Neon** (`db.save_subscription`); lúc startup, `_restore_subscriptions()` trong `app/main.py` đọc bảng này và tự khởi động lại worker cho từng wss — khách không phải đăng ký lại sau khi rebuild/update server. Hàm này chạy trong `asyncio.create_task` (**không block lifespan startup**), nên `/health` trả `ok` trước khi các broker kịp `connected`. `/api/mcp/disconnect` xóa dòng tương ứng. Chống trùng theo `endpoint_key` (`db.endpoint_key_for`): decode JWT trong query param `token` lấy `endpointId` — cùng thiết bị đăng ký lại với token cấp mới sẽ thay thế dòng cũ và worker cũ bị cancel; wss không phải JWT thì dedup theo cả chuỗi. Migrations: `migrate_003_create_user_subscriptions.sql`, `migrate_004_add_endpoint_key.sql`.

### Database (`app/db.py`)

PostgreSQL qua asyncpg. DB là **optional** — nếu không kết nối được, app vẫn chạy với `session_id` ngẫu nhiên (uuid4). Bảng: `users` (uuid, full_name, age, preferences jsonb, weak_points), `chat_sessions`, `chat_history`.

**Chỉ 1 DB (`app/state.py`):** DB chính (users/chat/media) **dùng chung một Neon** với why_questions/subscriptions. Mỗi biến `DB_*` fallback sang `WHY_DB_*` tương ứng. **KHÔNG hardcode credential** — host/user/password/name PHẢI cung cấp qua `.env` (local, load bằng `python-dotenv` trong `state.py`) hoặc **HF Secrets** (deploy); chỉ `WHY_DB_PORT` giữ default `5432` (không phải bí mật). Thiếu env → DSN không hợp lệ → pool không tạo được → app vẫn chạy nhưng DB tắt (session_id ngẫu nhiên). Pool tạo trong `app/main.py` với `min_size=1, max_size=5` và `ssl` theo `DB_SSL` (default `require`; đặt `DB_SSL=disable` cho Postgres local không bật SSL).

> **Deploy HF BẮT BUỘC set Secrets** `WHY_DB_HOST/PORT/NAME/USER/PASSWORD` (và/hoặc `DB_*`). Không còn default Neon trong code nên thiếu secret = DB không kết nối. Các script standalone (`scripts/*.py`) tự `load_dotenv()` từ `.env` ở gốc repo; `combined_server.py` (subprocess) nhận env qua `os.environ.copy()` của app, và cũng tự `load_dotenv()` khi chạy standalone.

### Migrations (tạo bảng trên Neon)

Bảng của **tools** (`why_questions`, `user_subscriptions`, `su_ky_events`, `su_ky_bookmark`, `products`/`entitlements`/`orders`, `accounts`/`sessions`) nằm trong schema `tools` trên Neon và **không được app tự tạo lúc startup** — phải chạy migration thủ công một lần.

> **Chỉ làm việc trong schema `tools`.** Schema `public` trên cùng Neon (36 bảng: `users`, `parents`, `lessons`, `live_wallet`… + `alembic_version`) thuộc **một sản phẩm khác**, do Alembic của app đó quản lý. Repo này **không đọc, không ghi, không `ALTER`** bên đó — kể cả khi thấy bảng nghe có vẻ liên quan (`parents` có sẵn email/password_hash nhưng **không** phải hệ tài khoản của server này). Ngoại lệ lịch sử: `db.get_user_profile/create_chat_session/save_chat_history` vẫn trỏ `users`/`chat_sessions`/`chat_history` không prefix schema — đó là code cũ của path Gemini dormant, đừng mở rộng thêm.

Migration là file SQL thuần trong `scripts/`, đặt tên `migrate_<số>_<mô tả>.sql`, chạy theo thứ tự số:

| File | Tạo ra |
|------|--------|
| `migrate_001_create_why_questions.sql` | `tools.why_questions` |
| `migrate_002_add_unique_question.sql` | unique index `MD5(question)` |
| `migrate_003_create_user_subscriptions.sql` | `tools.user_subscriptions` |
| `migrate_004_add_endpoint_key.sql` | cột + index `endpoint_key` |
| `migrate_005_create_su_ky.sql` | `tools.su_ky_events`, `tools.su_ky_bookmark`, extension `pg_trgm` |
| `migrate_006_create_store.sql` | `tools.products`, `tools.entitlements`, `tools.orders` + seed 4 chủ đề why |
| `migrate_007_create_accounts.sql` | `tools.accounts`, `tools.sessions` |
| `migrate_008_link_account.sql` | `account_id` trên `user_subscriptions` + `entitlements`; bỏ PK cũ của `entitlements`, thêm CHECK có chủ + 2 partial unique index |

**Cách chạy — `scripts/run_migration.py`** (dùng `asyncpg`, **không cần cài psql**; máy dev Windows thường không có psql):
```powershell
python scripts/run_migration.py                 # tất cả migrate_*.sql, theo thứ tự tên
python scripts/run_migration.py scripts/migrate_005_create_su_ky.sql   # một file cụ thể
python scripts/run_migration.py --dry-run       # chỉ liệt kê, không đụng DB
python scripts/run_migration.py --ignore-errors # statement lỗi thì log rồi chạy tiếp
```
Runner tách file theo `;` rồi execute từng statement (các migration chỉ là DDL đơn giản, không có DO block). Kết nối bằng đúng bộ env `WHY_DB_*` như `build_why_db.py` / `parse_dvsktt.py`.

Nếu có sẵn psql thì tương đương: `psql "<NEON_CONNECTION_STRING>" -f scripts/migrate_005_create_su_ky.sql`.

**Idempotent:** mọi DDL đều `CREATE ... IF NOT EXISTS` → chạy lại nhiều lần vô hại; migration mới chỉ cần thêm file rồi chạy lại runner.

**Lưu ý `pg_trgm`:** `migrate_005` có `CREATE EXTENSION IF NOT EXISTS pg_trgm` (cho GIN index tăng tốc `tim_su_kien`). Nếu Neon từ chối tạo extension, dùng `--ignore-errors` — bảng vẫn được tạo và `tim_su_kien` vẫn chạy bằng `ILIKE`, chỉ chậm hơn.

### Audio (`app/audio.py`)

- STT: `speech_recognition` → Google Speech API, chạy sync trong thread executor.
- TTS: `edge_tts` async stream, giọng `vi-VN-HoaiMyNeural`. Retry 2 lần khi lỗi.

### Media System (`app/media.py`)

Upload/download pipeline cho phép admin tải media lên Cloudflare R2 và ESP32 lấy file về SD card. **Yêu cầu PostgreSQL và ffmpeg/ffprobe có trong PATH.**

Flow:
1. Admin upload qua `POST /api/admin/media/upload` → ffprobe xác thực nội dung thực sự khớp extension → ffmpeg normalize (image→PNG 240×320, audio→MP3 128k, video→MJPEG 320×240 15fps PCM 16kHz) → upload lên R2, ghi metadata vào DB.
2. ESP32 gọi `POST /api/media/prepare-download` với query text → server tìm fuzzy trong `search_title`, tạo signed URL (TTL 1h mặc định), tạo transfer ticket kèm `ack_token`, trả về arguments cho `self.sdcard.download_file`.
3. Sau khi tải xong, ESP32 gọi `POST /api/media/transfers/{transfer_id}/ack` với token + SHA-256 + bytes_written → server verify HMAC token, kích thước, hash → xóa R2 object → đánh status `consumed`.
4. Background task `_cleanup_loop` chạy mỗi `CLEANUP_INTERVAL_SECONDS` xóa các file đã hết TTL.

Media files có TTL 24h mặc định; đã `consumed` hoặc `expired` không còn trên R2. Idempotent ACK: nếu transfer đã `success` thì trả `idempotent: true` không lỗi.

Lưu ý: các API admin media **không có xác thực** (và cả `/adminctrl` + `/api/admin/devices|device`) — chỉ deploy ở môi trường chấp nhận rủi ro này. Trang admin không bao giờ trả wss đầy đủ (token là credential) — luôn mask qua `_mask_wss`; nhưng `endpoint_key` thì hiện nguyên, và nhóm endpoint này hiện là read-only nên chưa cho phép cấp/thu quyền. Khi test với ESP32 trong LAN, đặt `MEDIA_PUBLIC_BASE_URL=http://<IP-LAN-của-laptop>:7860` (không dùng `127.0.0.1` — trên ESP nó trỏ về chính ESP) và mở port 7860 trên firewall Windows.

### HTTP API (ngoài WebSocket)

- `GET /` — serve `static/index.html` (web UI frontend). `/static` được mount qua `StaticFiles` (`app/main.py`). Frontend tách file: `static/css/*.css` (11 file theo khu vực UI) + `static/js/*.js` — thứ tự nạp: `utils`, `tools`, `tool-test`, `media`, `mcp`, `store`, `tabs`, `account`, `main`. UI có 2 tab (`tabs.js` + `switchTab()`): `🔧 Đăng ký tools` và `🛒 Mua thêm nội dung`. **Script là classic `<script defer>`, KHÔNG phải ES module** — markup dùng inline `onclick=` nên các hàm phải ở global scope; `main.js` phải nạp cuối. Thứ tự `<link>` CSS cũng không được đổi (`right-panel.css`/`media.css` chứa rule override `.tool-card`).
- `GET /login` — serve `static/login.html` (form đăng nhập/đăng ký, assets `css/auth.css` + `js/auth.js`).
- `POST /api/auth/register` / `login` / `logout`, `GET /api/auth/me` — xem "Tài khoản & đăng nhập". `/me` trả `{"authenticated": false}` khi chưa đăng nhập (không 401) để frontend gọi thoải mái.
- `GET /api/devices/mine` — thiết bị của tài khoản đang đăng nhập + trạng thái mở khoá từng chủ đề (cần đăng nhập, 401 nếu chưa).
- `POST /api/devices/claim` — nhận thiết bị đã đăng ký về tài khoản (body `{websocket_url}`).
- `GET /adminctrl` — serve `static/admin.html` (trang admin, **chỉ đọc**, cần role admin — chưa đủ quyền thì **302 về `/login?next=/adminctrl`**): cột trái danh sách thiết bị đã đăng ký + trạng thái kết nối, bấm vào → cột phải hiện tools thiết bị đang được cấp, chức năng đã/chưa mở khoá, và lịch sử thanh toán. Assets riêng (`css/admin.css`, `js/admin.js` + dùng chung `utils.js`) — **không** nằm trong chuỗi script của `index.html`.
- `GET /api/admin/devices` — list thiết bị (từ `tools.user_subscriptions`) kèm `endpoint_key`, `owner_email`, status runtime, `unlocked_count`/`purchased_count`/`product_count`.
- `GET /api/admin/device?endpoint_key=...` — chi tiết 1 thiết bị: `device`, `tools` (kèm `unlocked_refs`/`locked_refs` theo `products.tool`), `products` (trạng thái sở hữu), `orders` (20 đơn gần nhất). `endpoint_key` chứa dấu `/` nên truyền qua **query param**, không phải path param. `store_ready=false` khi chưa chạy migration 006.
- `GET /health` — health check cho UptimeRobot/Render, không phụ thuộc DB/MCP.
- `GET /api/tools` — list tools đã đăng ký.
- `POST /api/tools/run` — gọi tool trực tiếp (dùng `mcp_outbound.call_tool_by_name`).
- `POST /api/mcp/probe` — probe broker WebSocket để lấy danh sách tools mà không connect thường trực.
- `POST /api/internal/push_image` — internal: gọi `self.screen.preview_image` trên device qua broker WebSocket (MCP client tạm thời).
- `POST /api/internal/set_image` — internal: `show_why_image` (cloud mode) gửi URL gốc; server tải + convert baseline JPEG 320px (Pillow) rồi đẩy URL `/api/why_image/...` vào queue `_pending_image_url` (fallback wsrv.nl nếu lỗi).
- `GET /api/image_queue` — firmware ESP32 long-poll (tối đa 3s), nhận URL ảnh một lần rồi queue xóa.
- `GET /api/why_image/{image_id}.jpg` — serve ảnh đã convert từ in-memory store (LRU 20 ảnh, `Cache-Control: max-age=3600`).
- `GET /api/why/categories` — thống kê chủ đề `tools.why_questions` (`total`, `with_image`) cho tab "Mua thêm nội dung".
- `POST /api/admin/media/upload` — upload và normalize media lên R2 (yêu cầu DB + R2).
- `GET /api/admin/media` — list toàn bộ media files.
- `DELETE /api/admin/media/{media_id}` — xóa media khỏi DB và R2.
- `POST /api/media/prepare-download` — tạo signed URL + transfer ticket cho ESP32.
- `POST /api/media/transfers/{transfer_id}/ack` — ESP32 xác nhận tải thành công.

### Key env vars (`.env`)

| Var | Mục đích |
|-----|----------|
| `GEMINI_API_KEY` | Google Gemini API |
| `SEARXNG_URL` | URL của SearXNG (local: `http://localhost:8080`, deploy: `https://ai-robot-searxng.onrender.com`) |
| `SMARTLIGHT_API_URL` | Smart light API (optional, default `http://localhost:5067`) |
| `DEVICE_API_URL` | IP thiết bị ESP32 trên LAN để push audio + hiển thị ảnh, e.g. `http://192.168.1.100` (optional) |
| `DEVICE_PLAY_DELAY` | Giây chờ trước khi push audio đến thiết bị để TTS phát xong (default `4`) |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | PostgreSQL chính cho user/session/chat (fallback sang `WHY_DB_*`; KHÔNG hardcode — xem "Chỉ 1 DB") |
| `DB_SSL` | SSL mode cho pool DB chính (default `require`; đặt `disable` cho Postgres local) |
| `SESSION_DAYS` | Hạn session đăng nhập (default `30`) |
| `SESSION_COOKIE_SECURE` | `1`/`0` — ép cờ `Secure` của cookie session; bỏ trống = auto theo `SPACE_ID`/`PUBLIC_URL` |
| `LOGIN_MAX_FAILED`, `LOGIN_LOCKOUT_SECONDS` | Ngưỡng khoá tạm khi đăng nhập sai (default `8` lần / `900` giây) |
| `WHY_DB_HOST`, `WHY_DB_PORT`, `WHY_DB_NAME`, `WHY_DB_USER`, `WHY_DB_PASSWORD` | Neon PostgreSQL cho schema `tools` (why_questions/su_ky/subscriptions). BẮT BUỘC set qua `.env`/HF Secrets — chỉ `WHY_DB_PORT` default `5432`, ssl=require |
| `PUBLIC_URL` | URL công khai của server để firmware ESP32 poll `/api/image_queue` (cloud mode). Auto-derive từ `SPACE_ID` nếu chạy trên HuggingFace Spaces; fallback là `MEDIA_API_BASE_URL` |
| `WHY_TTS_SPEED` | Ước tính tốc độ đọc TTS (ký tự/giây) — dùng tính delay ảnh (default `15`) |
| `WHY_DOWNLOAD_LEAD` | Giây cần download + decode ảnh từ wsrv.nl trước khi hiển thị (default `3`) |
| `IMAGE_CACHE_PORT` | Port HTTP server serve ảnh đã cache cho ESP32 tải từ LAN (default `8765`) |
| `MEDIA_API_BASE_URL` | Base URL của server chính để `prepare_media_download` proxy đến (default `http://127.0.0.1:7860`) |
| `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT_URL` | Cloudflare R2 — bắt buộc cho media system |
| `R2_REGION` | R2 region (default `auto`) |
| `MEDIA_PUBLIC_BASE_URL` | Base URL công khai của server, dùng để tạo `ack_url` trong prepare-download (bắt buộc nếu dùng media) |
| `MEDIA_TTL_HOURS` | Thời gian giữ file trên R2 trước khi cleanup (default `24`) |
| `MEDIA_SIGNED_URL_TTL_SECONDS` | TTL của presigned URL trả cho ESP32 (default `3600`) |
| `MEDIA_TRANSFER_TTL_SECONDS` | TTL của transfer ticket (default `3600`) |
| `MEDIA_CLEANUP_INTERVAL_SECONDS` | Khoảng thời gian giữa các lần cleanup R2 (default `3600`) |

### Ports

- `7860` — FastAPI main app (override với env `PORT`)
- `5434` — PostgreSQL chính (mapped từ 5432 trong Docker container)
- `5433` — PostgreSQL why_questions local (chỉ dùng khi override `WHY_DB_*` vars; default hiện tại là Neon cloud)
- `8080` — SearXNG
- `8765` — Image cache HTTP server (chỉ khởi động khi `DEVICE_API_URL` được đặt)

### Deploy

Cùng một `Dockerfile` phục vụ 2 target (`CMD uvicorn app.main:app --port ${PORT:-7860}`, cài `ffmpeg`, chạy non-root UID 1000 theo yêu cầu HF Spaces):

- **HuggingFace Spaces** — target chính hiện tại. Config nằm trong frontmatter của `README.md` (`sdk: docker`, `app_port: 7860`). Credential đặt ở **Space Secrets** (xem "Chỉ 1 DB": bắt buộc `WHY_DB_*`). `PUBLIC_URL` tự suy ra từ `SPACE_ID`.
- **Render** — `render.yaml` khai báo 2 services: `ai-robot-searxng` (Docker, `Dockerfile.searxng`, port 8080) và `ai-robot-mcp-tools-server-dev` (Docker, healthcheck `/health`). Lưu ý `render.yaml` chỉ khai báo `GEMINI_API_KEY`/`DB_*`/`SMARTLIGHT_API_URL` — **chưa có `WHY_DB_*`**, nên deploy Render sẽ mất why_questions/su_ky/subscriptions cho tới khi thêm.

Cả hai đều free tier → `combined_server.py` gộp tools vào 1 subprocess để tiết kiệm RAM.
