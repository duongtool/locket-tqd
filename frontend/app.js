"use strict";
/* Locket Tqd - frontend: gọi API của backend (backend gọi thẳng Locket thật) */

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const state = {
  me: null,
  friends: [],
  friendByUid: {},
  currentChatUid: null,
  currentChatName: "",
  postFile: null,
  postKind: null,
  presets: [],
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch { /* ignore */ }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || `Lỗi ${res.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}
const apiJson = (path, body, method = "POST") =>
  api(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function fullName(u) {
  if (!u) return "Người dùng Locket";
  const n = `${u.first_name || ""} ${u.last_name || ""}`.trim();
  return n || (u.username ? `@${u.username}` : "Người dùng Locket");
}
function initialOf(u) { return (fullName(u).trim()[0] || "?").toUpperCase(); }
function avatarHtml(u, cls = "") {
  if (u && u.avatar_url) return `<img class="avatar-img ${cls}" src="${esc(u.avatar_url)}" alt="">`;
  return `<span class="avatar-fallback ${cls}">${esc(initialOf(u))}</span>`;
}
function timeAgo(epoch) {
  if (!epoch) return "";
  const s = Math.max(0, Math.floor(Date.now() / 1000) - epoch);
  if (s < 60) return "vừa xong";
  if (s < 3600) return `${Math.floor(s / 60)} phút trước`;
  if (s < 86400) return `${Math.floor(s / 3600)} giờ trước`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} ngày trước`;
  return new Date(epoch * 1000).toLocaleDateString("vi-VN");
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ================= Điều hướng ================= */
function showView(name) {
  ["feed", "post", "friends", "chat", "me"].forEach((v) =>
    $(`#view-${v}`).classList.toggle("hidden", v !== name));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.nav === name));
  if (name === "feed") loadFeed();
  if (name === "friends") loadFriends();
  if (name === "chat") loadConversations();
  if (name === "me") loadMe();
}
$$(".nav-btn").forEach((b) => b.addEventListener("click", () => showView(b.dataset.nav)));
$("#me-chip").addEventListener("click", () => showView("me"));

/* ================= Đăng nhập ================= */
async function checkStatus() {
  try {
    const st = await api("/api/status");
    if (st.authenticated) {
      await afterLogin();
      return;
    }
  } catch { /* rơi xuống màn hình đăng nhập */ }
  $("#login-view").classList.remove("hidden");
  $("#app").classList.add("hidden");
}

async function afterLogin() {
  $("#login-view").classList.add("hidden");
  $("#app").classList.remove("hidden");
  try {
    state.me = await api("/api/me");
    renderMeChip();
  } catch { state.me = null; }
  loadPresets();
  loadFriends(true);
  showView("feed");
}

function renderMeChip() {
  const me = state.me;
  if (!me) return;
  if (me.avatar_url) {
    $("#me-avatar").src = me.avatar_url;
    $("#me-avatar").classList.remove("hidden");
    $("#me-initial").classList.add("hidden");
  } else {
    $("#me-initial").textContent = initialOf(me);
  }
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-btn");
  const err = $("#login-error");
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "Đang đăng nhập…";
  try {
    await apiJson("/api/login", {
      email: $("#login-email").value.trim(),
      password: $("#login-password").value,
    });
    toast("Đăng nhập thành công 💛");
    await afterLogin();
  } catch (ex) {
    err.textContent = ex.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Đăng nhập";
  }
});

$("#logout-btn").addEventListener("click", async () => {
  await apiJson("/api/logout", {});
  location.reload();
});

/* ================= Feed ================= */
function captionPillHtml(m) {
  const ov = (m.overlays || []).find((o) => o && (o.alt_text || o.data));
  let text = m.caption || "";
  let colors = null, icon = "", textColor = "#fff";
  if (ov) {
    const d = ov.data || ov;
    text = text || d.alt_text || ov.alt_text || "";
    colors = d.colors || ov.colors || null;
    icon = d.icon || ov.icon || "";
    textColor = d.text_color || ov.text_color || "#fff";
  }
  if (!text && !icon) return "";
  const bg = colors && colors.length
    ? `background:linear-gradient(90deg,${colors.join(",")});`
    : "";
  return `<div class="caption-pill" style="${bg}color:${esc(textColor)}">${esc(icon)} ${esc(text)}</div>`;
}

