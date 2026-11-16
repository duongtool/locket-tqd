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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Optional

# Cho phép import gói locketlam đặt ở thư mục gốc của dự án
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
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
        "image_url": _first(m, "image_url", "imageUrl", "thumbnail_url"),
        "video_url": _first(m, "video_url", "videoUrl"),
        "caption": caption,
        "overlays": overlays,
        "views_count": m.get("views_count"),
        "viewers": m.get("viewers"),
        "reactions": m.get("reactions"),
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


_feed_cache: dict = {"ts": 0.0, "items": None}


@app.get("/api/feed/full")
def feed_full(fresh: bool = False):
    """Toàn bộ khoảnh khắc: GỘP CẢ BA NGUỒN của thư viện locketlam —
    (1) get_latest(), (2) quét feed một lượt bằng sync_token (bắt được cả
    moment nhóm và moment lọt khỏi bộ lọc theo người), (3) lịch sử riêng
    từng bạn bè + chính mình bằng get_shared_moments_by_user chạy đa luồng.
    Trả kèm thống kê từng nguồn/từng người để biết còn thiếu ở đâu; kết quả
    chỉ được đệm 120 giây khi đã nạp trọn, thiếu thì lần sau tự nạp lại."""
    client = require_auth()

    now = time.time()
    if (
        not fresh
        and _feed_cache["items"] is not None
        and now - _feed_cache["ts"] < 120
    ):
        items = _feed_cache["items"]
        return {"items": items, "count": len(items), "cached": True}

    def _do():
        merged: dict = {}
        stats: dict = {
            "latest": 0,
            "scan": 0,
            "per_user": {},
            "empty_users": 0,
            "complete": True,
        }

        def _add(m) -> bool:
            nm = normalize_moment(m)
            nm.pop("raw", None)
            mid = nm.get("id")
            if mid and mid not in merged:
                merged[mid] = nm
                return True
            return False

        # (1) Trang mới nhất
        try:
            latest = client.moments.get_latest() or []
        except Exception:
            latest = []
        stats["latest"] = len(latest)
        for m in latest:
            _add(m)

        # (2) Quét feed một lượt bằng sync_token (bổ sung moment nhóm)
        seen = set()
        sync = None
        scan_complete = False
        for _ in range(100):
            payload = {
                "should_count_missed_moments": True,
                "include_group_moments": True,
            }
            if sync:
                payload["sync_token"] = sync
            res = client.post_api("getLatestMomentV2", payload)
            data = res.get("data", []) if isinstance(res, dict) else []
            if not data:
                scan_complete = True
                break
            new_count = 0
            for m in data:
                if not isinstance(m, dict):
                    continue
                mid = m.get("canonical_uid")
                if mid and mid not in seen:
                    seen.add(mid)
                    new_count += 1
                    sync = mid
                    if _add(m):
                        stats["scan"] += 1
            if new_count == 0 or (isinstance(res, dict) and res.get("status") == 304):
                scan_complete = True
                break
        if not scan_complete:
            stats["complete"] = False

        # (3) Lịch sử riêng từng người, đa luồng, thử lại khi ra trống
        try:
            friends = client.friends.get_all_friends() or []
        except Exception:
            friends = []
        targets = [
            f.get("uid") for f in friends if isinstance(f, dict) and f.get("uid")
        ]
        my_uid = getattr(client.session, "uid", None)
        if my_uid and my_uid not in targets:
            targets.append(my_uid)

        def _fetch(uid):
            items = []
            for attempt in range(2):
                try:
                    items = client.moments.get_shared_moments_by_user(uid) or []
                except Exception:
                    items = []
                if items:
                    break
                if attempt == 0:
                    time.sleep(1)
            return uid, items

        if targets:
            with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
                for uid, items in pool.map(_fetch, targets):
                    stats["per_user"][uid] = len(items)
                    if not items:
                        stats["empty_users"] += 1
                    for m in items:
                        _add(m)

        items = sorted(
            merged.values(), key=lambda x: x.get("created_at") or 0, reverse=True
        )
        if stats["complete"]:
            _feed_cache["ts"] = time.time()
            _feed_cache["items"] = items
        return {"items": items, "count": len(items), "stats": stats}

    return run_lib(_do)


