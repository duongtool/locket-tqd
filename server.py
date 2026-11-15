#!/usr/bin/env python3
"""
Locket Tqd - Backend Server
Khai thác full locketlam SDK (https://github.com/leanhminh2104/locketlam)
Ready for Render.com deployment
"""

import os
import json
import uuid
import base64
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
    print("=" * 60)
    print("⚠️  Chưa cài locketlam!")
    print("   Chạy: pip install locketlam flask flask-cors gunicorn")
    print("=" * 60)
    raise

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "locket-tqd-secret-key-2026-change-me")
# Production cookie settings for Render (HTTPS)
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER", "") == "true"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
CORS(app, supports_credentials=True)

# Global client instances keyed by session id (simple in-memory store)
clients = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_client():
    """Lấy LocketClient theo session hiện tại"""
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
        if uid:
            data = client.user.get_profile(user_uid=uid)
        else:
            data = client.user.get_profile()
        return jsonify({"ok": True, "profile": data or {}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/profile/username/<username>")
@require_auth
def profile_by_username(client, username):
    try:
        data = client.user.get_profile_by_username(username)
        return jsonify({"ok": True, "profile": data or {}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/profile/update", methods=["POST"])
@require_auth
def update_profile(client):
    data = request.get_json() or {}
    try:
        if "first_name" in data or "last_name" in data:
            client.user.update_name(
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
        if "birthdate" in data:
            client.user.update_birthdate(data["birthdate"])
        if "avatar" in data:
            client.user.update_avatar(data["avatar"])
        profile = client.user.get_profile()
        return jsonify({"ok": True, "profile": profile})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends")
@require_auth
def friends(client):
    try:
        friends_list = client.friends.get_all_friends() or []
        return jsonify({"ok": True, "friends": friends_list})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/request", methods=["POST"])
@require_auth
def send_friend_request(client):
    data = request.get_json() or {}
    username = data.get("username")
    uid = data.get("uid")
    try:
        if username:
            client.friends.send_request_by_username(username)
        elif uid:
            client.friends.send_request(user_uid=uid)
        else:
            return jsonify({"ok": False, "error": "Thiếu username hoặc uid"}), 400
        return jsonify({"ok": True, "message": "Đã gửi lời mời kết bạn"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/accept", methods=["POST"])
@require_auth
def accept_friend(client):
    data = request.get_json() or {}
    uid = data.get("uid")
    if not uid:
        return jsonify({"ok": False, "error": "Thiếu uid"}), 400
    try:
        client.friends.accept_request(user_uid=uid)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/remove", methods=["POST"])
@require_auth
def remove_friend(client):
    data = request.get_json() or {}
    uid = data.get("uid")
    if not uid:
        return jsonify({"ok": False, "error": "Thiếu uid"}), 400
    try:
        client.friends.remove(user_uid=uid)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/feed")
@require_auth
def feed(client):
    try:
        posts = client.moments.get_latest() or []
        return jsonify({"ok": True, "posts": posts})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/user/<username>")
@require_auth
def moments_by_username(client, username):
    limit = request.args.get("limit", 20, type=int)
    try:
        posts = client.moments.get_posts_by_username(username, limit=limit) or []
        return jsonify({"ok": True, "posts": posts})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/post", methods=["POST"])
@require_auth
def post_moment(client):
    """Post photo/video moment. Hỗ trợ multipart/form-data hoặc JSON base64"""
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

        image_path = None
        video_path = None

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
                with open(image_path, "wb") as f:
                    f.write(img_data)

        if not image_path and not video_path:
            return jsonify({"ok": False, "error": "Thiếu ảnh hoặc video"}), 400

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
            kwargs["image"] = image_path
            kwargs["video"] = video_path
        else:
            kwargs["image"] = image_path

        result = client.moments.post(**kwargs)

        for p in [image_path, video_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        return jsonify({"ok": True, "moment": result})
    except StorageUploadError as e:
        return jsonify({"ok": False, "error": f"Upload thất bại: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/react", methods=["POST"])
@require_auth
def react_moment(client):
    data = request.get_json() or {}
    moment_uid = data.get("moment_uid")
    reaction = data.get("reaction", "❤️")
    if not moment_uid:
        return jsonify({"ok": False, "error": "Thiếu moment_uid"}), 400
    try:
        client.moments.react(moment_uid=moment_uid, reaction=reaction)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/views/<moment_uid>")
@require_auth
def moment_views(client, moment_uid):
    try:
        views = client.moments.get_views(moment_uid=moment_uid)
        return jsonify({"ok": True, "views": views})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/moments/delete", methods=["POST"])
@require_auth
def delete_moment(client):
    data = request.get_json() or {}
    moment_uid = data.get("moment_uid")
    if not moment_uid:
        return jsonify({"ok": False, "error": "Thiếu moment_uid"}), 400
    try:
        client.moments.delete(moment_uid=moment_uid)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/conversations")
@require_auth
def conversations(client):
    try:
        convs = client.chat.get_conversations() or []
        return jsonify({"ok": True, "conversations": convs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/messages")
@require_auth
def messages(client):
    other_uid = request.args.get("uid")
    if not other_uid:
        return jsonify({"ok": False, "error": "Thiếu uid"}), 400
    try:
        msgs = client.chat.get_messages(other_user_id=other_uid) or []
        return jsonify({"ok": True, "messages": msgs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/send", methods=["POST"])
@require_auth
def send_message(client):
    data = request.get_json() or {}
    receiver_uid = data.get("uid")
    text = data.get("text")
    moment_uid = data.get("moment_uid")
    if not receiver_uid:
        return jsonify({"ok": False, "error": "Thiếu uid người nhận"}), 400
    try:
        if moment_uid:
            client.chat.send_moment(receiver_uid=receiver_uid, moment_uid=moment_uid, text=text)
        else:
            client.chat.send_message(receiver_uid=receiver_uid, text=text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/note-types")
def note_types():
    """Danh sách NoteType có sẵn"""
    types = [attr for attr in dir(NoteType) if not attr.startswith("_") and attr.isupper()]
    return jsonify({"ok": True, "types": types})


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "Locket Tqd"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print("\n" + "=" * 60)
    print("💛  Locket Tqd Server")
    print(f"    http://0.0.0.0:{port}")
    print("    Powered by locketlam SDK")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
