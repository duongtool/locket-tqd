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
  currentConversationId: null,
  chatSocket: null,
  chatReactions: [],
  postFile: null,
  postKind: null,
  feedItems: [],
  camStream: null,
  camRecorder: null,
  camChunks: [],
  camTimerInt: null,
  presets: [],
  filtersLoaded: false,
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
  if (name === "post") { loadFilters(); renderRecipients(); startCamera(); } else { stopCamera(); }
  if (name === "friends") loadFriends();
  if (name === "chat") loadConversations();
  if (name === "me") { loadMe(); loadDevice(); }
}
$$(".nav-btn").forEach((b) => b.addEventListener("click", () => showView(b.dataset.nav)));
$("#me-chip").addEventListener("click", () => showView("me"));

/* ================= Đăng nhập ================= */
async function checkStatus() {
  try {
    const st = await api("/api/status");
    if (st.authenticated) { await afterLogin(); return; }
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
  closeChatSocket();
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
  const bg = colors && colors.length ? `background:linear-gradient(90deg,${colors.join(",")});` : "";
  return `<div class="caption-pill" style="${bg}color:${esc(textColor)}">${esc(icon)} ${esc(text)}</div>`;
}

function momentCard(m, inDetail = false) {
  const author = m.user || state.friendByUid[m.user_uid] || { uid: m.user_uid };
  const fullImg = m.image_url || m.thumbnail_url || "";
  const media = m.video_url
    ? `<video src="${esc(m.video_url)}" poster="${esc(fullImg)}" controls playsinline></video>`
    : `<img src="${esc(fullImg)}" alt="" loading="lazy">`;
  const viewsLine = m.views_count != null
    ? `<div class="moment-views">👀 ${esc(m.views_count)} lượt xem</div>` : "";
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
      <button class="react-btn" data-share title="Chia sẻ vào tin nhắn">↗️</button>
    </div>
    <div class="share-picker hidden"></div>
    ${viewsLine}
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
  const picker = el.querySelector(".share-picker");
  el.querySelector("[data-share]").addEventListener("click", () => {
    picker.classList.toggle("hidden");
    if (picker.innerHTML) return;
    if (!state.friends.length) { picker.innerHTML = `<span class="muted-note">Chưa có bạn bè để chia sẻ.</span>`; return; }
    state.friends.forEach((f) => {
      const b = document.createElement("button");
      b.className = "chip";
      b.textContent = fullName(f);
      b.addEventListener("click", async () => {
        try {
          await apiJson("/api/messages/send-moment", { receiver_uid: f.uid, moment_uid: m.id });
          toast(`Đã chia sẻ tới ${fullName(f)} 💛`);
          picker.classList.add("hidden");
        } catch (ex) { toast(ex.message); }
      });
      picker.appendChild(b);
    });
  });
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
  const mediaEl = el.querySelector(".moment-media img, .moment-media video");
  if (mediaEl) mediaEl.addEventListener("click", () => {
    if (!ghostMomentsOn()) {
      apiJson("/api/moments/viewed", { moment_uid: m.id }).catch(() => {});
    }
    if (!inDetail) openLightbox(m.image_url || m.thumbnail_url, m.video_url);
  });
  return el;
}

function ghostMomentsOn() {
  const box = $("#ghost-moments");
  return box ? box.checked : localStorage.getItem("ghostMoments") === "1";
}
(function initGhostMoments() {
  const box = $("#ghost-moments");
  if (!box) return;
  box.checked = localStorage.getItem("ghostMoments") === "1";
  box.addEventListener("change", () => {
    localStorage.setItem("ghostMoments", box.checked ? "1" : "0");
    toast(box.checked ? "Đã bật chặn đã xem 🕶" : "Đã tắt chặn đã xem");
  });
})();

async function loadFeed(forceFresh = false) {
  const grid = $("#feed-grid");
  if (!state.feedItems.length) {
    grid.innerHTML = `<p class="empty" style="grid-column:1/-1">Đang tải khoảnh khắc…</p>`;
  }
  $("#feed-empty").classList.add("hidden");
  // Lớp 1: trang mới nhất về rất nhanh, hiện lên ngay cho khỏi phải chờ.
  try {
    const first = await api("/api/feed");
    if ((first.items || []).length >= state.feedItems.length) {
      state.feedItems = first.items || [];
      buildFeedFilter();
      renderFeedGrid();
    }
  } catch (ex) {
    if (!state.feedItems.length) grid.innerHTML = "";
    toast(ex.message);
  }
  // Lớp 2: toàn bộ lịch sử tải ở nền xong thì tự thay vào, giữ nguyên vị trí cuộn.
  const countEl = $("#feed-count");
  try {
    if (countEl && countEl.textContent) countEl.textContent += " · đang tải thêm toàn bộ…";
    const full = await api(forceFresh ? "/api/feed/full?fresh=1" : "/api/feed/full");
    if (full.stats) state.feedStats = full.stats;
    if ((full.items || []).length >= state.feedItems.length) {
      const y = window.scrollY;
      state.feedItems = full.items;
      renderFeedGrid();
      window.scrollTo(0, y);
    }
  } catch { /* giữ bản trang đầu nếu lớp 2 lỗi */ } finally {
    buildFeedFilter();
  }
}

function feedAuthorUid(m) {
  return m.user_uid || (m.user && m.user.uid) || null;
}

function buildFeedFilter() {
  const sel = $("#feed-filter");
  const prev = sel.value || "all";
  const seen = new Map();
  if (state.me && state.me.uid) seen.set(state.me.uid, "Của tôi");
  state.friends.forEach((f) => { if (f.uid) seen.set(f.uid, fullName(f)); });
  state.feedItems.forEach((m) => {
    const uid = feedAuthorUid(m);
    if (uid && !seen.has(uid)) {
      const u = m.user || state.friendByUid[uid];
      seen.set(uid, u ? fullName(u) : "Người dùng Locket");
    }
  });
  const myUid = state.me && state.me.uid;
  sel.innerHTML = `<option value="all">Mọi người ▾</option>` +
    [...seen.entries()].map(([uid, name]) =>
      `<option value="${esc(uid)}">${esc(uid === myUid ? "Của tôi" : name)}</option>`).join("");
  sel.value = prev === "all" || seen.has(prev) ? prev : "all";
}

function renderFeedGrid() {
  const grid = $("#feed-grid");
  const selVal = $("#feed-filter").value || "all";
  const items = state.feedItems.filter((m) => selVal === "all" || feedAuthorUid(m) === selVal);
  const countEl = $("#feed-count");
  countEl.textContent = items.length ? `${items.length} khoảnh khắc` : "";
  if (selVal === "all" && state.feedStats) {
    if (state.feedStats.complete === false) {
      countEl.textContent += " · có thể chưa đủ, bấm ⟳ thử lại";
    }
    const pu = state.feedStats.per_user || {};
    const lines = Object.entries(pu).map(
      ([uid, n]) => `${fullName(state.friendByUid[uid] || { uid })}: ${n} khoảnh khắc`
    );
    countEl.title = `Nguồn mới nhất: ${state.feedStats.latest} · quét feed thêm: ${state.feedStats.scan} · quét trò chuyện thêm: ${state.feedStats.firestore ?? "?"} (trong ${state.feedStats.conversations ?? "?"} cuộc trò chuyện)\n${lines.join("\n")}`;
  }
  grid.innerHTML = "";
  $("#feed-empty").classList.toggle("hidden", items.length > 0);
  items.forEach((m) => {
    const author = m.user || state.friendByUid[feedAuthorUid(m)] || {};
    const cell = document.createElement("button");
    cell.className = "grid-cell";
    cell.innerHTML = `<img src="${esc(m.thumbnail_url || m.image_url || "")}" alt="" loading="lazy" decoding="async">
      ${m.video_url ? `<span class="video-badge">▶ video</span>` : ""}
      <span class="cell-author">${esc(fullName(author))}</span>`;
    cell.addEventListener("click", () => openMomentDetail(m));
    grid.appendChild(cell);
  });
}
$("#feed-filter").addEventListener("change", renderFeedGrid);

function openMomentDetail(m) {
  const body = $("#moment-detail-body");
  body.innerHTML = "";
  body.appendChild(momentCard(m, true));
  $("#moment-detail").classList.remove("hidden");
  if (!ghostMomentsOn()) {
    apiJson("/api/moments/viewed", { moment_uid: m.id }).catch(() => {});
  }
}
function closeMomentDetail() {
  $("#moment-detail").classList.add("hidden");
  $("#moment-detail-body").innerHTML = "";
}
$("#moment-detail-close").addEventListener("click", closeMomentDetail);
$("#moment-detail").addEventListener("click", (e) => {
  if (e.target.id === "moment-detail") closeMomentDetail();
});
$("#feed-refresh").addEventListener("click", () => loadFeed(true));

$("#rollcall-btn").addEventListener("click", async () => {
  const strip = $("#rollcall-strip");
  if (!strip.classList.contains("hidden")) { strip.classList.add("hidden"); return; }
  strip.innerHTML = `<span class="muted-note">Đang tải Rollcall tuần này…</span>`;
  strip.classList.remove("hidden");
  try {
    const data = await api("/api/rollcall");
    const items = data.items || [];
    strip.innerHTML = items.length ? "" : `<span class="muted-note">Tuần này chưa có bài Rollcall nào.</span>`;
    items.forEach((m) => {
      const author = m.user || state.friendByUid[m.user_uid] || {};
      const cell = document.createElement("div");
      cell.className = "rc-cell";
      cell.innerHTML = `${m.video_url
        ? `<video src="${esc(m.video_url)}" poster="${esc(m.thumbnail_url || "")}" muted playsinline></video>`
        : `<img src="${esc(m.thumbnail_url || "")}" alt="">`}
        <div class="rc-name">${esc(fullName(author))}</div>`;
      cell.addEventListener("click", () => openLightbox(m.image_url || m.thumbnail_url, m.video_url));
      strip.appendChild(cell);
    });
  } catch (ex) { strip.innerHTML = `<span class="muted-note">${esc(ex.message)}</span>`; }
});

/* ================= Đăng bài ================= */
// Các nhãn động nhóm General (nhạc, thời tiết, giờ...) trong thư viện không
// có sẵn chữ/biểu tượng vì app Locket tự điền nội dung khi hiển thị, nên ở
// đây đặt tên tiếng Việt + biểu tượng đại diện để người dùng thấy và chọn được.
const PRESET_NAMES = {
  standard: ["✏️", "Chú thích thường"],
  review: ["⭐", "Đánh giá"],
  music: ["🎵", "Âm nhạc"],
  location: ["📍", "Vị trí"],
  weather: ["🌤️", "Thời tiết"],
  time: ["🕐", "Thời gian"],
  streak: ["🔥", "Chuỗi ngày (streak)"],
  star_sign: ["♈", "Cung hoàng đạo"],
  poll: ["📊", "Bình chọn"],
  locket_count: ["💛", "Đếm số Locket"],
  colors: ["🎨", "Màu sắc"],
  color_palette: ["🖍️", "Bảng màu"],
};
function presetDisplay(p) {
  const named = PRESET_NAMES[p.id];
  return {
    icon: p.icon || (named ? named[0] : ""),
    name: p.text || (named ? named[1] : p.id.replace(/_/g, " ")),
  };
}

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
        const d = presetDisplay(p);
        const o = document.createElement("option");
        o.value = p.id;
        o.textContent = `${d.icon ? d.icon + " " : ""}${d.name}`;
        g.appendChild(o);
      });
      sel.appendChild(g);
    });
    sel.value = "standard";
  } catch { /* không có preset vẫn đăng được */ }
}

