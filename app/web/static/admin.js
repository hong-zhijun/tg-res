const state = {
  route: "dashboard",
  messagePage: 1,
  messageHasNext: false,
  users: [],
  settings: {},
};

const routes = {
  dashboard: ["仪表盘", "今日概览"],
  messages: ["消息列表", "搜索 / 筛选"],
  users: ["用户白名单", "访问控制"],
  groups: ["分组管理", "资源分类"],
  logs: ["日志查看", "运行记录"],
  settings: ["设置页", "系统配置"],
};

const typeNames = {
  text: "文本",
  photo: "图片",
  video: "视频",
  document: "文档",
  voice: "语音",
  audio: "音频",
  animation: "动画",
  sticker: "贴纸",
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  bindEvents();
  showRoute(currentRoute());
});

function bindElements() {
  [
    "sidebar", "scrim", "menuBtn", "nav", "pageTitle", "pageCrumb", "globalSearch",
    "logoutBtn", "refreshBtn", "metricToday", "metricWeek", "metricMonth", "metricStorage",
    "heroSummary", "recentMessages", "typeDistribution", "messageSearch", "typeFilter",
    "dateFrom", "dateTo", "prevPageBtn", "nextPageBtn", "messageRows", "userSearch",
    "allowedFilter", "userRows", "logLevelFilter", "logSearch", "refreshLogsBtn",
    "addRootGroupBtn", "groupTree",
    "logRows", "settingsList", "modalBackdrop", "modalBox", "modalTitle", "modalBody",
    "modalFoot", "modalClose", "toastStack",
  ].forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function bindEvents() {
  window.addEventListener("hashchange", () => showRoute(currentRoute()));
  els.menuBtn?.addEventListener("click", () => {
    els.sidebar.classList.add("open");
    els.scrim.classList.add("show");
  });
  els.scrim?.addEventListener("click", closeSidebar);
  els.logoutBtn?.addEventListener("click", logout);
  els.refreshBtn?.addEventListener("click", () => loadRoute(state.route, true));
  document.querySelectorAll("[data-action='refresh']").forEach((button) => {
    button.addEventListener("click", () => loadRoute(state.route, true));
  });

  els.messageSearch?.addEventListener("input", debounce(() => {
    state.messagePage = 1;
    loadMessages();
  }, 300));
  [els.typeFilter, els.dateFrom, els.dateTo].forEach((el) => {
    el?.addEventListener("change", () => {
      state.messagePage = 1;
      loadMessages();
    });
  });
  els.prevPageBtn?.addEventListener("click", () => {
    if (state.messagePage > 1) {
      state.messagePage -= 1;
      loadMessages();
    }
  });
  els.nextPageBtn?.addEventListener("click", () => {
    if (state.messageHasNext) {
      state.messagePage += 1;
      loadMessages();
    }
  });

  els.userSearch?.addEventListener("input", debounce(renderUsers, 200));
  els.allowedFilter?.addEventListener("change", renderUsers);
  els.addRootGroupBtn?.addEventListener("click", () => promptCreateGroup(null));
  els.logLevelFilter?.addEventListener("change", loadLogs);
  els.logSearch?.addEventListener("input", debounce(loadLogs, 250));
  els.refreshLogsBtn?.addEventListener("click", loadLogs);

  els.modalClose?.addEventListener("click", closeModal);
  els.modalBackdrop?.addEventListener("click", (event) => {
    if (event.target === els.modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
}

function currentRoute() {
  const hash = window.location.hash.replace("#", "");
  return routes[hash] ? hash : "dashboard";
}

async function showRoute(route) {
  state.route = routes[route] ? route : "dashboard";
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === state.route);
  });
  document.querySelectorAll(".nav a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === state.route);
  });
  els.pageTitle.textContent = routes[state.route][0];
  els.pageCrumb.textContent = routes[state.route][1];
  closeSidebar();
  await loadRoute(state.route, false);
}