function momentCard(m) {
  const author = m.user || state.friendByUid[m.user_uid] || { uid: m.user_uid };
  const media = m.video_url
    ? `<video src="${esc(m.video_url)}" poster="${esc(m.thumbnail_url || "")}" controls playsinline></video>`
    : `<img src="${esc(m.thumbnail_url || "")}" alt="" loading="lazy">`;
  const el = document.createElement("article");
  el.className = "moment-card";
  el.innerHTML = `
    <div class="moment-meta">${avatarHtml(author)}
      <div><div class="moment-author">${esc(fullName(author))}</div>
      <div class="moment-time">${esc(timeAgo(m.created_at))}</div></div>
    </div>
    <div class="moment-media">${media}${captionPillHtml(m)}</div>
    <div class="moment-actions">
      ${["❤️", "🔥", "🥰", "🥳", "🥺"].map((e) => `<button class="react-btn" data-react="${e}">${e}</button>`).join("")}
    </div>
    <form class="moment-comment">
      <input type="text" placeholder="Bình luận…" maxlength="200">
      <button type="submit" title="Gửi bình luận">💬</button>
    </form>`;
  el.querySelectorAll("[data-react]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await apiJson("/api/react", { moment_uid: m.id, reaction: b.dataset.react });
        toast(`Đã thả ${b.dataset.react}`);
      } catch (ex) { toast(ex.message); }
    }));
  el.querySelector(".moment-comment").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = ev.target.querySelector("input");
    const text = input.value.trim();
    if (!text) return;
    const receiver = m.user_uid || (author && author.uid);
    if (!receiver) { toast("Không rõ chủ bài đăng để bình luận"); return; }
    try {
      await apiJson("/api/comment", { moment_uid: m.id, receiver_uid: receiver, text });
      input.value = "";
      toast("Đã gửi bình luận 💬");
    } catch (ex) { toast(ex.message); }
  });
  const img = el.querySelector(".moment-media img");
  if (img) img.addEventListener("click", () => openLightbox(m.thumbnail_url, null));
  return el;
}

async function loadFeed() {
  const list = $("#feed-list");
  list.innerHTML = "";
  $("#feed-empty").classList.add("hidden");
  try {
    const data = await api("/api/feed");
    const items = data.items || [];
    if (!items.length) $("#feed-empty").classList.remove("hidden");
    items.forEach((m) => list.appendChild(momentCard(m)));
  } catch (ex) {
    toast(ex.message);
  }
}
$("#feed-refresh").addEventListener("click", loadFeed);

/* ================= Đăng bài ================= */
async function loadPresets() {
  try {
    const data = await api("/api/presets");
    state.presets = data.items || [];
    const sel = $("#post-preset");
    sel.innerHTML = "";
    const groups = {};
    state.presets.forEach((p) => {
      const sec = p.section || "Khác";
      (groups[sec] = groups[sec] || []).push(p);
    });
    Object.entries(groups).forEach(([sec, arr]) => {
      const g = document.createElement("optgroup");
      g.label = sec;
      arr.forEach((p) => {
        const o = document.createElement("option");
        o.value = p.id;
        o.textContent = `${p.icon ? p.icon + " " : ""}${p.text || p.id}`;
        g.appendChild(o);
      });
      sel.appendChild(g);
    });
    sel.value = "standard";
  } catch { /* không có preset vẫn đăng được */ }
}

function currentPreset() {
  return state.presets.find((p) => p.id === $("#post-preset").value);
}
function refreshPostPill() {
  const pill = $("#post-caption-pill");
  const preset = currentPreset();
  const caption = $("#post-caption").value.trim();
  const useCustom = $("#post-custom-colors").checked;
  const text = caption || (preset && preset.text) || "";
  const icon = preset && preset.icon ? preset.icon : "";
  if (!text && !icon && !useCustom) { pill.classList.add("hidden"); return; }
  let colors = preset && preset.colors && preset.colors.length ? preset.colors : null;
  let textColor = (preset && preset.text_color) || "#FFFFFF";
  if (useCustom) {
    colors = [$("#post-color1").value, $("#post-color2").value];
    textColor = $("#post-textcolor").value;
  }
  pill.style.background = colors ? `linear-gradient(90deg,${colors.join(",")})` : "linear-gradient(90deg,#5B5BD6,#9B5DE5)";
  pill.style.color = textColor;
  pill.textContent = `${icon} ${text}`.trim();
  pill.classList.remove("hidden");
}
["post-caption", "post-preset", "post-color1", "post-color2", "post-textcolor", "post-custom-colors"]
  .forEach((id) => $("#" + id).addEventListener("input", refreshPostPill));