async function loadFilters() {
  if (state.filtersLoaded) return;
  state.filtersLoaded = true;
  const box = $("#filters-box");
  try {
    const data = await api("/api/filters");
    const raw = data && (data.filters || data.data || data);
    const arr = Array.isArray(raw) ? raw : (raw && typeof raw === "object" ? Object.values(raw) : []);
    const names = arr.map((f) => (typeof f === "string" ? f : f.name || f.id || f.title)).filter(Boolean);
    box.innerHTML = names.length
      ? names.slice(0, 40).map((n) => `<span class="chip">${esc(n)}</span>`).join("")
      : `<span class="muted-note">Không lấy được danh sách bộ lọc.</span>`;
  } catch { box.innerHTML = `<span class="muted-note">Không lấy được danh sách bộ lọc.</span>`; }
}

async function renderRecipients() {
  const box = $("#post-recipients");
  if (!state.friends.length) {
    try { await loadFriends(true); } catch { /* bỏ qua */ }
  }
  box.innerHTML = state.friends.length
    ? state.friends.map((f) =>
        `<label class="check-field"><input type="checkbox" value="${esc(f.uid)}" class="recipient-check"> ${esc(fullName(f))}</label>`).join("")
    : `<span class="muted-note">Chưa có bạn bè.</span>`;
}