async function loadRoute(route, noisy) {
  try {
    if (route === "dashboard") await loadDashboard();
    if (route === "messages") await loadMessages();
    if (route === "users") await loadUsers();
    if (route === "groups") await loadGroups();
    if (route === "logs") await loadLogs();
    if (route === "settings") await loadSettings();
    if (noisy) showToast("已刷新", "success");
  } catch (error) {
    handleApiError(error);
  }
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("未登录或会话已过期");
  }
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch (_) {
      // keep default message
    }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response.text();
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  els.metricToday.textContent = data.stats.today;
  els.metricWeek.textContent = data.stats.week;
  els.metricMonth.textContent = data.stats.month;
  els.metricStorage.textContent = formatBytes(data.stats.storage_bytes);
  els.heroSummary.textContent = `累计归档 ${data.stats.total} 条，本月新增 ${data.stats.month} 条，媒体目录占用 ${formatBytes(data.stats.storage_bytes)}。`;
  renderRecentMessages(data.recent_messages || []);
  renderTypeDistribution(data.type_distribution || []);
}

function renderRecentMessages(items) {
  els.recentMessages.innerHTML = items.map((item) => `
    <div class="activity-item">
      <i class="activity-dot"></i>
      <div>
        <strong>#${item.id} ${escapeHtml(typeNames[item.type] || item.type)}</strong>
        <span>${escapeHtml(summaryText(item))}</span>
      </div>
      <time>${formatDate(item.created_at)}</time>
    </div>
  `).join("") || `<div class="empty">暂无消息</div>`;
}

function renderTypeDistribution(items) {
  els.typeDistribution.innerHTML = items.map((item) => `
    <div class="activity-item">
      <i class="activity-dot"></i>
      <div>
        <strong>${escapeHtml(typeNames[item.type] || item.type)}</strong>
        <span>${item.count} 条记录</span>
      </div>
      <time>${Math.round(item.count)}</time>
    </div>
  `).join("") || `<div class="empty">暂无类型数据</div>`;
}

async function loadMessages() {
  const params = new URLSearchParams({
    page: String(state.messagePage),
    page_size: "50",
  });
  if (els.messageSearch.value.trim()) params.set("q", els.messageSearch.value.trim());
  if (els.typeFilter.value) params.set("type", els.typeFilter.value);
  if (els.dateFrom.value) params.set("date_from", els.dateFrom.value);
  if (els.dateTo.value) params.set("date_to", els.dateTo.value);

  const data = await api(`/api/messages?${params.toString()}`);
  state.messageHasNext = data.has_next;
  els.prevPageBtn.disabled = state.messagePage <= 1;
  els.nextPageBtn.disabled = !data.has_next;
  renderMessages(data.items || []);
}

