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
| POST | `/api/profile/avatar` | Đổi ảnh đại diện (multipart `file`) |
| GET | `/api/feed` | Feed khoảnh khắc mới nhất |
| GET | `/api/my-moments` | Khoảnh khắc của tôi |
| GET | `/api/users/{username}/moments` | Khoảnh khắc của một người dùng |
| POST | `/api/post` | Đăng bài (multipart: `image`/`video`, `caption`, `note_type`, `icon`, `colors`, `text_color`, `is_private`) |
| POST | `/api/react` | Thả cảm xúc `{moment_uid, reaction}` |
| POST | `/api/comment` | Bình luận `{moment_uid, receiver_uid, text}` |
| GET | `/api/moments/{id}/views` | Lượt xem và cảm xúc của một bài |
| DELETE | `/api/moments/{id}` | Xoá bài của mình |
| GET | `/api/presets` | 158 kiểu nhãn chú thích |
| GET | `/api/friends` | Danh sách bạn bè |
| GET | `/api/friend-requests` | Lời mời kết bạn |
| POST | `/api/friends/request` | Gửi lời mời `{username}` hoặc `{user_uid}` |
| POST | `/api/friends/accept` | Đồng ý lời mời `{user_uid}` |
| POST | `/api/friends/remove` | Huỷ kết bạn `{user_uid}` |
| GET | `/api/conversations` | Danh sách cuộc trò chuyện |
| GET | `/api/messages?other_user_id=` | Tin nhắn với một người |
| POST | `/api/messages/send` | Gửi tin nhắn `{receiver_uid, text}` |

## Lưu ý

- Đây là dự án học tập dùng API không chính thức của Locket, không liên kết với
  Locket Camera, Inc. Hãy dùng bằng tài khoản của chính bạn và có trách nhiệm.
- File phiên đăng nhập nằm ở `backend/data/locket_session.json` chứa token truy cập —
  **không chia sẻ file này cho bất kỳ ai**.
- Máy chủ mặc định phục vụ một phiên đăng nhập tại một thời điểm (một người dùng).
