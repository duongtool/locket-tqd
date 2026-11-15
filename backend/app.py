"""
Locket Tqd - Backend
====================
Máy chủ API cho ứng dụng web Locket Tqd. Toàn bộ thao tác đều gọi thẳng
tới máy chủ Locket Camera thật thông qua thư viện `locketlam`
(đã đóng gói kèm trong thư mục gốc của dự án).

Chạy:
    uvicorn backend.app:app --host 0.0.0.0 --port 8000
hoặc dùng run.sh ở thư mục gốc.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

# Cho phép import gói locketlam đặt ở thư mục gốc của dự án
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from locketlam import LocketClient
from locketlam.exceptions import AuthenticationError, LocketAPIError, LocketError

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
SESSION_PATH = os.path.join(DATA_DIR, "locket_session.json")
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
PRESETS_PATH = os.path.join(PROJECT_ROOT, "locketlam", "caption_presets.json")

app = FastAPI(title="Locket Tqd API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Quản lý client Locket (một phiên đăng nhập duy nhất cho cả máy chủ)
# ---------------------------------------------------------------------------
_client: Optional[LocketClient] = None
_lock = threading.RLock()


def get_client() -> LocketClient:
    global _client
    with _lock:
        if _client is None:
            _client = LocketClient(session_path=SESSION_PATH)
        return _client


def reset_client() -> None:
    global _client
    with _lock:
        _client = None


def require_auth() -> LocketClient:
    client = get_client()
    if not client.is_authenticated():
        raise HTTPException(status_code=401, detail="Chưa đăng nhập Locket.")
    return client


def run_lib(fn):
    """Chạy một hàm của thư viện và dịch lỗi sang HTTP cho gọn."""
    with _lock:
        try:
            return fn()
        except AuthenticationError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except LocketAPIError as e:
            raise HTTPException(status_code=502, detail=f"Locket API: {e}")
        except LocketError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            raise
        except Exception as e:  # lỗi mạng, lỗi không lường trước
            raise HTTPException(status_code=500, detail=f"Lỗi máy chủ: {e}")


# ---------------------------------------------------------------------------
# Chuẩn hoá dữ liệu trả về cho frontend
# ---------------------------------------------------------------------------
def _ts_to_epoch(value: Any) -> Optional[int]:
    """Đưa mọi kiểu thời gian của Locket về epoch giây."""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("_seconds", "seconds", "$numberLong"):
            if key in value:
                try:
                    return int(value[key])
                except Exception:
                    pass
        if "_nanoseconds" in value and "seconds" in value:
            return int(value["seconds"])
        return None
    if isinstance(value, (int, float)):
        v = int(value)
        return v // 1000 if v > 10_000_000_000 else v
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception:
            return None
    return None


def _first(d: dict, *keys: str):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def normalize_user(u: Any) -> dict:
    if not isinstance(u, dict):
        return {"uid": str(u)}
    return {
        "uid": _first(u, "uid", "id", "user_uid", "localId"),
        "first_name": _first(u, "first_name", "firstName", "given_name") or "",
        "last_name": _first(u, "last_name", "lastName", "family_name") or "",
        "username": _first(u, "username", "locket_username", "handle"),
        "avatar_url": _first(
            u,
            "profile_picture_url",
            "profilePictureUrl",
            "avatar_url",
            "avatarUrl",
            "photo_url",
            "photoUrl",
            "profile_picture",
        ),
        "raw": u,
    }


def normalize_moment(m: Any) -> dict:
    if not isinstance(m, dict):
        return {"raw": m}
    epoch = _ts_to_epoch(_first(m, "date", "created_at", "createdAt", "timestamp"))
    caption = _first(m, "caption", "text") or ""
    overlays = m.get("overlays") or []
    if not caption and overlays and isinstance(overlays, list):
        for ov in overlays:
            if isinstance(ov, dict) and ov.get("alt_text"):
                caption = ov["alt_text"]
                break
    user = m.get("user")
    return {
        "id": _first(m, "canonical_uid", "id", "uid", "moment_uid"),
        "user_uid": user if isinstance(user, str) else _first(m, "user_uid", "owner_uid", "author_uid"),
        "user": normalize_user(user) if isinstance(user, dict) else None,
        "thumbnail_url": _first(m, "thumbnail_url", "thumbnailUrl", "image_url"),
        "video_url": _first(m, "video_url", "videoUrl"),
        "caption": caption,
        "overlays": overlays,
        "created_at": epoch,
        "created_at_iso": (
            datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat() if epoch else None
        ),
        "raw": m,
    }


# ---------------------------------------------------------------------------
# Hệ thống
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "app": "Locket Tqd", "time": int(time.time())}


@app.get("/api/status")
def status():
    client = get_client()
    auth = client.is_authenticated()
    return {
        "authenticated": auth,
        "uid": client.session.uid if auth else None,
        "email": client.session.email if auth else None,
    }


# ---------------------------------------------------------------------------
# Xác thực
# ---------------------------------------------------------------------------
@app.post("/api/login")
async def login(req: Request):
    body = await req.json()
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=422, detail="Thiếu email hoặc mật khẩu.")

    def _do():
        client = get_client()
        client.login(email, password)
        try:
            profile = client.user.get_profile()
        except Exception:
            profile = {}
        return {
            "uid": client.session.uid,
            "email": client.session.email,
            "profile": normalize_user(profile) if profile else None,
        }

    return run_lib(_do)


@app.post("/api/logout")
def logout():
    with _lock:
        try:
            if os.path.exists(SESSION_PATH):
                os.remove(SESSION_PATH)
        finally:
            reset_client()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Hồ sơ
# ---------------------------------------------------------------------------
@app.get("/api/me")
def me():
    client = require_auth()
    profile = run_lib(lambda: client.user.get_profile())
    return normalize_user(profile)


@app.get("/api/users/by-username/{username}")
def user_by_username(username: str):
    client = require_auth()
    profile = run_lib(lambda: client.user.get_profile_by_username(username))
    return normalize_user(profile)


@app.post("/api/profile/name")
async def update_name(req: Request):
    client = require_auth()
    body = await req.json()
    first = (body.get("first_name") or "").strip()
    last = (body.get("last_name") or "").strip()
    if not first and not last:
        raise HTTPException(status_code=422, detail="Thiếu họ tên.")
    return run_lib(lambda: client.user.update_name(first, last))


@app.post("/api/profile/avatar")
async def update_avatar(file: UploadFile = File(...)):
    client = require_auth()
    data = await file.read()
    suffix = os.path.splitext(file.filename or "avatar.png")[1] or ".png"
    fd, path = tempfile.mkstemp(suffix=suffix, dir=DATA_DIR)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return run_lib(lambda: client.user.update_avatar(path))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Khoảnh khắc (Moments)
# ---------------------------------------------------------------------------
@app.get("/api/feed")
def feed():
    client = require_auth()
    items = run_lib(lambda: client.moments.get_latest())
    return {"items": [normalize_moment(m) for m in (items or [])]}


@app.get("/api/my-moments")
def my_moments():
    client = require_auth()
    items = run_lib(lambda: client.moments.get_all_my_moments())
    return {"items": [normalize_moment(m) for m in (items or [])]}


@app.get("/api/users/{username}/moments")
def moments_by_username(username: str, limit: Optional[int] = None):
    client = require_auth()
    items = run_lib(
        lambda: client.moments.get_shared_moments_by_username(username, limit=limit)
    )
    return {"items": [normalize_moment(m) for m in (items or [])]}


@app.post("/api/post")
async def post_moment(
    image: Optional[UploadFile] = File(None),
    video: Optional[UploadFile] = File(None),
    caption: str = Form(""),
    note_type: str = Form("standard"),
    icon: Optional[str] = Form(None),
    colors: Optional[str] = Form(None),
    text_color: Optional[str] = Form(None),
    is_private: bool = Form(False),
):
    client = require_auth()
    if image is None and video is None:
        raise HTTPException(status_code=422, detail="Cần chọn ảnh hoặc video để đăng.")

    tmp_paths: list[str] = []

    async def _save(upload: UploadFile, default_suffix: str) -> str:
        data = await upload.read()
        suffix = os.path.splitext(upload.filename or "")[1] or default_suffix
        fd, path = tempfile.mkstemp(suffix=suffix, dir=DATA_DIR)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        tmp_paths.append(path)
        return path

    try:
        image_path = await _save(image, ".jpg") if image is not None else None
        video_path = await _save(video, ".mp4") if video is not None else None

        color_list = None
        if colors:
            try:
                parsed = json.loads(colors)
                color_list = parsed if isinstance(parsed, list) else None
            except Exception:
                color_list = [c.strip() for c in colors.split(",") if c.strip()]

        def _do():
            return client.moments.post(
                image=image_path,
                video=video_path,
                caption=caption or "",
                note_type=note_type or "standard",
                icon=icon or None,
                colors=color_list,
                text_color=text_color or None,
                is_private=bool(is_private),
            )

        result = run_lib(_do)
        return {"ok": True, "result": result}
    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except OSError:
                pass


@app.post("/api/react")
async def react(req: Request):
    client = require_auth()
    body = await req.json()
    moment_uid = body.get("moment_uid")
    reaction = body.get("reaction") or "❤️"
    if not moment_uid:
        raise HTTPException(status_code=422, detail="Thiếu moment_uid.")
    return run_lib(lambda: client.moments.react(moment_uid, reaction))


@app.post("/api/comment")
async def comment(req: Request):
    client = require_auth()
    body = await req.json()
    moment_uid = body.get("moment_uid")
    receiver_uid = body.get("receiver_uid")
    text = (body.get("text") or "").strip()
    if not moment_uid or not receiver_uid or not text:
        raise HTTPException(
            status_code=422, detail="Thiếu moment_uid, receiver_uid hoặc nội dung."
        )
    return run_lib(lambda: client.moments.comment(moment_uid, receiver_uid, text))


@app.get("/api/moments/{moment_uid}/views")
def moment_views(moment_uid: str):
    client = require_auth()
    return run_lib(lambda: client.moments.get_views(moment_uid))


@app.delete("/api/moments/{moment_uid}")
def delete_moment(moment_uid: str):
    client = require_auth()
    return run_lib(lambda: client.moments.delete(moment_uid))


@app.get("/api/presets")
def presets():
    try:
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    out = []
    if isinstance(data, dict):
        for key, val in data.items():
            item = {"id": key}
            if isinstance(val, dict):
                item.update(val)
            out.append(item)
    return {"items": out}


# ---------------------------------------------------------------------------
# Bạn bè
# ---------------------------------------------------------------------------
@app.get("/api/friends")
def friends():
    client = require_auth()
    items = run_lib(lambda: client.friends.get_all_friends())
    return {"items": [normalize_user(u) for u in (items or [])]}


@app.get("/api/friend-requests")
def friend_requests():
    client = require_auth()
    return run_lib(lambda: client.friends.get_friend_requests())


@app.post("/api/friends/request")
async def send_friend_request(req: Request):
    client = require_auth()
    body = await req.json()
    username = (body.get("username") or "").strip()
    user_uid = (body.get("user_uid") or "").strip()
    if username:
        return run_lib(lambda: client.friends.send_request_by_username(username))
    if user_uid:
        return run_lib(lambda: client.friends.send_request(user_uid))
    raise HTTPException(status_code=422, detail="Thiếu username hoặc user_uid.")


@app.post("/api/friends/accept")
async def accept_friend(req: Request):
    client = require_auth()
    body = await req.json()
    user_uid = (body.get("user_uid") or "").strip()
    if not user_uid:
        raise HTTPException(status_code=422, detail="Thiếu user_uid.")
    return run_lib(lambda: client.friends.accept_request(user_uid))


@app.post("/api/friends/remove")
async def remove_friend(req: Request):
    client = require_auth()
    body = await req.json()
    user_uid = (body.get("user_uid") or "").strip()
    if not user_uid:
        raise HTTPException(status_code=422, detail="Thiếu user_uid.")
    return run_lib(lambda: client.friends.remove(user_uid))


# ---------------------------------------------------------------------------
# Tin nhắn
# ---------------------------------------------------------------------------
@app.get("/api/conversations")
def conversations():
    client = require_auth()
    items = run_lib(lambda: client.chat.get_conversations())
    return {"items": items or []}


@app.get("/api/messages")
def messages(other_user_id: str):
    client = require_auth()
    items = run_lib(lambda: client.chat.get_messages(other_user_id=other_user_id))
    return {"items": items or []}


@app.post("/api/messages/send")
async def send_message(req: Request):
    client = require_auth()
    body = await req.json()
    receiver_uid = (body.get("receiver_uid") or "").strip()
    text = (body.get("text") or "").strip()
    if not receiver_uid or not text:
        raise HTTPException(status_code=422, detail="Thiếu người nhận hoặc nội dung.")
    return run_lib(lambda: client.chat.send_message(receiver_uid, text))


# ---------------------------------------------------------------------------
# Phục vụ frontend tĩnh
# ---------------------------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
