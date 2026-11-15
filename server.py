#!/usr/bin/env python3
"""
Locket Tqd - Backend Server
Khai thác full locketlam SDK — auto_compress H.265 cho video > 6MB
"""

import os
import json
import uuid
import base64
import subprocess
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

try:
    from locketlam import LocketClient, NoteType
    from locketlam.exceptions import (
        AuthenticationError,
        LocketAPIError,
        StorageUploadError,
        LocketError,
    )
except ImportError:
    print("Chưa cài locketlam! pip install locketlam flask flask-cors gunicorn")
    raise

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "locket-tqd-secret-key-2026-change-me")
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER", "") == "true"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
CORS(app, supports_credentials=True)

clients = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_client():
    sid = session.get("sid")
    if not sid or sid not in clients:
        return None
    return clients[sid]


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        client = get_client()
        if not client or not client.is_authenticated():
            return jsonify({"ok": False, "error": "Chưa đăng nhập"}), 401
        return f(client, *args, **kwargs)
    return decorated


def extract_thumbnail(video_path: str) -> str:
    """Cắt 1 frame từ video làm thumbnail JPG (dự phòng)."""
    out_path = os.path.join(UPLOAD_DIR, f"thumb_{uuid.uuid4().hex}.jpg")
    ffmpeg_bin = "ffmpeg"
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    for ss in ("0.5", "0"):
        cmd = [ffmpeg_bin, "-y", "-ss", ss, "-i", video_path, "-frames:v", "1", "-q:v", "3", out_path]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
        except Exception:
            continue
    raise RuntimeError("Không cắt được thumbnail")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def status():
    client = get_client()
    if client and client.is_authenticated():
        return jsonify({
            "ok": True,
            "authenticated": True,
            "uid": client.session.uid,
            "email": getattr(client.session, "email", None),
        })
    return jsonify({"ok": True, "authenticated": False})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"ok": False, "error": "Thiếu email hoặc mật khẩu"}), 400
    sid = str(uuid.uuid4())
    session_path = os.path.join(SESSION_DIR, f"{sid}.json")
    try:
        client = LocketClient(session_path=session_path)
        client.set_device(auto_emulate=True)
        login_data = client.login(email=email, password=password)
        clients[sid] = client
        session["sid"] = sid
        profile = {}
        try:
            profile = client.user.get_profile() or {}
        except Exception:
            pass
        return jsonify({
            "ok": True,
            "uid": login_data.get("localId") or client.session.uid,
            "email": login_data.get("email") or email,
            "profile": profile,
        })
    except AuthenticationError as e:
        return jsonify({"ok": False, "error": f"Đăng nhập thất bại: {str(e)}"}), 401
    except LocketError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Lỗi hệ thống: {str(e)}"}), 500


@app.route("/api/logout", methods=["POST"])
def logout():
    sid = session.pop("sid", None)
    if sid and sid in clients:
        del clients[sid]
    return jsonify({"ok": True})


