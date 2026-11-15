#!/usr/bin/env python3
"""
Locket Tqd - Backend Server
Video: pre-compress < 5.5MB + locketlam auto_compress
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
    print("Chua cai locketlam!")
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

MAX_VIDEO_BYTES = 6 * 1024 * 1024


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
            return jsonify({"ok": False, "error": "Chua dang nhap"}), 401
        return f(client, *args, **kwargs)
    return decorated


def get_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def extract_thumbnail(video_path: str) -> str:
    out_path = os.path.join(UPLOAD_DIR, f"thumb_{uuid.uuid4().hex}.jpg")
    ffmpeg_bin = get_ffmpeg()
    for ss in ("0.5", "0"):
        cmd = [ffmpeg_bin, "-y", "-ss", ss, "-i", video_path, "-frames:v", "1", "-q:v", "3", out_path]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
        except Exception:
            continue
    raise RuntimeError("Khong cat duoc thumbnail tu video")


def compress_video(video_path: str, max_bytes: int = MAX_VIDEO_BYTES) -> str:
    """Nen video xuong duoi max_bytes. Thu nhieu muc CRF + scale."""
    ffmpeg_bin = get_ffmpeg()
    size = os.path.getsize(video_path)
    if size < max_bytes:
        return video_path

    out_path = os.path.join(UPLOAD_DIR, f"cmp_{uuid.uuid4().hex}.mp4")
    attempts = [
        (720, 28, "veryfast"),
        (720, 32, "veryfast"),
        (540, 30, "veryfast"),
        (540, 34, "veryfast"),
        (480, 32, "veryfast"),
        (480, 36, "ultrafast"),
        (360, 34, "ultrafast"),
        (360, 38, "ultrafast"),
        (360, 40, "ultrafast"),
    ]

    last_err = None
    for height, crf, preset in attempts:
        try:
            cmd = [
                ffmpeg_bin, "-y", "-i", video_path,
                "-vf", f"scale=-2:{height}",
                "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-c:a", "aac", "-b:a", "64k",
                "-movflags", "+faststart", "-pix_fmt", "yuv420p",
                out_path,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
            if os.path.exists(out_path) and 0 < os.path.getsize(out_path) < max_bytes:
                return out_path
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
        except Exception as e:
            last_err = e
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            continue

    # Lan cuoi: bitrate thap + 360p, co the cat 20s
    try:
        cmd = [
            ffmpeg_bin, "-y", "-i", video_path,
            "-vf", "scale=-2:360",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-b:v", "700k", "-maxrate", "900k", "-bufsize", "1800k",
            "-c:a", "aac", "-b:a", "48k",
            "-movflags", "+faststart", "-pix_fmt", "yuv420p",
            out_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
        if os.path.exists(out_path) and 0 < os.path.getsize(out_path) < max_bytes:
            return out_path
        if os.path.exists(out_path) and os.path.getsize(out_path) >= max_bytes:
            out2 = os.path.join(UPLOAD_DIR, f"cmp2_{uuid.uuid4().hex}.mp4")
            cmd2 = [ffmpeg_bin, "-y", "-i", out_path, "-t", "20", "-c", "copy", out2]
            subprocess.run(cmd2, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
            try:
                os.remove(out_path)
            except Exception:
                pass
            if os.path.exists(out2):
                return out2
    except Exception as e:
        last_err = e

    raise RuntimeError(
        f"Khong nen duoc video duoi {max_bytes/(1024*1024):.1f}MB. "
        f"Goc: {size/(1024*1024):.1f} MB. Loi: {last_err}"
    )


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
        return jsonify({"ok": False, "error": "Thieu email hoac mat khau"}), 400
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
        return jsonify({"ok": False, "error": f"Dang nhap that bai: {str(e)}"}), 401
    except LocketError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Loi he thong: {str(e)}"}), 500


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
            return jsonify({"ok": False, "error": "Thieu username hoac uid"}), 400
        return jsonify({"ok": True, "message": "Da gui loi moi"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/friends/accept", methods=["POST"])
@require_auth
def accept_friend(client):
    data = request.get_json() or {}
    if not data.get("uid"):
        return jsonify({"ok": False, "error": "Thieu uid"}), 400
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
        return jsonify({"ok": False, "error": "Thieu uid"}), 400
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
    """Dang anh/video. Video >=5.5MB se duoc nen truoc khi upload."""
    image_path = None
    video_path = None
    thumb_generated = None
    compressed_path = None
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
            return jsonify({"ok": False, "error": "Thieu anh hoac video"}), 400

        original_mb = None
        did_compress = False
        if video_path:
            original_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
            size_b = os.path.getsize(video_path)
            SAFE = 5_500_000  # nen som de chac an duoi 6MB
            if size_b >= SAFE:
                try:
                    print(f"[post] compress start {original_mb}MB")
                    out = compress_video(video_path, max_bytes=SAFE)
                    if out != video_path:
                        compressed_path = out
                        try:
                            os.remove(video_path)
                        except Exception:
                            pass
                        video_path = out
                        did_compress = True
                        new_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
                        print(f"[post] compress done {original_mb}MB -> {new_mb}MB")
                except Exception as e:
                    print(f"[post] pre-compress failed: {e}")

            if not image_path:
                try:
                    image_path = extract_thumbnail(video_path)
                    thumb_generated = image_path
                except Exception as e:
                    return jsonify({"ok": False, "error": f"Khong tao duoc thumbnail: {e}"}), 400

            final_size = os.path.getsize(video_path)
            if final_size >= 6_291_456:
                mb = final_size / (1024 * 1024)
                return jsonify({
                    "ok": False,
                    "error": (
                        f"Video sau nen van con {mb:.1f} MB (Locket can < 6 MB). "
                        "Hay chon video ngan hon."
                    )
                }), 400

        priority = (request.form.get("priority") or "balanced").lower()
        if priority not in ("video", "audio", "balanced"):
            priority = "balanced"

        kwargs = {"caption": caption, "is_private": is_private, "note_type": note_type}
        if icon:
            kwargs["icon"] = icon
        if colors:
            kwargs["colors"] = colors

        if video_path:
            kwargs["image"] = image_path
            kwargs["video"] = video_path
            kwargs["auto_compress"] = True
            kwargs["priority"] = priority
        else:
            kwargs["image"] = image_path

        result = client.moments.post(**kwargs)
        final_mb = None
        if video_path and os.path.exists(video_path):
            final_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
        return jsonify({
            "ok": True,
            "moment": result,
            "original_size_mb": original_mb,
            "compressed": did_compress,
            "final_size_mb": final_mb,
            "auto_compress": bool(video_path),
        })
    except StorageUploadError as e:
        return jsonify({"ok": False, "error": f"Upload that bai: {str(e)}"}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        msg = str(e) or e.__class__.__name__
        if "6 MB" in msg or "6MB" in msg or "6291456" in msg:
            msg = "Video vuot gioi han 6 MB cua Locket. Nen chua du — thu video ngan hon."
        elif "compress" in msg.lower() or "ffmpeg" in msg.lower():
            msg = f"Nen video that bai: {msg}"
        return jsonify({"ok": False, "error": msg}), 400
    finally:
        for p in (image_path, video_path, thumb_generated, compressed_path):
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
        return jsonify({"ok": False, "error": "Thieu moment_uid"}), 400
    try:
        client.moments.react(moment_uid=moment_uid, reaction=data.get("reaction", "\u2764\ufe0f"))
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
        return jsonify({"ok": False, "error": "Thieu moment_uid"}), 400
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
        return jsonify({"ok": False, "error": "Thieu uid"}), 400
    try:
        return jsonify({"ok": True, "messages": client.chat.get_messages(other_user_id=other_uid) or []})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/chat/send", methods=["POST"])
@require_auth
def send_message(client):
    data = request.get_json() or {}
    if not data.get("uid"):
        return jsonify({"ok": False, "error": "Thieu uid nguoi nhan"}), 400
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
