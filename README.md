# 💛 Locket Tqd

Web client đẹp lung linh cho **Locket Camera**, khai thác full SDK [locketlam](https://github.com/leanhminh2104/locketlam).

## Tính năng

- Đăng nhập / Session persistence
- Feed moments từ bạn bè + thả reaction
- Danh sách bạn bè + tìm & gửi lời mời theo username
- Đăng ảnh / video moment (caption, private)
- Chat conversations
- Hồ sơ cá nhân
- UI glassmorphism + animation mượt, mobile-first

## Cài đặt

```bash
# 1. Cài dependencies
pip install locketlam flask flask-cors

# 2. Chạy server
cd /path/to/this/folder
python server.py
```

Mở trình duyệt: **http://127.0.0.1:5000**

## Cấu trúc

```
.
├── server.py          # Flask backend (wrap full locketlam API)
├── static/
│   └── index.html     # Frontend animation đẹp
├── sessions/          # Session JSON (auto tạo)
└── uploads/           # Temp media upload (auto tạo)
```

## API endpoints chính

| Method | Path | Mô tả |
|--------|------|-------|
| POST   | `/api/login` | Đăng nhập |
| POST   | `/api/logout` | Đăng xuất |
| GET    | `/api/status` | Kiểm tra auth |
| GET    | `/api/profile` | Hồ sơ |
| GET    | `/api/friends` | Danh sách bạn |
| GET    | `/api/feed` | Feed moments |
| POST   | `/api/moments/post` | Đăng moment |
| POST   | `/api/moments/react` | Reaction |
| GET    | `/api/chat/conversations` | Inbox |

## Powered by

- [locketlam](https://github.com/leanhminh2104/locketlam) — Unofficial Locket Camera Python SDK
- Flask + modern CSS (glassmorphism, orbs animation)

## Disclaimer

Unofficial client. Sử dụng có trách nhiệm, tuân thủ ToS của Locket.