function currentPreset() {
  return state.presets.find((p) => p.id === $("#post-preset").value);
}
function refreshPostPill() {
  const pill = $("#post-caption-pill");
  const preset = currentPreset();
  const caption = $("#post-caption").value.trim();
  const useCustom = $("#post-custom-colors").checked;
  let text = caption || (preset && preset.text) || "";
  let icon = preset && preset.icon ? preset.icon : "";
  // Nhãn động (General) không có chữ sẵn: hiện tên kiểu nhãn để thấy đã chọn.
  if (!text && !icon && preset) {
    const d = presetDisplay(preset);
    text = d.name;
    icon = d.icon;
  }
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

function setPostFile(f) {
  state.postFile = f;
  const url = URL.createObjectURL(f);
  // Nhận diện video theo cả kiểu MIME lẫn đuôi file (có file trình duyệt
  // không báo MIME, trước đây bị hiểu nhầm thành ảnh nên xem trước sai).
  const isVideo = (f.type || "").startsWith("video")
    || /\.(mp4|mov|webm|mkv|avi|m4v|3gp)$/i.test(f.name || "");
  state.postKind = isVideo ? "video" : "image";
  $("#post-placeholder").classList.add("hidden");
  $("#cam-preview").classList.add("hidden");
  $("#post-clear").classList.remove("hidden");
  $("#post-preview-img").classList.toggle("hidden", isVideo);
  $("#post-preview-video").classList.toggle("hidden", !isVideo);
  if (isVideo) {
    const pv = $("#post-preview-video");
    pv.src = url;
    pv.muted = true;
    pv.loop = true;
    pv.play().catch(() => { /* trình duyệt chặn tự phát thì vẫn có nút phát */ });
  } else {
    $("#post-preview-img").src = url;
  }
  refreshPostPill();
}

function clearPostFile() {
  state.postFile = null;
  state.postKind = null;
  $("#post-file").value = "";
  $("#post-preview-img").classList.add("hidden");
  const pv = $("#post-preview-video");
  pv.classList.add("hidden");
  try { pv.pause(); } catch { /* ignore */ }
  pv.removeAttribute("src");
  $("#post-clear").classList.add("hidden");
  refreshPostPill();
  startCamera();
}
$("#post-clear").addEventListener("click", clearPostFile);

$("#post-file").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) { stopCamera(); setPostFile(f); }
});