@app.get("/api/my-moments")
def my_moments(
    limit: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    client = require_auth()
    items = run_lib(
        lambda: client.moments.get_all_my_moments(
            limit=limit, start_date=start_date, end_date=end_date
        )
    )
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
    recipients: Optional[str] = Form(None),
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

        recipient_list = None
        if recipients:
            try:
                parsed_r = json.loads(recipients)
                if isinstance(parsed_r, list):
                    recipient_list = [str(x) for x in parsed_r if x]
            except Exception:
                recipient_list = None

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
                recipients=recipient_list,
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
# Thiết bị giả lập & phiên nâng cao
# ---------------------------------------------------------------------------
@app.get("/api/device")
def device_info():
    client = get_client()
    try:
        info = client.device.to_dict()
    except Exception:
        info = {}
    return {"device": info}


@app.post("/api/device/auto")
async def device_auto(req: Request):
    body = await req.json()
    auto = bool(body.get("auto_emulate", True))
    client = get_client()

    def _do():
        client.set_device(auto_emulate=auto)
        return {"device": client.device.to_dict()}

    return run_lib(_do)


@app.post("/api/session/refresh")
def session_refresh():
    client = require_auth()
    return run_lib(lambda: (client.session.refresh(), {"ok": True})[1])


@app.post("/api/session/sync")
def session_sync():
    client = require_auth()

    def _do():
        out = {}
        try:
            out["sync"] = client.user.sync_client_data()
        except Exception as e:
            out["sync_error"] = str(e)
        try:
            out["notification_token"] = client.user.set_notification_token()
        except Exception as e:
            out["notification_token_error"] = str(e)
        return out

    return run_lib(_do)


# ---------------------------------------------------------------------------
# Hồ sơ mở rộng
# ---------------------------------------------------------------------------
@app.post("/api/profile/birthdate")
async def update_birthdate(req: Request):
    client = require_auth()
    body = await req.json()
    birthdate = (body.get("birthdate") or "").strip()
    if not birthdate:
        raise HTTPException(status_code=422, detail="Thiếu ngày sinh (YYYY-MM-DD).")
    return run_lib(lambda: client.user.update_birthdate(birthdate))


@app.get("/api/users/by-uid/{user_uid}")
def user_by_uid(user_uid: str):
    client = require_auth()
    profile = run_lib(lambda: client.user.get_profile(user_uid))
    return normalize_user(profile)


@app.get("/api/users/by-uid/{user_uid}/moments")
def moments_by_uid(user_uid: str, limit: Optional[int] = None):
    client = require_auth()
    items = run_lib(
        lambda: client.moments.get_shared_moments_by_user(user_uid, limit=limit)
    )
    return {"items": [normalize_moment(m) for m in (items or [])]}


# ---------------------------------------------------------------------------
# Khoảnh khắc mở rộng: bộ lọc, đã xem, Rollcall
# ---------------------------------------------------------------------------
@app.get("/api/filters")
def filters():
    client = require_auth()
    return run_lib(lambda: client.moments.get_filters())


@app.post("/api/moments/viewed")
async def mark_viewed(req: Request):
    client = require_auth()
    body = await req.json()
    moment_uid = body.get("moment_uid")
    if not moment_uid:
        raise HTTPException(status_code=422, detail="Thiếu moment_uid.")
    return run_lib(lambda: client.moments.mark_as_viewed(moment_uid))


@app.get("/api/rollcall")
def rollcall(week: Optional[int] = None, year: Optional[int] = None):
    client = require_auth()
    result = run_lib(
        lambda: client.moments.get_rollcall_posts(week_of_year=week, year=year)
    )
    items: list = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        for key in ("posts", "moments", "data", "items", "rollcall_posts"):
            if isinstance(result.get(key), list):
                items = result[key]
                break
    return {"items": [normalize_moment(m) for m in items], "raw": result}


# ---------------------------------------------------------------------------
# Bạn bè mở rộng: nhóm, chặn, gợi ý, link mời
# ---------------------------------------------------------------------------
@app.get("/api/groups")
def groups():
    client = require_auth()
    return run_lib(lambda: client.friends.get_groups_and_friends())


@app.post("/api/friends/block")
async def block_friend(req: Request):
    client = require_auth()
    body = await req.json()
    user_uid = (body.get("user_uid") or "").strip()
    if not user_uid:
        raise HTTPException(status_code=422, detail="Thiếu user_uid.")
    return run_lib(lambda: client.friends.block(user_uid))


@app.post("/api/friends/unblock")
async def unblock_friend(req: Request):
    client = require_auth()
    body = await req.json()
    user_uid = (body.get("user_uid") or "").strip()
    if not user_uid:
        raise HTTPException(status_code=422, detail="Thiếu user_uid.")
    return run_lib(lambda: client.friends.unblock(user_uid))


@app.post("/api/friends/suggest")
async def suggest_friends(req: Request):
    client = require_auth()
    body = await req.json()
    contacts = body.get("phone_contacts") or []
    if not isinstance(contacts, list):
        raise HTTPException(status_code=422, detail="phone_contacts phải là danh sách.")
    result = run_lib(lambda: client.friends.suggest_friends(contacts))
    items: list = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        for key in ("data", "users", "suggestions", "items"):
            if isinstance(result.get(key), list):
                items = result[key]
                break
    return {"items": [normalize_user(u) for u in items], "raw": result}


@app.get("/api/invite/{username}")
def invite_info(username: str):
    client = require_auth()

    def _do():
        token = client.friends.resolve_invite_token_from_username(username)
        user = None
        if token:
            try:
                user = client.friends.fetch_user_by_invite_token(token)
            except Exception:
                user = None
        return {
            "username": username,
            "invite_token": token,
            "link": f"https://locket.cam/{username}",
            "user": normalize_user(user) if user else None,
        }

    return run_lib(_do)


# ---------------------------------------------------------------------------
# Tin nhắn mở rộng: gửi khoảnh khắc, cảm xúc, thu hồi, đã đọc, thời gian thực
# ---------------------------------------------------------------------------
@app.get("/api/chat/reactions")
def chat_reactions():
    require_auth()
    from locketlam.modules.chat import ChatModule

    return {"items": ChatModule.get_supported_reactions()}


@app.post("/api/messages/send-moment")
async def send_moment(req: Request):
    client = require_auth()
    body = await req.json()
    receiver_uid = (body.get("receiver_uid") or "").strip()
    moment_uid = (body.get("moment_uid") or "").strip()
    text = body.get("text")
    if not receiver_uid or not moment_uid:
        raise HTTPException(status_code=422, detail="Thiếu receiver_uid hoặc moment_uid.")
    return run_lib(
        lambda: client.chat.send_moment(receiver_uid, moment_uid, text or None)
    )


@app.post("/api/messages/reaction")
async def message_reaction(req: Request):
    client = require_auth()
    body = await req.json()
    conversation_id = (body.get("conversation_id") or "").strip()
    message_id = (body.get("message_id") or "").strip()
    emoji = (body.get("emoji") or "").strip()
    if not conversation_id or not message_id or not emoji:
        raise HTTPException(
            status_code=422, detail="Thiếu conversation_id, message_id hoặc emoji."
        )
    return run_lib(
        lambda: client.chat.send_reaction(conversation_id, message_id, emoji)
    )


@app.post("/api/messages/reaction/remove")
async def message_reaction_remove(req: Request):
    client = require_auth()
    body = await req.json()
    conversation_id = (body.get("conversation_id") or "").strip()
    message_id = (body.get("message_id") or "").strip()
    if not conversation_id or not message_id:
        raise HTTPException(status_code=422, detail="Thiếu conversation_id hoặc message_id.")
    return run_lib(
        lambda: client.chat.remove_reaction(conversation_id, message_id)
    )


@app.post("/api/messages/delete")
async def message_delete(req: Request):
    client = require_auth()
    body = await req.json()
    conversation_uid = (body.get("conversation_uid") or "").strip()
    message_uid = (body.get("message_uid") or "").strip()
    if not conversation_uid or not message_uid:
        raise HTTPException(status_code=422, detail="Thiếu conversation_uid hoặc message_uid.")
    return run_lib(
        lambda: client.chat.delete_message(conversation_uid, message_uid)
    )


@app.post("/api/messages/read")
async def message_read(req: Request):
    client = require_auth()
    body = await req.json()
    conversation_uid = (body.get("conversation_uid") or "").strip() or None
    other_user_id = (body.get("other_user_id") or "").strip() or None
    send_receipt = bool(body.get("send_read_receipt", True))
    if not conversation_uid and not other_user_id:
        raise HTTPException(
            status_code=422, detail="Thiếu conversation_uid hoặc other_user_id."
        )
    return run_lib(
        lambda: client.chat.mark_as_read(
            conversation_uid=conversation_uid,
            other_user_id=other_user_id,
            send_read_receipt=send_receipt,
        )
    )


@app.websocket("/api/chat/ws")
async def chat_ws(websocket: WebSocket, other_user_id: str):
    """Cầu nối WebSocket: chuyển tiếp tin nhắn thời gian thực từ Locket về trình duyệt."""
    client = get_client()
    if not client.is_authenticated():
        await websocket.close(code=4401)
        return
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()

    def _on_message(msg):
        try:
            queue.put_nowait(msg)
        except Exception:
            pass

    async def _pump():
        while True:
            msg = await queue.get()
            await websocket.send_json({"type": "message", "data": msg})

    async def _listen():
        await client.chat.listen_realtime(other_user_id, _on_message)

    tasks = [asyncio.create_task(_pump()), asyncio.create_task(_listen())]
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        for t in tasks:
            t.cancel()


# ---------------------------------------------------------------------------
# Phục vụ frontend tĩnh
# ---------------------------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