@app.route("/api/profile")
@require_auth
def profile(client):
    try:
        uid = request.args.get("uid")
        data = client.user.get_profile(user_uid=uid) if uid else client.user.get_profile()
        return jsonify({"ok": True, "profile": data or {}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/profile/username/<username>")
@require_auth
def profile_by_username(client, username):
    try:
        return jsonify({"ok": True, "profile": client.user.get_profile_by_username(username) or {}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/profile/update", methods=["POST"])
@require_auth
def update_profile(client):
    data = request.get_json() or {}
    try:
        if "first_name" in data or "last_name" in data:
            client.user.update_name(first_name=data.get("first_name", ""), last_name=data.get("last_name", ""))
        if "birthdate" in data:
            client.user.update_birthdate(data["birthdate"])
        if "avatar" in data:
            client.user.update_avatar(data["avatar"])
        return jsonify({"ok": True, "profile": client.user.get_profile()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends")
@require_auth
def friends(client):
    try:
        return jsonify({"ok": True, "friends": client.friends.get_all_friends() or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/request", methods=["POST"])
@require_auth
def send_friend_request(client):
    data = request.get_json() or {}
    try:
        if data.get("username"):
            client.friends.send_request_by_username(data["username"])
        elif data.get("uid"):
            client.friends.send_request(user_uid=data["uid"])
        else:
            return jsonify({"ok": False, "error": "Thiếu username hoặc uid"}), 400
        return jsonify({"ok": True, "message": "Đã gửi lời mời kết bạn"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/accept", methods=["POST"])
@require_auth
def accept_friend(client):
    data = request.get_json() or {}
    if not data.get("uid"):
        return jsonify({"ok": False, "error": "Thiếu uid"}), 400
    try:
        client.friends.accept_request(user_uid=data["uid"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/remove", methods=["POST"])
@require_auth
def remove_friend(client):
    data = request.get_json() or {}
    if not data.get("uid"):
        return jsonify({"ok": False, "error": "Thiếu uid"}), 400
    try:
        client.friends.remove(user_uid=data["uid"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/feed")
@require_auth
def feed(client):
    try:
        return jsonify({"ok": True, "posts": client.moments.get_latest() or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/user/<username>")
@require_auth
def moments_by_username(client, username):
    limit = request.args.get("limit", 20, type=int)
    try:
        return jsonify({"ok": True, "posts": client.moments.get_posts_by_username(username, limit=limit) or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/post", methods=["POST"])
@require_auth
def post_moment(client):
    """
    Đăng ảnh/video.
    Video: auto_compress=True (locketlam nén H.265 nếu >= 6MB),
    priority=balanced|video|audio.
    """
    image_path = None
    video_path = None
    thumb_generated = None
    try:
        caption = request.form.get("caption") or (request.get_json() or {}).get("caption") or ""
        is_private = request.form.get("is_private", "false").lower() == "true"
        note_type_str = request.form.get("note_type") or "STANDARD"
        icon = request.form.get("icon")
        colors_raw = request.form.get("colors")
        note_type = getattr(NoteType, note_type_str.upper(), NoteType.STANDARD)
        colors = None
        if colors_raw:
            try:
                colors = json.loads(colors_raw)
            except Exception:
                pass

        if "image" in request.files:
            f = request.files["image"]
            if f.filename:
                fname = secure_filename(f.filename) or f"img_{uuid.uuid4().hex}.jpg"
                image_path = os.path.join(UPLOAD_DIR, fname)
                f.save(image_path)

        if "video" in request.files:
            f = request.files["video"]
            if f.filename:
                fname = secure_filename(f.filename) or f"vid_{uuid.uuid4().hex}.mp4"
                video_path = os.path.join(UPLOAD_DIR, fname)
                f.save(video_path)

        if not image_path and request.is_json:
            data = request.get_json()
            if data.get("image_base64"):
                img_data = base64.b64decode(data["image_base64"].split(",")[-1])
                image_path = os.path.join(UPLOAD_DIR, f"img_{uuid.uuid4().hex}.jpg")
                with open(image_path, "wb") as fh:
                    fh.write(img_data)

        if not image_path and not video_path:
            return jsonify({"ok": False, "error": "Thiếu ảnh hoặc video"}), 400

        original_mb = None
        if video_path:
            original_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
            if not image_path:
                try:
                    image_path = extract_thumbnail(video_path)
                    thumb_generated = image_path
                except Exception:
                    image_path = None  # locketlam cũng tự cắt thumb từ video

        priority = (request.form.get("priority") or "balanced").lower()
        if priority not in ("video", "audio", "balanced"):
            priority = "balanced"

        kwargs = {
            "caption": caption,
            "is_private": is_private,
            "note_type": note_type,
        }
        if icon:
            kwargs["icon"] = icon
        if colors:
            kwargs["colors"] = colors

        if video_path:
            if image_path:
                kwargs["image"] = image_path
            kwargs["video"] = video_path
            # Đúng theo docs locketlam: tự nén H.265 nếu >= 6MB
            kwargs["auto_compress"] = True
            kwargs["priority"] = priority
        else:
            kwargs["image"] = image_path

        result = client.moments.post(**kwargs)
        return jsonify({
            "ok": True,
            "moment": result,
            "original_size_mb": original_mb,
            "auto_compress": bool(video_path),
            "priority": priority if video_path else None,
        })
    except StorageUploadError as e:
        return jsonify({"ok": False, "error": f"Upload thất bại: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        for p in (image_path, video_path, thumb_generated):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


@app.route("/api/moments/react", methods=["POST"])
@require_auth
def react_moment(client):
    data = request.get_json() or {}
    moment_uid = data.get("moment_uid")
    if not moment_uid:
        return jsonify({"ok": False, "error": "Thiếu moment_uid"}), 400
    try:
        client.moments.react(moment_uid=moment_uid, reaction=data.get("reaction", "❤️"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/views/<moment_uid>")
@require_auth
def moment_views(client, moment_uid):
    try:
        return jsonify({"ok": True, "views": client.moments.get_views(moment_uid=moment_uid)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/delete", methods=["POST"])
@require_auth
def delete_moment(client):
    data = request.get_json() or {}
    if not data.get("moment_uid"):
        return jsonify({"ok": False, "error": "Thiếu moment_uid"}), 400
    try:
        client.moments.delete(moment_uid=data["moment_uid"])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/conversations")
@require_auth
def conversations(client):
    try:
        return jsonify({"ok": True, "conversations": client.chat.get_conversations() or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/messages")
@require_auth
def messages(client):
    other_uid = request.args.get("uid")
    if not other_uid:
        return jsonify({"ok": False, "error": "Thiếu uid"}), 400
    try:
        return jsonify({"ok": True, "messages": client.chat.get_messages(other_user_id=other_uid) or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/send", methods=["POST"])
@require_auth
def send_message(client):
    data = request.get_json() or {}
    if not data.get("uid"):
        return jsonify({"ok": False, "error": "Thiếu uid người nhận"}), 400
    try:
        if data.get("moment_uid"):
            client.chat.send_moment(receiver_uid=data["uid"], moment_uid=data["moment_uid"], text=data.get("text"))
        else:
            client.chat.send_message(receiver_uid=data["uid"], text=data.get("text"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/note-types")
def note_types():
    types = [a for a in dir(NoteType) if not a.startswith("_") and a.isupper()]
    return jsonify({"ok": True, "types": types})


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "Locket Tqd"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print("Locket Tqd on port", port)
    app.run(host="0.0.0.0", port=port, debug=debug)