/* ---------- Camera trực tiếp ngay trong khung Đăng ----------
   Khung lớn là camera trực tiếp; nút tròn ở giữa chụp ảnh, nút bên phải
   quay video (có thu tiếng), nút bên trái tải file có sẵn lên. */
function showCamFallback(msg) {
  const t = $("#post-placeholder-text");
  if (t) t.textContent = msg;
  $("#post-placeholder").classList.remove("hidden");
}

async function startCamera() {
  if (state.postFile) return;
  const pv = $("#cam-preview");
  pv.classList.remove("hidden");
  if (state.camStream) { $("#post-placeholder").classList.add("hidden"); return; }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showCamFallback("Trình duyệt này không hỗ trợ camera (cần https hoặc localhost). Hãy dùng nút Tải file lên.");
    return;
  }
  try {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: true,
      });
    } catch {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
    }
    state.camStream = stream;
    pv.srcObject = stream;
    pv.muted = true;
    $("#post-placeholder").classList.add("hidden");
  } catch (ex) {
    showCamFallback("Không mở được camera: " + ex.message + " — hãy dùng nút Tải file lên.");
  }
}

function stopCamera() {
  if (state.camRecorder && state.camRecorder.state !== "inactive") {
    try { state.camRecorder.stop(); } catch { /* ignore */ }
  }
  state.camRecorder = null;
  if (state.camTimerInt) { clearInterval(state.camTimerInt); state.camTimerInt = null; }
  if (state.camStream) {
    state.camStream.getTracks().forEach((t) => t.stop());
    state.camStream = null;
  }
  const rb = $("#cam-record-btn");
  if (rb) {
    rb.classList.remove("recording");
    const sp = rb.querySelector("span");
    if (sp) sp.textContent = "Quay video";
  }
  const tm = $("#cam-timer");
  if (tm) tm.textContent = "";
}

