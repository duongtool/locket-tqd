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

## Deploy lên Render.com (khuyến nghị)

1. Vào [render.com](https://render.com) → **New +** → **Web Service**
2. Connect GitHub repo: `duongtool/locket-tqd`
3. Cấu hình:
   - **Name:** `locket-tqd` (hoặc tên bạn muốn)
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn server:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
   - **Instance Type:** Free
4. (Tùy chọn) Environment Variables:
   - `SECRET_KEY` = chuỗi bí mật ngẫu nhiên dài
5. Click **Create Web Service** → đợi build xong, mở URL Render

> Free tier có thể sleep sau 15 phút không request. Request đầu tiên sẽ chậm ~30s.

## Chạy local

```bash
git clone https://github.com/duongtool/locket-tqd.git
cd locket-tqd
pip install -r requirements.txt
python server.py
```

Mở: **http://127.0.0.1:5000**

## Cấu trúc

```
.
├── server.py          # Flask + gunicorn ready
├── static/index.html  # Frontend
├── Procfile           # Render / Heroku
├── requirements.txt
├── runtime.txt
└── README.md
```

## Powered by

- [locketlam](https://github.com/leanhminh2104/locketlam) — Unofficial Locket Camera Python SDK
- Flask + gunicorn + modern CSS

## Disclaimer

Unofficial client. Sử dụng có trách nhiệm, tuân thủ ToS của Locket.
