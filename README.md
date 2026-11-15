# Locket Tqd

Ứng dụng web Locket chạy **thật qua API của Locket Camera**, gồm backend và frontend
viết lại dựa trên thư viện mã nguồn mở [`locketlam`](https://github.com/leanhminh2104/locketlam)
(đã đóng gói kèm trong thư mục `locketlam/` của dự án này, giấy phép MIT — xem `LICENSE-locketlam.txt`).

Giao diện mô phỏng ứng dụng Locket: nền tối, điểm nhấn vàng, thẻ ảnh bo tròn lớn,
nhãn chú thích dạng viên thuốc có dải màu gradient, nút chụp tròn ở màn hình đăng bài.

## Tính năng

- Đăng nhập bằng tài khoản Locket thật (email + mật khẩu), phiên đăng nhập được lưu
  và tự làm mới token — đăng nhập một lần, dùng mãi tới khi đăng xuất.
- Feed khoảnh khắc mới nhất của bạn bè, xem ảnh/video, thả cảm xúc ❤️ 🔥 🥰 🥳 🥺, bình luận.
- Đăng ảnh hoặc video kèm chú thích, chọn trong 158 kiểu nhãn preset gốc của Locket
  hoặc tự phối dải màu gradient + màu chữ; video tự nén HEVC chuẩn Apple dưới 6 MB.
- Bạn bè: xem danh sách, kết bạn bằng username, đồng ý lời mời, huỷ kết bạn.
- Tin nhắn: xem các cuộc trò chuyện và gửi tin nhắn văn bản.
- Trang cá nhân: xem và sửa tên, đổi ảnh đại diện, xem lưới khoảnh khắc của mình, xoá bài.

## Cách chạy

```bash
cd locket-tqd
./run.sh
```

Lần đầu chạy sẽ tự tạo môi trường ảo `.venv` và cài thư viện. Sau đó mở
<http://localhost:8000> trên trình duyệt và đăng nhập bằng tài khoản Locket của bạn.

Chạy thủ công nếu muốn:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## Cấu trúc thư mục

```
locket-tqd/
├── backend/
│   ├── app.py            # Máy chủ FastAPI: toàn bộ endpoint /api/*
│   └── data/             # Phiên đăng nhập (tự sinh, đừng chia sẻ thư mục này)
├── frontend/
│   ├── index.html        # Giao diện
│   ├── style.css         # Phong cách Locket: tối + vàng, thẻ bo tròn
│   └── app.js            # Logic gọi API
├── locketlam/            # Thư viện gọi API Locket thật (đóng gói kèm)
├── requirements.txt
└── run.sh
```

## API của backend

| Method | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/api/login` | Đăng nhập `{email, password}` |
| POST | `/api/logout` | Đăng xuất, xoá phiên |
| GET | `/api/status` | Trạng thái đăng nhập |
| GET | `/api/me` | Hồ sơ của tôi |
| POST | `/api/profile/name` | Đổi họ tên |
| POST | `/api/profile/birthdate` | Đổi ngày sinh `{birthdate}` (YYYY-MM-DD) |
| POST | `/api/profile/avatar` | Đổi ảnh đại diện (multipart `file`) |
| GET | `/api/users/by-username/{username}` | Tra hồ sơ theo username |
| GET | `/api/users/by-uid/{uid}` | Tra hồ sơ theo UID |
| GET | `/api/users/by-uid/{uid}/moments` | Khoảnh khắc của một người theo UID |
| GET | `/api/device` | Thông tin thiết bị giả lập hiện tại |
| POST | `/api/device/auto` | Đổi thiết bị giả lập tự động `{auto_emulate}` |
| POST | `/api/session/refresh` | Làm mới token phiên đăng nhập |
| POST | `/api/session/sync` | Đồng bộ cài đặt + token thông báo với Locket |
| GET | `/api/feed` | Feed khoảnh khắc mới nhất |
| GET | `/api/feed/full` | Toàn bộ khoảnh khắc (lịch sử của mọi bạn bè + bài của mình, đã khử trùng lặp) |
| GET | `/api/my-moments` | Khoảnh khắc của tôi (hỗ trợ `limit`, `start_date`, `end_date`) |
| GET | `/api/users/{username}/moments` | Khoảnh khắc của một người dùng |
| GET | `/api/filters` | Danh sách bộ lọc máy ảnh của Locket |
| GET | `/api/rollcall` | Bài đăng Rollcall tuần này (`week`, `year`) |
| POST | `/api/moments/viewed` | Đánh dấu đã xem `{moment_uid}` |
| POST | `/api/post` | Đăng bài (multipart: `image`/`video`, `caption`, `note_type`, `icon`, `colors`, `text_color`, `is_private`, `recipients` dạng JSON) |
| POST | `/api/react` | Thả cảm xúc `{moment_uid, reaction}` |
| POST | `/api/comment` | Bình luận `{moment_uid, receiver_uid, text}` |
| GET | `/api/moments/{id}/views` | Lượt xem và cảm xúc của một bài |
| DELETE | `/api/moments/{id}` | Xoá bài của mình |
| GET | `/api/presets` | 158 kiểu nhãn chú thích |
| GET | `/api/friends` | Danh sách bạn bè |
| GET | `/api/friend-requests` | Lời mời kết bạn |
| GET | `/api/groups` | Nhóm và bạn bè |
| POST | `/api/friends/request` | Gửi lời mời `{username}` hoặc `{user_uid}` |
| POST | `/api/friends/accept` | Đồng ý lời mời `{user_uid}` |
| POST | `/api/friends/remove` | Huỷ kết bạn `{user_uid}` |
| POST | `/api/friends/block` | Chặn người dùng `{user_uid}` |
| POST | `/api/friends/unblock` | Bỏ chặn `{user_uid}` |
| POST | `/api/friends/suggest` | Gợi ý bạn bè từ danh bạ `{phone_contacts: [...]}` |
| GET | `/api/invite/{username}` | Link mời công khai `locket.cam/<username>` + hồ sơ |
| GET | `/api/conversations` | Danh sách cuộc trò chuyện |
| GET | `/api/messages?other_user_id=` | Tin nhắn với một người |
| POST | `/api/messages/send` | Gửi tin nhắn `{receiver_uid, text}` |
| POST | `/api/messages/send-moment` | Chia sẻ khoảnh khắc vào chat `{receiver_uid, moment_uid, text?}` |
| GET | `/api/chat/reactions` | Bảng biểu cảm chính thức cho tin nhắn |
| POST | `/api/messages/reaction` | Thả cảm xúc vào tin nhắn `{conversation_id, message_id, emoji}` |
| POST | `/api/messages/reaction/remove` | Gỡ cảm xúc khỏi tin nhắn |
| POST | `/api/messages/delete` | Thu hồi tin nhắn `{conversation_uid, message_uid}` |
| POST | `/api/messages/read` | Đánh dấu đã đọc, hỗ trợ ẩn danh `{send_read_receipt: false}` |
| WS | `/api/chat/ws?other_user_id=` | Luồng tin nhắn thời gian thực (WebSocket) |

## Kiểm thử

Có bộ kiểm thử khói tự động chạy toàn bộ endpoint bằng client giả lập
(không cần tài khoản Locket thật):

```bash
.venv/bin/pip install httpx
.venv/bin/python tests/smoke_test.py
```

## Lưu ý

- Đây là dự án học tập dùng API không chính thức của Locket, không liên kết với
  Locket Camera, Inc. Hãy dùng bằng tài khoản của chính bạn và có trách nhiệm.
- File phiên đăng nhập nằm ở `backend/data/locket_session.json` chứa token truy cập —
  **không chia sẻ file này cho bất kỳ ai**.
- Máy chủ mặc định phục vụ một phiên đăng nhập tại một thời điểm (một người dùng).