$("#cam-shutter").addEventListener("click", () => {
  const pv = $("#cam-preview");
  if (!state.camStream || !pv.videoWidth) { toast("Camera chưa sẵn sàng"); return; }
  const canvas = document.createElement("canvas");
  canvas.width = pv.videoWidth;
  canvas.height = pv.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.translate(canvas.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(pv, 0, 0);
  canvas.toBlob((blob) => {
    if (!blob) { toast("Chụp thất bại"); return; }
    stopCamera();
    setPostFile(new File([blob], "camera-photo.jpg", { type: "image/jpeg" }));
    toast("Đã chụp ảnh 📷");
  }, "image/jpeg", 0.92);
});

$("#cam-record-btn").addEventListener("click", () => {
  if (state.camRecorder && state.camRecorder.state === "recording") {
    state.camRecorder.stop();
    return;
  }
  if (!state.camStream) { toast("Camera chưa mở"); startCamera(); return; }
  if (typeof MediaRecorder === "undefined") {
    toast("Trình duyệt này không hỗ trợ quay video.");
    return;
  }
  const candidates = [
    "video/mp4;codecs=avc1.42001f,mp4a.40.2",
    "video/mp4",
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm",
  ];
  const mime = candidates.find((t) => MediaRecorder.isTypeSupported(t)) || "";
  const rec = new MediaRecorder(state.camStream, mime ? { mimeType: mime } : undefined);
  state.camChunks = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) state.camChunks.push(e.data); };
  rec.onstop = () => {
    if (state.camTimerInt) { clearInterval(state.camTimerInt); state.camTimerInt = null; }
    $("#cam-timer").textContent = "";
    const type = rec.mimeType || mime || "video/webm";
    const ext = type.includes("mp4") ? "mp4" : "webm";
    const blob = new Blob(state.camChunks, { type });
    stopCamera();
    setPostFile(new File([blob], `camera-video.${ext}`, { type }));
    toast("Đã quay xong video 🎥");
  };
  state.camRecorder = rec;
  rec.start(250);
  const rb = $("#cam-record-btn");
  rb.classList.add("recording");
  rb.querySelector("span").textContent = "Dừng quay";
  const t0 = Date.now();
  state.camTimerInt = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    $("#cam-timer").textContent = `● Đang quay ${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")} (có tiếng)`;
  }, 500);
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
  const isPrivate = $("#post-private").checked;
  fd.append("is_private", isPrivate ? "true" : "false");
  if (!isPrivate) {
    const chosen = $$(".recipient-check").filter((c) => c.checked).map((c) => c.value);
    if (chosen.length) fd.append("recipients", JSON.stringify(chosen));
  }
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
    $("#post-clear").classList.add("hidden");
    $("#post-caption").value = "";
    $$(".recipient-check").forEach((c) => (c.checked = false));
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
function personRow(u, actionsHtml) {
  const row = document.createElement("div");
  row.className = "person";
  row.innerHTML = `${avatarHtml(u)}<div class="person-main">
    <div class="person-name">${esc(fullName(u))}</div>
    <div class="person-sub">${u.username ? "@" + esc(u.username) : ""}</div></div>${actionsHtml || ""}`;
  return row;
}