$("#post-pick").addEventListener("click", () => $("#post-file").click());
$("#post-stage").addEventListener("click", () => { if (!state.postFile) $("#post-file").click(); });
$("#post-file").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  state.postFile = f;
  const url = URL.createObjectURL(f);
  const isVideo = f.type.startsWith("video");
  state.postKind = isVideo ? "video" : "image";
  $("#post-placeholder").classList.add("hidden");
  $("#post-preview-img").classList.toggle("hidden", isVideo);
  $("#post-preview-video").classList.toggle("hidden", !isVideo);
  if (isVideo) $("#post-preview-video").src = url; else $("#post-preview-img").src = url;
  refreshPostPill();
});

$("#post-submit").addEventListener("click", async () => {
  const err = $("#post-error"), ok = $("#post-ok");
  err.textContent = ""; ok.textContent = "";
  if (!state.postFile) { err.textContent = "Bạn chưa chọn ảnh hoặc video."; return; }
  const preset = currentPreset();
  const fd = new FormData();
  fd.append(state.postKind === "video" ? "video" : "image", state.postFile);
  fd.append("caption", $("#post-caption").value.trim());
  fd.append("note_type", $("#post-preset").value || "standard");
  if (preset && preset.icon) fd.append("icon", preset.icon);
  if ($("#post-custom-colors").checked) {
    fd.append("colors", JSON.stringify([$("#post-color1").value, $("#post-color2").value]));
    fd.append("text_color", $("#post-textcolor").value);
  }
  fd.append("is_private", $("#post-private").checked ? "true" : "false");
  const btn = $("#post-submit");
  btn.disabled = true;
  btn.textContent = state.postKind === "video" ? "Đang nén và tải video lên…" : "Đang gửi…";
  try {
    await api("/api/post", { method: "POST", body: fd });
    ok.textContent = "Đã đăng khoảnh khắc thành công 💛";
    state.postFile = null;
    $("#post-file").value = "";
    $("#post-preview-img").classList.add("hidden");
    $("#post-preview-video").classList.add("hidden");
    $("#post-placeholder").classList.remove("hidden");
    $("#post-caption").value = "";
    refreshPostPill();
    showView("feed");
  } catch (ex) {
    err.textContent = ex.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Gửi tới bạn bè";
  }
});

/* ================= Bạn bè ================= */
async function loadFriends(silent = false) {
  try {
    const data = await api("/api/friends");
    state.friends = data.items || [];
    state.friendByUid = {};
    state.friends.forEach((f) => { if (f.uid) state.friendByUid[f.uid] = f; });
    const list = $("#friends-list");
    list.innerHTML = state.friends.length ? "" : `<p class="empty">Chưa có bạn bè nào.</p>`;
    state.friends.forEach((f) => {
      const row = document.createElement("div");
      row.className = "person";
      row.innerHTML = `${avatarHtml(f)}<div class="person-main">
        <div class="person-name">${esc(fullName(f))}</div>
        <div class="person-sub">${f.username ? "@" + esc(f.username) : ""}</div></div>
        <button class="btn-ghost" data-remove="${esc(f.uid)}">Huỷ kết bạn</button>`;
      row.querySelector("[data-remove]").addEventListener("click", async (ev) => {
        ev.stopPropagation();
        if (!confirm(`Huỷ kết bạn với ${fullName(f)}?`)) return;
        try { await apiJson("/api/friends/remove", { user_uid: f.uid }); loadFriends(); }
        catch (ex) { toast(ex.message); }
      });
      list.appendChild(row);
    });
  } catch (ex) { if (!silent) toast(ex.message); }
  loadRequests();
}

function extractRequestUsers(payload) {
  const out = [];
  const walk = (v) => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") {
      if ((v.uid || v.id) && (v.first_name || v.username || v.last_name)) out.push(v);
      else Object.values(v).forEach(walk);
    }
  };
  walk(payload);
  const seen = new Set();
  return out.filter((u) => { const k = u.uid || u.id; if (seen.has(k)) return false; seen.add(k); return true; });
}