function renderMessages(items) {
  els.messageRows.innerHTML = items.map((item) => `
    <tr>
      <td>
        <div class="title-cell">
          <div class="avatar">${typeAvatar(item.type)}</div>
          <div><strong>#${item.id}</strong><span>${escapeHtml(summaryText(item))}</span></div>
        </div>
      </td>
      <td><span class="pill">${escapeHtml(typeNames[item.type] || item.type)}</span></td>
      <td>${item.user_id}</td>
      <td>${formatDate(item.created_at)}</td>
      <td>${item.file_size ? formatBytes(item.file_size) : "-"}</td>
      <td>
        <div class="row-actions">
          <button class="icon-btn" title="查看详情" data-message-detail="${item.id}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/></svg></button>
          <button class="icon-btn icon-btn--danger" title="删除" data-message-delete="${item.id}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2m1 0v14H7V6h10ZM10 10v7m4-7v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
        </div>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="6"><div class="empty">没有匹配的消息</div></td></tr>`;

  document.querySelectorAll("[data-message-detail]").forEach((button) => {
    button.addEventListener("click", () => openMessageDetail(button.dataset.messageDetail));
  });
  document.querySelectorAll("[data-message-delete]").forEach((button) => {
    button.addEventListener("click", () => confirmDeleteMessage(button.dataset.messageDelete));
  });
}

async function openMessageDetail(id) {
  try {
    const msg = await api(`/api/messages/${id}`);
    const media = renderMedia(msg);
    openModal({
      title: `消息 #${msg.id}`,
      body: `
        <div class="detail-grid">
          <div class="detail-item"><span>Telegram ID</span><strong>${msg.telegram_message_id}</strong></div>
          <div class="detail-item"><span>类型</span><strong>${escapeHtml(typeNames[msg.type] || msg.type)}</strong></div>
          <div class="detail-item"><span>用户</span><strong>${escapeHtml(userLabel(msg.user) || String(msg.user_id))}</strong></div>
          <div class="detail-item"><span>时间</span><strong>${formatDate(msg.created_at)}</strong></div>
          <div class="detail-item"><span>文件</span><strong>${escapeHtml(msg.file_path || "-")}</strong></div>
          <div class="detail-item"><span>大小</span><strong>${msg.file_size ? formatBytes(msg.file_size) : "-"}</strong></div>
        </div>
        <div class="message-body">${escapeHtml(msg.text || "无文字内容")}</div>
        ${media}
        <h4>原始 JSON</h4>
        <pre class="json-body">${escapeHtml(JSON.stringify(msg.raw_json, null, 2))}</pre>
      `,
      foot: `
        <button class="btn ghost" data-modal-close>关闭</button>
        <button class="btn danger" data-delete-current="${msg.id}">删除</button>
      `,
    });
    document.querySelector("[data-delete-current]")?.addEventListener("click", () => {
      closeModal();
      confirmDeleteMessage(msg.id);
    });
  } catch (error) {
    handleApiError(error);
  }
}

function renderMedia(msg) {
  if (!msg.media_url) return "";
  const url = encodeURI(msg.media_url);
  if (msg.type === "photo" || msg.type === "sticker") {
    return `<div class="media-box"><img src="${url}" alt=""></div>`;
  }
  if (msg.type === "video" || msg.type === "animation") {
    return `<div class="media-box"><video src="${url}" controls></video></div>`;
  }
  if (msg.type === "audio" || msg.type === "voice") {
    return `<div class="media-box"><audio src="${url}" controls></audio></div>`;
  }
  return `<div class="media-box"><a class="btn" href="${url}" target="_blank" rel="noreferrer">下载文件</a></div>`;
}

function confirmDeleteMessage(id) {
  openModal({
    title: "删除消息",
    small: true,
    body: `<p>确定删除消息 #${id}？这会同时删除数据库记录和已保存的媒体文件。</p>`,
    foot: `
      <button class="btn ghost" data-modal-close>取消</button>
      <button class="btn danger" id="confirmDeleteMessage">删除</button>
    `,
  });
  document.getElementById("confirmDeleteMessage").addEventListener("click", async () => {
    try {
      await api(`/api/messages/${id}`, { method: "DELETE" });
      closeModal();
      showToast("消息已删除", "success");
      await loadMessages();
      await loadDashboard();
    } catch (error) {
      handleApiError(error);
    }
  });
}

async function loadUsers() {
  const data = await api("/api/users");
  state.users = data.items || [];
  renderUsers();
}

function renderUsers() {
  const q = els.userSearch.value.trim().toLowerCase();
  const allowed = els.allowedFilter.value;
  const users = state.users.filter((user) => {
    const text = [user.id, user.username, user.display_name, user.notes].join(" ").toLowerCase();
    const matchQ = !q || text.includes(q);
    const matchAllowed = allowed === "" || String(user.allowed) === allowed;
    return matchQ && matchAllowed;
  });

  els.userRows.innerHTML = users.map((user) => `
    <tr>
      <td>
        <div class="title-cell">
          <div class="avatar">${escapeHtml(userInitial(user))}</div>
          <div><strong>${escapeHtml(userLabel(user))}</strong><span>${user.id}</span></div>
        </div>
      </td>
      <td><span class="pill ${user.allowed ? "success" : "warn"}">${user.allowed ? "已允许" : "未允许"}</span></td>
      <td>${user.message_count || 0}</td>
      <td>${formatDate(user.last_seen_at)}</td>
      <td>${escapeHtml(user.notes || "-")}</td>
      <td>
        <div class="row-actions">
          <button class="icon-btn ${user.allowed ? "icon-btn--warn" : "icon-btn--success"}" title="${user.allowed ? "禁用用户" : "允许用户"}" data-user-toggle="${user.id}">${user.allowed ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M7 11V7a5 5 0 0 1 10 0v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="16.5" r="1.5" fill="currentColor"/></svg>' : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M7 11V7a5 5 0 0 1 9.9-1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="16.5" r="1.5" fill="currentColor"/></svg>'}</button>
          <button class="icon-btn" title="编辑备注" data-user-note="${user.id}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        </div>
      </td>
    </tr>
  `).join("") || `<tr><td colspan="6"><div class="empty">没有匹配的用户</div></td></tr>`;

  document.querySelectorAll("[data-user-toggle]").forEach((button) => {
    button.addEventListener("click", () => toggleUser(button.dataset.userToggle));
  });
  document.querySelectorAll("[data-user-note]").forEach((button) => {
    button.addEventListener("click", () => openUserNote(button.dataset.userNote));
  });
}

async function toggleUser(id) {
  try {
    await api(`/api/users/${id}/toggle`, { method: "POST" });
    showToast("用户权限已更新", "success");
    await loadUsers();
  } catch (error) {
    handleApiError(error);
  }
}

function openUserNote(id) {
  const user = state.users.find((item) => String(item.id) === String(id));
  if (!user) return;
  openModal({
    title: "编辑备注",
    small: true,
    body: `
      <div class="field">
        <label>用户</label>
        <input value="${escapeAttr(userLabel(user))}" disabled>
      </div>
      <div class="field">
        <label for="noteInput">备注</label>
        <textarea id="noteInput">${escapeHtml(user.notes || "")}</textarea>
      </div>
    `,
    foot: `
      <button class="btn ghost" data-modal-close>取消</button>
      <button class="btn primary" id="saveUserNote">保存</button>
    `,
  });
  document.getElementById("saveUserNote").addEventListener("click", async () => {
    try {
      const notes = document.getElementById("noteInput").value;
      await api(`/api/users/${id}/note`, {
        method: "PATCH",
        body: JSON.stringify({ notes }),
      });
      closeModal();
      showToast("备注已保存", "success");
      await loadUsers();
    } catch (error) {
      handleApiError(error);
    }
  });
}

async function loadLogs() {
  const params = new URLSearchParams({ limit: "500" });
  if (els.logLevelFilter.value) params.set("level", els.logLevelFilter.value);
  const data = await api(`/api/logs?${params.toString()}`);
  const q = els.logSearch.value.trim().toLowerCase();
  const lines = (data.lines || []).filter((line) => !q || line.toLowerCase().includes(q));
  renderLogs(lines);
}

function renderLogs(lines) {
  els.logRows.innerHTML = lines.map((line) => {
    const level = extractLevel(line);
    return `
      <div class="log-line">
        <span class="pill ${levelClass(level)}">${escapeHtml(level || "LOG")}</span>
        <span>${escapeHtml(extractTime(line))}</span>
        <code>${escapeHtml(line)}</code>
      </div>
    `;
  }).join("") || `<div class="empty">暂无日志</div>`;
}

async function loadGroups() {
  const data = await api("/api/groups");
  renderGroupTree(data.items || []);
}

const GROUP_ICONS = ["📁", "📂", "📦", "📋", "⭐", "❤️", "🔥", "💎"];

function renderGroupTree(items) {
  if (!items.length) {
    els.groupTree.innerHTML = '<div class="empty">还没有分组。点击上方按钮创建第一个分组。</div>';
    return;
  }
  els.groupTree.innerHTML = items.map((g) => {
    const depth = g.path.split("/").filter(Boolean).length - 1;
    const indent = depth * 28;
    const icon = g.icon || "📁";
    return `
      <div class="group-row" style="padding-left:${indent}px">
        <div class="group-info">
          <button class="icon-picker-trigger" title="更换图标" data-group-icon="${g.id}">${icon}</button>
          <strong>${escapeHtml(g.name)}</strong>
          <span class="pill">${g.message_count} 条</span>
          <span class="group-path">${escapeHtml(g.path)}</span>
        </div>
        <div class="row-actions">
          <button class="icon-btn icon-btn--success" title="新建子分组" data-group-add="${g.id}">+</button>
          <button class="icon-btn" title="重命名" data-group-rename="${g.id}" data-group-name="${escapeAttr(g.name)}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M18.5 2.5a2.12 2.12 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
          <button class="icon-btn icon-btn--danger" title="删除分组" data-group-delete="${g.id}" data-group-name="${escapeAttr(g.name)}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2m1 0v14H7V6h10zM10 10v7m4-7v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
        </div>
      </div>
    `;
  }).join("");

  document.querySelectorAll("[data-group-add]").forEach((btn) => {
    btn.addEventListener("click", () => promptCreateGroup(Number(btn.dataset.groupAdd)));
  });
  document.querySelectorAll("[data-group-rename]").forEach((btn) => {
    btn.addEventListener("click", () => promptRenameGroup(Number(btn.dataset.groupRename), btn.dataset.groupName));
  });
  document.querySelectorAll("[data-group-delete]").forEach((btn) => {
    btn.addEventListener("click", () => confirmDeleteGroup(Number(btn.dataset.groupDelete), btn.dataset.groupName));
  });
  document.querySelectorAll("[data-group-icon]").forEach((btn) => {
    btn.addEventListener("click", () => promptChangeIcon(Number(btn.dataset.groupIcon)));
  });
}

function buildIconPicker(selectedIcon = "📁", inputId = "iconPicker") {
  return `
    <div class="field">
      <label>选择图标</label>
      <div class="icon-picker" id="${inputId}">
        ${GROUP_ICONS.map((ic) => `<button type="button" class="icon-option${ic === selectedIcon ? " active" : ""}" data-icon="${ic}">${ic}</button>`).join("")}
      </div>
    </div>
  `;
}

function bindIconPicker(containerId = "iconPicker") {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.querySelectorAll(".icon-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll(".icon-option").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
}

function getSelectedIcon(containerId = "iconPicker") {
  const container = document.getElementById(containerId);
  if (!container) return "📁";
  const active = container.querySelector(".icon-option.active");
  return active ? active.dataset.icon : "📁";
}

function promptCreateGroup(parentId) {
  const label = parentId ? "新建子分组" : "新建根分组";
  openModal({
    title: label,
    small: true,
    body: `
      <div class="field"><label for="groupNameInput">分组名称</label><input id="groupNameInput" placeholder="例：旅行"></div>
      ${buildIconPicker("📁")}
    `,
    foot: `<button class="btn ghost" data-modal-close>取消</button><button class="btn primary" id="confirmCreateGroup">创建</button>`,
  });
  bindIconPicker();
  const input = document.getElementById("groupNameInput");
  input.focus();
  const confirm = document.getElementById("confirmCreateGroup");
  const doCreate = async () => {
    const name = input.value.trim();
    if (!name) return showToast("名称不能为空", "error");
    const icon = getSelectedIcon();
    try {
      await api("/api/groups", { method: "POST", body: JSON.stringify({ name, parent_id: parentId, icon }) });
      closeModal();
      showToast("分组已创建", "success");
      await loadGroups();
    } catch (e) { handleApiError(e); }
  };
  confirm.addEventListener("click", doCreate);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doCreate(); });
}