async function loadFriends(silent = false) {
  try {
    const data = await api("/api/friends");
    state.friends = data.items || [];
    state.friendByUid = {};
    state.friends.forEach((f) => { if (f.uid) state.friendByUid[f.uid] = f; });
    const list = $("#friends-list");
    list.innerHTML = state.friends.length ? "" : `<p class="empty">Chưa có bạn bè nào.</p>`;
    state.friends.forEach((f) => {
      const row = personRow(f,
        `<button class="btn-ghost" data-chat="${esc(f.uid)}">Nhắn tin</button>
         <button class="btn-ghost" data-remove="${esc(f.uid)}">Huỷ</button>
         <button class="btn-ghost" data-block="${esc(f.uid)}">Chặn</button>`);
      row.querySelector("[data-chat]").addEventListener("click", () => { showView("chat"); openChat(f.uid, fullName(f), null); });
      row.querySelector("[data-remove]").addEventListener("click", async () => {
        if (!confirm(`Huỷ kết bạn với ${fullName(f)}?`)) return;
        try { await apiJson("/api/friends/remove", { user_uid: f.uid }); loadFriends(); }
        catch (ex) { toast(ex.message); }
      });
      row.querySelector("[data-block]").addEventListener("click", async () => {
        if (!confirm(`Chặn ${fullName(f)}? Locket sẽ tự huỷ kết bạn với người này.`)) return;
        try { await apiJson("/api/friends/block", { user_uid: f.uid }); toast("Đã chặn"); loadFriends(); }
        catch (ex) { toast(ex.message); }
      });
      list.appendChild(row);
    });
  } catch (ex) { if (!silent) toast(ex.message); }
  loadRequests();
  loadGroups();
}

async function loadGroups() {
  try {
    const data = await api("/api/groups");
    const groups = (data && (data.groups || (data.data && data.data.groups))) || [];
    const head = $("#groups-head"), list = $("#groups-list");
    list.innerHTML = "";
    head.classList.toggle("hidden", !groups.length);
    groups.forEach((g) => {
      const name = g.name || g.title || g.id || "Nhóm";
      const members = g.members || g.member_uids || [];
      const row = document.createElement("div");
      row.className = "person";
      row.innerHTML = `<span class="avatar-fallback">👥</span><div class="person-main">
        <div class="person-name">${esc(name)}</div>
        <div class="person-sub">${Array.isArray(members) ? members.length + " thành viên" : ""}</div></div>`;
      list.appendChild(row);
    });
  } catch { /* bỏ qua nếu không có nhóm */ }
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
      const row = personRow(u, `<button class="btn-gold small" data-accept="${esc(u.uid)}">Đồng ý</button>`);
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
  try {
    const inv = await api(`/api/invite/${encodeURIComponent(username)}`);
    const box = $("#invite-box");
    box.innerHTML = `Link Locket công khai của @${esc(username)}: <a href="${esc(inv.link)}" target="_blank" rel="noopener">${esc(inv.link)}</a>`;
    box.classList.remove("hidden");
  } catch { /* bỏ qua nếu không phân giải được link */ }
});

$("#suggest-btn").addEventListener("click", async () => {
  const phones = $("#suggest-phones").value.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean);
  const list = $("#suggest-list");
  list.innerHTML = `<p class="empty">Đang tìm…</p>`;
  try {
    const data = await apiJson("/api/friends/suggest", { phone_contacts: phones });
    const items = data.items || [];
    list.innerHTML = items.length ? "" : `<p class="empty">Không tìm thấy gợi ý nào.</p>`;
    items.forEach((u) => {
      const row = personRow(u, `<button class="btn-gold small" data-add="${esc(u.uid)}">Kết bạn</button>`);
      row.querySelector("[data-add]").addEventListener("click", async () => {
        try { await apiJson("/api/friends/request", { user_uid: u.uid }); toast("Đã gửi lời mời 💛"); }
        catch (ex) { toast(ex.message); }
      });
      list.appendChild(row);
    });
  } catch (ex) { list.innerHTML = `<p class="empty">${esc(ex.message)}</p>`; }
});