async function loadRequests() {
  try {
    const data = await api("/api/friend-requests");
    const users = extractRequestUsers(data).filter((u) => !state.friendByUid[u.uid || u.id]);
    const head = $("#requests-head"), list = $("#requests-list");
    list.innerHTML = "";
    head.classList.toggle("hidden", !users.length);
    users.forEach((raw) => {
      const u = { uid: raw.uid || raw.id, first_name: raw.first_name || "", last_name: raw.last_name || "", username: raw.username, avatar_url: raw.profile_picture_url || raw.avatar_url };
      const row = document.createElement("div");
      row.className = "person";
      row.innerHTML = `${avatarHtml(u)}<div class="person-main">
        <div class="person-name">${esc(fullName(u))}</div>
        <div class="person-sub">${u.username ? "@" + esc(u.username) : "Lời mời kết bạn"}</div></div>
        <button class="btn-gold small" data-accept="${esc(u.uid)}">Đồng ý</button>`;
      row.querySelector("[data-accept]").addEventListener("click", async () => {
        try { await apiJson("/api/friends/accept", { user_uid: u.uid }); toast("Đã kết bạn 💛"); loadFriends(); }
        catch (ex) { toast(ex.message); }
      });
      list.appendChild(row);
    });
  } catch { /* im lặng nếu API không trả lời mời */ }
}

$("#add-friend-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#friend-error"), ok = $("#friend-ok");
  err.textContent = ""; ok.textContent = "";
  const username = $("#add-friend-username").value.trim().replace(/^@/, "");
  if (!username) return;
  try {
    await apiJson("/api/friends/request", { username });
    ok.textContent = `Đã gửi lời mời kết bạn tới @${username}`;
    $("#add-friend-username").value = "";
  } catch (ex) { err.textContent = ex.message; }
});

/* ================= Tin nhắn ================= */
function convOtherUid(c) {
  if (!c || typeof c !== "object") return null;
  const meUid = state.me && state.me.uid;
  const parts = c.participants || c.participant_uids || c.members || [];
  if (Array.isArray(parts) && parts.length) {
    const other = parts.map((p) => (typeof p === "string" ? p : p.uid || p.id)).find((x) => x && x !== meUid);
    if (other) return other;
  }
  return c.other_user_uid || c.other_uid || c.receiver_uid || c.friend_uid || null;
}
function convTitle(c, otherUid) {
  const f = state.friendByUid[otherUid];
  if (f) return fullName(f);
  return c.title || c.name || (otherUid ? "Bạn bè Locket" : "Cuộc trò chuyện");
}
function convLastText(c) {
  const m = c.last_message || c.latest_message || {};
  return m.text || m.body || c.last_text || "";
}

async function loadConversations() {
  $("#chat-box").classList.add("hidden");
  const list = $("#conv-list");
  list.classList.remove("hidden");
  list.innerHTML = "";
  try {
    const data = await api("/api/conversations");
    const items = data.items || [];
    if (!items.length) list.innerHTML = `<p class="empty">Chưa có cuộc trò chuyện nào.</p>`;
    items.forEach((c) => {
      const otherUid = convOtherUid(c);
      const row = document.createElement("button");
      row.className = "person";
      const f = state.friendByUid[otherUid];
      row.innerHTML = `${avatarHtml(f || {})}<div class="person-main">
        <div class="person-name">${esc(convTitle(c, otherUid))}</div>
        <div class="person-sub">${esc(convLastText(c))}</div></div>`;
      row.addEventListener("click", () => { if (otherUid) openChat(otherUid, convTitle(c, otherUid)); else toast("Chưa rõ người trò chuyện"); });
      list.appendChild(row);
    });
    if (!items.length && state.friends.length) {
      state.friends.forEach((f) => {
        const row = document.createElement("button");
        row.className = "person";
        row.innerHTML = `${avatarHtml(f)}<div class="person-main">
          <div class="person-name">${esc(fullName(f))}</div>
          <div class="person-sub">Bắt đầu trò chuyện</div></div>`;
        row.addEventListener("click", () => openChat(f.uid, fullName(f)));
        list.appendChild(row);
      });
    }
  } catch (ex) { toast(ex.message); }
}

