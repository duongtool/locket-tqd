#!/usr/bin/env python3
"""
Kiểm thử khói (smoke test) cho backend Locket Tqd.

Chạy toàn bộ endpoint bằng một FakeClient giả lập thư viện locketlam,
không cần tài khoản Locket thật:

    .venv/bin/pip install httpx
    .venv/bin/python tests/smoke_test.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000000020001e221bc330000"
    "000049454e44ae426082"
)

FRIEND_UID = "FRIENDUID123456789012345678"
ME_UID = "MEUID1234567890123456789012"

SAMPLE_MOMENT = {
    "canonical_uid": "mom1",
    "user": FRIEND_UID,
    "thumbnail_url": "https://example.com/t.jpg",
    "video_url": None,
    "caption": "Xin chào",
    "date": {"_seconds": 1794700000},
    "overlays": [],
    "views_count": 3,
    "viewers": [FRIEND_UID],
    "reactions": [{"user": FRIEND_UID, "reaction": "❤️"}],
}

SAMPLE_PROFILE = {
    "uid": ME_UID,
    "first_name": "T",
    "last_name": "Q D",
    "username": "tqd",
    "profile_picture_url": "https://example.com/a.jpg",
}


class FakeSession:
    uid = ME_UID
    email = "tqd@example.com"
    id_token = "fake-token"
    refresh_token = "fake-refresh"

    def refresh(self):
        return None


class FakeDevice:
    def to_dict(self):
        return {"model_name": "iPhone 15 Pro", "ios_version": "18.1.0"}


class FakeUser:
    def get_profile(self, user_uid=None):
        return dict(SAMPLE_PROFILE, uid=user_uid or ME_UID)

    def get_profile_by_username(self, username):
        return dict(SAMPLE_PROFILE, username=username)

    def update_name(self, first_name, last_name):
        return {"ok": True}

    def update_birthdate(self, birthdate):
        return {"ok": True, "birthdate": birthdate}

    def update_avatar(self, path):
        return {"ok": True}

    def sync_client_data(self, **kw):
        return {"ok": True}

    def set_notification_token(self, **kw):
        return {"ok": True}


class FakeMoments:
    def get_latest(self):
        return [SAMPLE_MOMENT]

    def get_all_my_moments(self, limit=None, start_date=None, end_date=None):
        return [SAMPLE_MOMENT]

    def get_shared_moments_by_username(self, username, limit=None):
        return [SAMPLE_MOMENT]

    def get_shared_moments_by_user(self, user_uid, limit=None):
        return [SAMPLE_MOMENT]

    def get_filters(self):
        return {"filters": [{"name": "Normal"}, {"name": "Vivid"}]}

    def mark_as_viewed(self, moment_uid):
        return {"ok": True}

    def react(self, moment_uid, reaction="❤️", from_memory=False):
        return {"ok": True}

    def comment(self, moment_uid, receiver_uid, text, from_memory=False):
        return {"ok": True}

    def get_views(self, moment_uid):
        return {"count": 3, "views": []}

    def delete(self, moment_uid):
        return {"ok": True}

    def get_rollcall_posts(self, week_of_year=None, year=None, source="banner"):
        return {"posts": [SAMPLE_MOMENT]}

    def post(self, **kwargs):
        assert kwargs.get("image") or kwargs.get("video"), "post thiếu media"
        return {"id": "mom_new", "canonical_uid": "mom_new"}


class FakeFriends:
    def get_all_friends(self):
        return [dict(SAMPLE_PROFILE, uid=FRIEND_UID, username="banbe")]

    def get_friend_requests(self):
        return {"incoming": [], "outgoing": []}

    def get_groups_and_friends(self):
        return {"groups": [{"id": "g1", "name": "Nhóm test"}], "friends": []}

    def send_request(self, user_uid, source="inviteCardPopup"):
        return {"ok": True}

    def send_request_by_username(self, username):
        return {"ok": True}

    def accept_request(self, user_uid):
        return {"ok": True}

    def remove(self, user_uid):
        return {"ok": True}

    def block(self, user_uid):
        return {"ok": True}

    def unblock(self, user_uid):
        return {"ok": True}

    def suggest_friends(self, phone_contacts=None):
        return [dict(SAMPLE_PROFILE, uid=FRIEND_UID, username="goiy")]

    def resolve_invite_token_from_username(self, username):
        return "invite-token-123"

    def fetch_user_by_invite_token(self, invite_token):
        return dict(SAMPLE_PROFILE, username="nguoimoi")


class FakeChat:
    def get_conversations(self):
        return [{
            "conversation_id": "conv1",
            "peer_uid": FRIEND_UID,
            "members": [ME_UID, FRIEND_UID],
            "unread_count": 1,
            "is_read": False,
            "latest_message": {"text": "Chào bạn", "sender_uid": FRIEND_UID},
        }]

    def get_messages(self, other_user_id=None, conversation_id=None, fetch_server=True):
        return [{
            "message_id": "msg1",
            "conversation_id": "conv1",
            "sender": FRIEND_UID,
            "text": "Chào bạn",
            "reactions": [],
        }]

    def send_message(self, receiver_uid, text=None, moment_uid=None):
        return {"ok": True}

    def send_moment(self, receiver_uid, moment_uid, text=None):
        return {"ok": True}

    def send_reaction(self, conversation_id, message_id, emoji, validate_receiver=True):
        return {"ok": True}

    def remove_reaction(self, conversation_id, message_id):
        return {"ok": True}

    def delete_message(self, conversation_uid, message_uid, validate_ownership=True):
        return {"ok": True}

    def mark_as_read(self, conversation_uid=None, other_user_id=None, send_read_receipt=True):
        return {"ok": True}

    async def listen_realtime(self, other_user_id, on_message):
        on_message({"sender": other_user_id, "text": "tin trực tiếp"})
        await asyncio.sleep(3600)


class FakeClient:
    def __init__(self):
        self.session = FakeSession()
        self.device = FakeDevice()
        self.user = FakeUser()
        self.moments = FakeMoments()
        self.friends = FakeFriends()
        self.chat = FakeChat()

    def is_authenticated(self):
        return True

    def login(self, email, password):
        return {"localId": ME_UID}

    def set_device(self, **kwargs):
        return None


def main():
    import backend.app as app_module

    app_module._client = FakeClient()

    from fastapi.testclient import TestClient

    c = TestClient(app_module.app)
    passed, failed = [], []

    def check(name, cond, extra=""):
        (passed if cond else failed).append(name)
        print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))

    def get(path, expect=200):
        r = c.get(path)
        check(f"GET {path}", r.status_code == expect, f"-> {r.status_code} {r.text[:120]}")
        return r

    def post(path, json_body=None, expect=200, **kw):
        r = c.post(path, json=json_body, **kw)
        check(f"POST {path}", r.status_code == expect, f"-> {r.status_code} {r.text[:120]}")
        return r

    get("/api/health")
    r = get("/api/status")
    check("status.authenticated", r.json().get("authenticated") is True)
    get("/api/me")
    get("/api/device")
    post("/api/device/auto", {"auto_emulate": True})
    post("/api/session/refresh", {})
    post("/api/session/sync", {})
    post("/api/profile/name", {"first_name": "T", "last_name": "QD"})
    post("/api/profile/birthdate", {"birthdate": "2008-01-01"})
    r = c.post("/api/profile/avatar", files={"file": ("a.png", PNG_1PX, "image/png")})
    check("POST /api/profile/avatar", r.status_code == 200, f"-> {r.status_code}")
    get("/api/users/by-username/tqd")
    get(f"/api/users/by-uid/{FRIEND_UID}")
    get(f"/api/users/by-uid/{FRIEND_UID}/moments")
    get("/api/users/tqd/moments")
    r = get("/api/feed")
    item = (r.json().get("items") or [{}])[0]
    check("feed normalize id", item.get("id") == "mom1")
    check("feed normalize views_count", item.get("views_count") == 3)
    get("/api/my-moments")
    get("/api/filters")
    post("/api/moments/viewed", {"moment_uid": "mom1"})
    r = get("/api/rollcall")
    check("rollcall items", len(r.json().get("items") or []) == 1)
    r = get("/api/presets")
    check("presets = 158", len(r.json().get("items") or []) == 158)
    r = c.post("/api/post", data={"caption": "hi"}, files={"image": ("a.png", PNG_1PX, "image/png")})
    check("POST /api/post (ảnh)", r.status_code == 200, f"-> {r.status_code} {r.text[:120]}")
    r = c.post(
        "/api/post",
        data={"caption": "hi", "recipients": f'["{FRIEND_UID}"]'},
        files={"image": ("a.png", PNG_1PX, "image/png")},
    )
    check("POST /api/post (recipients)", r.status_code == 200, f"-> {r.status_code}")
    post("/api/react", {"moment_uid": "mom1", "reaction": "🔥"})
    post("/api/comment", {"moment_uid": "mom1", "receiver_uid": FRIEND_UID, "text": "đẹp"})
    get("/api/moments/mom1/views")
    r = c.delete("/api/moments/mom1")
    check("DELETE /api/moments/mom1", r.status_code == 200, f"-> {r.status_code}")
    get("/api/friends")
    get("/api/friend-requests")
    get("/api/groups")
    post("/api/friends/request", {"username": "banbe"})
    post("/api/friends/accept", {"user_uid": FRIEND_UID})
    post("/api/friends/remove", {"user_uid": FRIEND_UID})
    post("/api/friends/block", {"user_uid": FRIEND_UID})
    post("/api/friends/unblock", {"user_uid": FRIEND_UID})
    r = post("/api/friends/suggest", {"phone_contacts": ["+84900000000"]})
    check("suggest items", len(r.json().get("items") or []) == 1)
    r = get("/api/invite/nguoimoi")
    check("invite link", r.json().get("link") == "https://locket.cam/nguoimoi")
    get("/api/conversations")
    get(f"/api/messages?other_user_id={FRIEND_UID}")
    r = get("/api/chat/reactions")
    check("chat reactions có ❤️", "❤️" in (r.json().get("items") or []))
    post("/api/messages/send", {"receiver_uid": FRIEND_UID, "text": "hi"})
    post("/api/messages/send-moment", {"receiver_uid": FRIEND_UID, "moment_uid": "mom1"})
    post("/api/messages/reaction", {"conversation_id": "conv1", "message_id": "msg1", "emoji": "❤️"})
    post("/api/messages/reaction/remove", {"conversation_id": "conv1", "message_id": "msg1"})
    post("/api/messages/delete", {"conversation_uid": "conv1", "message_uid": "msg1"})
    post("/api/messages/read", {"other_user_id": FRIEND_UID, "send_read_receipt": False})

    try:
        with c.websocket_connect(f"/api/chat/ws?other_user_id={FRIEND_UID}") as ws:
            data = ws.receive_json()
        check("WS /api/chat/ws nhận tin trực tiếp", data.get("data", {}).get("text") == "tin trực tiếp")
    except Exception as e:
        check("WS /api/chat/ws nhận tin trực tiếp", False, str(e)[:120])

    r = c.get("/")
    check("GET / (frontend)", r.status_code == 200 and "Locket" in r.text)

    post("/api/logout", {})
    r = c.get("/api/feed")
    check("sau logout feed -> 401", r.status_code == 401, f"-> {r.status_code}")

    print(f"\n===== {len(passed)} đạt, {len(failed)} lỗi =====")
    if failed:
        print("Lỗi:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