/* ================= Tin nhắn ================= */
function convOtherUid(c) {
  if (!c || typeof c !== "object") return null;
  if (c.peer_uid) return c.peer_uid;
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
  closeChatSocket();
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
      const badge = c.unread_count ? ` <span class="chip">${esc(c.unread_count)} chưa đọc</span>` : "";
      row.innerHTML = `${avatarHtml(f || {})}<div class="person-main">
        <div class="person-name">${esc(convTitle(c, otherUid))}${badge}</div>
        <div class="person-sub">${esc(convLastText(c))}</div></div>`;
      row.addEventListener("click", () => {
        if (otherUid) openChat(otherUid, convTitle(c, otherUid), c.conversation_id || null);
        else toast("Chưa rõ người trò chuyện");
      });
      list.appendChild(row);
    });
    if (!items.length && state.friends.length) {
      state.friends.forEach((f) => {
        const row = document.createElement("button");
        row.className = "person";
        row.innerHTML = `${avatarHtml(f)}<div class="person-main">
          <div class="person-name">${esc(fullName(f))}</div>
          <div class="person-sub">Bắt đầu trò chuyện</div></div>`;
        row.addEventListener("click", () => openChat(f.uid, fullName(f), null));
        list.appendChild(row);
      });
    }
  } catch (ex) { toast(ex.message); }
}

async function ensureChatReactions() {
  if (state.chatReactions.length) return;
  try {
    const data = await api("/api/chat/reactions");
    state.chatReactions = data.items || [];
  } catch { state.chatReactions = ["❤️", "🔥", "🥰", "😂", "🥺", "👍"]; }
}

function appendMessage(m) {
  const box = $("#chat-messages");
  const meUid = state.me && state.me.uid;
  const sender = m.sender || m.sender_uid || m.from || "";
  const text = m.text || m.body || m.message || "";
  const mid = m.message_id || m.id || m.uid || "";
  if (mid && box.querySelector(`[data-mid="${CSS.escape(mid)}"]`)) return;
  const wrap = document.createElement("div");
  wrap.className = "msg-row";
  const reactions = m.reactions || m.reaction || null;
  const reactionHtml = reactions
    ? `<span class="msg-reaction">${esc(Array.isArray(reactions) ? reactions.map((r) => r.emoji || r.reaction || r).join(" ") : reactions.emoji || reactions)}</span>` : "";
  wrap.innerHTML = `<div class="bubble${sender && meUid && sender === meUid ? " mine" : ""}" data-mid="${esc(mid)}">${esc(text)}${reactionHtml}</div>
    <div class="msg-actions hidden"></div>`;
  const bubble = wrap.querySelector(".bubble");
  const actions = wrap.querySelector(".msg-actions");
  bubble.addEventListener("click", async () => {
    const willShow = actions.classList.contains("hidden");
    $$(".msg-actions").forEach((a) => a.classList.add("hidden"));
    if (!willShow) return;
    await ensureChatReactions();
    actions.innerHTML = "";
    state.chatReactions.slice(0, 8).forEach((emoji) => {
      const b = document.createElement("button");
      b.textContent = emoji;
      b.addEventListener("click", async () => {
        const convId = state.currentConversationId || m.conversation_id;
        if (!convId || !mid) { toast("Chưa rõ mã cuộc trò chuyện"); return; }
        try { await apiJson("/api/messages/reaction", { conversation_id: convId, message_id: mid, emoji }); toast(`Đã thả ${emoji}`); actions.classList.add("hidden"); }
        catch (ex) { toast(ex.message); }
      });
      actions.appendChild(b);
    });
    if (sender && meUid && sender === meUid) {
      const del = document.createElement("button");
      del.textContent = "🗑 Thu hồi";
      del.addEventListener("click", async () => {
        const convId = state.currentConversationId || m.conversation_id;
        if (!convId || !mid) { toast("Chưa rõ mã tin nhắn"); return; }
        try { await apiJson("/api/messages/delete", { conversation_uid: convId, message_uid: mid }); wrap.remove(); toast("Đã thu hồi tin nhắn"); }
        catch (ex) { toast(ex.message); }
      });
      actions.appendChild(del);
    }
    actions.classList.remove("hidden");
  });
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
}

