const tokenKey = "safetrack_admin";

function token() {
  return localStorage.getItem(tokenKey) || "";
}

async function api(path, options) {
  const opts = options || {};
  const headers = { "Content-Type": "application/json" };
  if (token()) headers.Authorization = "Bearer " + token();
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined
  });
  const data = await res.json().catch(function () { return {}; });
  if (!res.ok) {
    const err = new Error(data.error || "Request failed");
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function copyText(value) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(value);
  }
  const area = document.createElement("textarea");
  area.value = value;
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
  return Promise.resolve();
}

function showLogin(message) {
  document.getElementById("login").hidden = false;
  document.getElementById("app").hidden = true;
  document.getElementById("login-note").textContent = message || "";
}

function showApp() {
  document.getElementById("login").hidden = true;
  document.getElementById("app").hidden = false;
  window.scrollTo(0, 0);
}

let lastUrl = "";
let devices = [];
let users = [];

function paintQr(url) {
  const box = document.getElementById("qr");
  box.textContent = "";
  if (window.QRCode) new QRCode(box, { text: url, width: 160, height: 160 });
}

function showCreated(data) {
  lastUrl = data.ingest_url;
  document.getElementById("created").hidden = false;
  document.getElementById("new-id").textContent = data.device_id || "";
  document.getElementById("ingest-url").textContent = data.ingest_url;
  paintQr(data.ingest_url);
}

function statusClass(status) {
  if (status === "Waiting") return "pill wait";
  if (status === "Offline") return "pill off";
  return "pill";
}

function renderDevices() {
  document.getElementById("device-count").textContent = String(devices.length);
  const box = document.getElementById("device-table");
  if (!devices.length) {
    box.innerHTML = '<div class="empty">No devices yet. Create one to get its URL.</div>';
    return;
  }
  const rows = devices.map(function (item) {
    return "<tr><td><b>" + escapeHtml(item.device_id) + "</b></td>"
      + "<td class=\"urlbox\" style=\"margin:0;\">" + escapeHtml(item.ingest_url) + "</td>"
      + "<td><button class=\"link\" data-copy=\"" + escapeHtml(item.ingest_url) + "\">Copy URL</button></td></tr>";
  }).join("");
  box.innerHTML = "<table><thead><tr><th>Device ID</th><th>URL</th><th></th></tr></thead><tbody>" + rows + "</tbody></table>";
  box.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () { copyText(button.getAttribute("data-copy")); });
  });
}

function renderUsers() {
  const box = document.getElementById("user-table");
  if (!users.length) {
    box.innerHTML = '<div class="empty">No users yet.</div>';
    return;
  }
  box.textContent = "";
  users.forEach(function (user, index) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "user-row";
    const who = document.createElement("div");
    const name = document.createElement("b");
    name.textContent = user.name || user.username || "User";
    const handle = document.createElement("div");
    handle.style.color = "#5d6b7c";
    handle.textContent = user.username || "";
    who.appendChild(name);
    who.appendChild(handle);
    const chev = document.createElement("span");
    chev.textContent = "›";
    chev.style.color = "#5d6b7c";
    row.appendChild(who);
    row.appendChild(chev);
    row.addEventListener("click", function () { openUser(index); });
    box.appendChild(row);
  });
}

function openUser(index) {
  const user = users[index];
  if (!user) return;
  document.getElementById("user-list-panel").hidden = true;
  document.getElementById("user-profile").hidden = false;
  document.getElementById("profile-name").textContent = user.name || user.username || "User";
  const bits = [user.username, user.country, user.phone || user.email, user.address].filter(Boolean);
  document.getElementById("profile-meta").textContent = bits.join(" · ");
  document.getElementById("profile-total").textContent = String(user.device_count || 0);
  document.getElementById("profile-connected").textContent = String(user.connected || 0);
  document.getElementById("profile-alive").textContent = String(user.alive || 0);
  const box = document.getElementById("profile-devices");
  const list = user.devices || [];
  if (!list.length) {
    box.innerHTML = '<div class="empty">This user has no devices.</div>';
    return;
  }
  const rows = list.map(function (item) {
    const battery = item.battery == null ? "—" : Math.round(item.battery) + "%";
    return "<tr><td><b>" + escapeHtml(item.device_id) + "</b></td>"
      + "<td><span class=\"" + statusClass(item.status) + "\">" + escapeHtml(item.status) + "</span></td>"
      + "<td>" + battery + "</td>"
      + "<td>" + escapeHtml(item.updated_label || "—") + "</td>"
      + "<td>" + escapeHtml(item.address || "—") + "</td>"
      + "<td class=\"urlbox\">" + escapeHtml(item.ingest_url) + "</td></tr>";
  }).join("");
  box.innerHTML = "<table><thead><tr><th>Device ID</th><th>Status</th><th>Battery</th><th>Last report</th><th>Place</th><th>URL</th></tr></thead><tbody>" + rows + "</tbody></table>";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, function (ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[ch];
  });
}

async function loadOverview() {
  const data = await api("/api/admin/overview");
  devices = data.devices || [];
  users = data.users || [];
  renderDevices();
  renderUsers();
}

document.getElementById("admin-pass").addEventListener("keydown", function (event) {
  if (event.key === "Enter") document.getElementById("login-btn").click();
});

document.getElementById("login-btn").addEventListener("click", async function () {
  document.getElementById("login-note").textContent = "";
  try {
    const data = await api("/api/admin/login", {
      method: "POST",
      body: {
        username: document.getElementById("admin-user").value.trim(),
        password: document.getElementById("admin-pass").value
      }
    });
    localStorage.setItem(tokenKey, data.token);
    showApp();
    await loadOverview();
  } catch (err) {
    document.getElementById("login-note").textContent = err.message;
  }
});

document.getElementById("signout").addEventListener("click", function () {
  localStorage.removeItem(tokenKey);
  showLogin();
});

document.getElementById("tab-devices").addEventListener("click", function () {
  document.getElementById("tab-devices").classList.add("on");
  document.getElementById("tab-users").classList.remove("on");
  document.getElementById("devices-view").hidden = false;
  document.getElementById("users-view").hidden = true;
});

document.getElementById("tab-users").addEventListener("click", function () {
  document.getElementById("tab-users").classList.add("on");
  document.getElementById("tab-devices").classList.remove("on");
  document.getElementById("users-view").hidden = false;
  document.getElementById("devices-view").hidden = true;
  document.getElementById("user-list-panel").hidden = false;
  document.getElementById("user-profile").hidden = true;
});

document.getElementById("user-back").addEventListener("click", function () {
  document.getElementById("user-profile").hidden = true;
  document.getElementById("user-list-panel").hidden = false;
});

document.getElementById("create").addEventListener("click", async function () {
  const note = document.getElementById("create-note");
  const button = document.getElementById("create");
  note.textContent = "";
  button.disabled = true;
  try {
    const data = await api("/api/admin/devices", { method: "POST", body: {} });
    showCreated(data);
    await loadOverview();
  } catch (err) {
    note.textContent = err.message;
  }
  button.disabled = false;
});

document.getElementById("copy-url").addEventListener("click", function () {
  if (lastUrl) copyText(lastUrl);
});

if (token()) {
  showApp();
  loadOverview().catch(function () { showLogin("Sign in again."); });
}