async function openChat(uid, name) {
  state.currentChatUid = uid;
  state.currentChatName = name;
  $("#conv-list").classList.add("hidden");
  $("#chat-box").classList.remove("hidden");
  $("#chat-title").textContent = name;
  await loadMessages();
}
$("#chat-back").addEventListener("click", loadConversations);

async function loadMessages() {
  const box = $("#chat-messages");
  box.innerHTML = "";
  try {
    const data = await api(`/api/messages?other_user_id=${encodeURIComponent(state.currentChatUid)}`);
    const items = data.items || [];
    const meUid = state.me && state.me.uid;
    items.forEach((m) => {
      const sender = m.sender || m.sender_uid || m.from || "";
      const text = m.text || m.body || m.message || "";
      if (!text) return;
      const b = document.createElement("div");
      b.className = "bubble" + (sender && meUid && sender === meUid ? " mine" : "");
      b.textContent = text;
      box.appendChild(b);
    });
    box.scrollTop = box.scrollHeight;
  } catch (ex) { toast(ex.message); }
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || !state.currentChatUid) return;
  try {
    await apiJson("/api/messages/send", { receiver_uid: state.currentChatUid, text });
    input.value = "";
    loadMessages();
  } catch (ex) { toast(ex.message); }
});

/* ================= Trang cá nhân ================= */
async function loadMe() {
  try {
    state.me = await api("/api/me");
    const me = state.me;
    renderMeChip();
    if (me.avatar_url) {
      $("#profile-avatar").src = me.avatar_url;
      $("#profile-avatar").classList.remove("hidden");
      $("#profile-initial").classList.add("hidden");
    } else {
      $("#profile-initial").textContent = initialOf(me);
    }
    $("#profile-name").textContent = fullName(me);
    $("#profile-username").textContent = me.username ? `@${me.username}` : "";
    const st = await api("/api/status");
    $("#profile-email").textContent = st.email || "";
    $("#edit-first").value = me.first_name || "";
    $("#edit-last").value = me.last_name || "";
  } catch (ex) { toast(ex.message); }
  try {
    const data = await api("/api/my-moments");
    const grid = $("#my-moments");
    grid.innerHTML = "";
    (data.items || []).forEach((m) => {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.innerHTML = `${m.video_url
        ? `<video src="${esc(m.video_url)}" poster="${esc(m.thumbnail_url || "")}" muted playsinline></video>`
        : `<img src="${esc(m.thumbnail_url || "")}" alt="">`}
        <button class="del" title="Xoá bài">✕</button>`;
      cell.querySelector(".del").addEventListener("click", async (ev) => {
        ev.stopPropagation();
        if (!confirm("Xoá khoảnh khắc này?")) return;
        try { await api(`/api/moments/${encodeURIComponent(m.id)}`, { method: "DELETE" }); loadMe(); }
        catch (ex) { toast(ex.message); }
      });
      cell.addEventListener("click", () => openLightbox(m.thumbnail_url, m.video_url));
      grid.appendChild(cell);
    });
  } catch { /* bỏ qua nếu chưa tải được */ }
}

$("#name-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await apiJson("/api/profile/name", {
      first_name: $("#edit-first").value.trim(),
      last_name: $("#edit-last").value.trim(),
    });
    $("#me-ok").textContent = "Đã cập nhật tên.";
    loadMe();
  } catch (ex) { $("#me-error").textContent = ex.message; }
});

$("#avatar-file").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  try {
    await api("/api/profile/avatar", { method: "POST", body: fd });
    $("#me-ok").textContent = "Đã đổi ảnh đại diện.";
    loadMe();
  } catch (ex) { $("#me-error").textContent = ex.message; }
});

/* ================= Lightbox ================= */
function openLightbox(img, video) {
  const lb = $("#lightbox");
  $("#lightbox-img").classList.toggle("hidden", !!video);
  $("#lightbox-video").classList.toggle("hidden", !video);
  if (video) $("#lightbox-video").src = video; else $("#lightbox-img").src = img || "";
  lb.classList.remove("hidden");
}
$("#lightbox").addEventListener("click", () => {
  $("#lightbox").classList.add("hidden");
  $("#lightbox-video").pause();
});

/* ================= Khởi động ================= */
checkStatus();