async function openChat(uid, name, conversationId) {
  state.currentChatUid = uid;
  state.currentChatName = name;
  state.currentConversationId = conversationId || null;
  $("#conv-list").classList.add("hidden");
  $("#chat-box").classList.remove("hidden");
  $("#chat-title").textContent = name;
  const ghost = $("#chat-ghost").checked;
  apiJson("/api/messages/read", {
    other_user_id: uid,
    conversation_uid: conversationId || undefined,
    send_read_receipt: !ghost,
  }).catch(() => {});
  await loadMessages();
  connectChatSocket(uid);
}
$("#chat-back").addEventListener("click", loadConversations);

async function loadMessages() {
  const box = $("#chat-messages");
  box.innerHTML = "";
  try {
    const data = await api(`/api/messages?other_user_id=${encodeURIComponent(state.currentChatUid)}`);
    const items = data.items || [];
    items.forEach((m) => {
      if (!state.currentConversationId && m.conversation_id) state.currentConversationId = m.conversation_id;
      if (m.text || m.body || m.message) appendMessage(m);
    });
    box.scrollTop = box.scrollHeight;
  } catch (ex) { toast(ex.message); }
}

function closeChatSocket() {
  if (state.chatSocket) {
    try { state.chatSocket.close(); } catch { /* ignore */ }
    state.chatSocket = null;
  }
  const live = $("#chat-live");
  if (live) live.classList.add("hidden");
}

function connectChatSocket(uid) {
  closeChatSocket();
  try {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/api/chat/ws?other_user_id=${encodeURIComponent(uid)}`);
    state.chatSocket = ws;
    ws.onopen = () => $("#chat-live").classList.remove("hidden");
    ws.onclose = () => $("#chat-live").classList.add("hidden");
    ws.onerror = () => $("#chat-live").classList.add("hidden");
    ws.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        const m = payload.data || payload;
        if (m && (m.text || m.body)) appendMessage(m);
      } catch { /* bỏ qua gói lạ */ }
    };
    const ping = setInterval(() => {
      if (ws.readyState === 1) ws.send("ping");
      else clearInterval(ping);
    }, 25000);
  } catch { /* không có trực tiếp vẫn xem được tin cũ */ }
}

$("#chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || !state.currentChatUid) return;
  try {
    await apiJson("/api/messages/send", { receiver_uid: state.currentChatUid, text });
    input.value = "";
    appendMessage({ sender: state.me && state.me.uid, text, message_id: "tmp" + Date.now() });
  } catch (ex) { toast(ex.message); }
});

/* ================= Trang cá nhân ================= */
async function loadDevice() {
  try {
    const data = await api("/api/device");
    const d = data.device || {};
    $("#device-info").textContent = d.model_name
      ? `Thiết bị giả lập hiện tại: ${d.model_name}${d.ios_version ? " · iOS " + d.ios_version : ""}`
      : "";
    if (state.me && !$("#edit-birthdate").value && state.me.raw && state.me.raw.birthdate) {
      $("#edit-birthdate").value = String(state.me.raw.birthdate).slice(0, 10);
    }
  } catch { /* bỏ qua */ }
}

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
      cell.addEventListener("click", () => openLightbox(m.image_url || m.thumbnail_url, m.video_url));
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

$("#birthdate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const v = $("#edit-birthdate").value;
  if (!v) return;
  try {
    await apiJson("/api/profile/birthdate", { birthdate: v });
    $("#me-ok").textContent = "Đã cập nhật ngày sinh.";
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

$("#session-sync-btn").addEventListener("click", async () => {
  try { await apiJson("/api/session/sync", {}); $("#me-ok").textContent = "Đã đồng bộ cài đặt với Locket."; }
  catch (ex) { $("#me-error").textContent = ex.message; }
});
$("#session-refresh-btn").addEventListener("click", async () => {
  try { await apiJson("/api/session/refresh", {}); $("#me-ok").textContent = "Đã làm mới phiên đăng nhập."; }
  catch (ex) { $("#me-error").textContent = ex.message; }
});
$("#device-auto-btn").addEventListener("click", async () => {
  try {
    await apiJson("/api/device/auto", { auto_emulate: true });
    $("#me-ok").textContent = "Đã đổi sang thiết bị giả lập mới.";
    loadDevice();
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