function promptRenameGroup(id, oldName) {
  openModal({
    title: "重命名分组",
    small: true,
    body: `<div class="field"><label for="renameInput">新名称</label><input id="renameInput" value="${escapeAttr(oldName)}"></div>`,
    foot: `<button class="btn ghost" data-modal-close>取消</button><button class="btn primary" id="confirmRenameGroup">保存</button>`,
  });
  const input = document.getElementById("renameInput");
  input.focus();
  input.select();
  const doRename = async () => {
    const name = input.value.trim();
    if (!name) return showToast("名称不能为空", "error");
    try {
      await api(`/api/groups/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
      closeModal();
      showToast("已重命名", "success");
      await loadGroups();
    } catch (e) { handleApiError(e); }
  };
  document.getElementById("confirmRenameGroup").addEventListener("click", doRename);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doRename(); });
}

function promptChangeIcon(id) {
  openModal({
    title: "更换图标",
    small: true,
    body: buildIconPicker("📁", "iconChangePicker"),
    foot: `<button class="btn ghost" data-modal-close>取消</button><button class="btn primary" id="confirmChangeIcon">保存</button>`,
  });
  bindIconPicker("iconChangePicker");
  document.getElementById("confirmChangeIcon").addEventListener("click", async () => {
    const icon = getSelectedIcon("iconChangePicker");
    try {
      await api(`/api/groups/${id}`, { method: "PATCH", body: JSON.stringify({ icon }) });
      closeModal();
      showToast("图标已更新", "success");
      await loadGroups();
    } catch (e) { handleApiError(e); }
  });
}

function confirmDeleteGroup(id, name) {
  openModal({
    title: "删除分组",
    small: true,
    body: `<p>确定删除分组「${escapeHtml(name)}」？</p><p style="color:var(--muted)">子分组会移到上级，分组内消息不会被删除。</p>`,
    foot: `<button class="btn ghost" data-modal-close>取消</button><button class="btn danger" id="confirmDeleteGroup">删除</button>`,
  });
  document.getElementById("confirmDeleteGroup").addEventListener("click", async () => {
    try {
      await api(`/api/groups/${id}`, { method: "DELETE" });
      closeModal();
      showToast("分组已删除", "success");
      await loadGroups();
    } catch (e) { handleApiError(e); }
  });
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  renderSettings();
}

function renderSettings() {
  els.settingsList.innerHTML = Object.entries(state.settings).map(([key, value]) => `
    <div class="setting-row">
      <div><strong>${escapeHtml(key)}</strong><span>${escapeHtml(String(value ?? ""))}</span></div>
      ${key.includes("TOKEN") || key.includes("HASH") || key.includes("PASSWORD") ? '<span class="pill warn">脱敏</span>' : '<span class="pill">只读</span>'}
    </div>
  `).join("");
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  } catch (error) {
    handleApiError(error);
  }
}

function openModal({ title, body, foot, small = false }) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = body;
  els.modalFoot.innerHTML = foot || `<button class="btn primary" data-modal-close>知道了</button>`;
  els.modalBox.classList.toggle("small", small);
  els.modalBackdrop.classList.add("show");
  els.modalFoot.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", closeModal);
  });
}

function closeModal() {
  els.modalBackdrop.classList.remove("show");
}

function showToast(message, type = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;
  els.toastStack.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    setTimeout(() => toast.remove(), 180);
  }, 2800);
}

function handleApiError(error) {
  showToast(error.message || "操作失败", "error");
}

function closeSidebar() {
  els.sidebar?.classList.remove("open");
  els.scrim?.classList.remove("show");
}

function summaryText(item) {
  return item.text || item.file_path || "无文字内容";
}

function typeAvatar(type) {
  return ({ text: "讯", photo: "图", video: "影", document: "文", voice: "声", audio: "音", animation: "动", sticker: "贴" }[type] || "档");
}

function userInitial(user) {
  const text = user.display_name || user.username || String(user.id);
  return text.slice(0, 1).toUpperCase();
}

function userLabel(user) {
  if (!user) return "";
  return user.display_name || (user.username ? `@${user.username}` : String(user.id));
}

function formatBytes(bytes) {
  const size = Number(bytes || 0);
  if (size < 1024) return `${size} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = size / 1024;
  for (const unit of units) {
    if (value < 1024 || unit === "TB") return `${value.toFixed(1)} ${unit}`;
    value /= 1024;
  }
  return `${size} B`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function extractLevel(line) {
  const match = line.match(/\[(INFO|WARNING|ERROR|WARN|DEBUG)\]/);
  return match ? match[1] : "";
}

function extractTime(line) {
  const match = line.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : "-";
}

function levelClass(level) {
  if (level === "ERROR") return "danger";
  if (level === "WARNING" || level === "WARN") return "warn";
  if (level === "INFO") return "success";
  return "";
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}
