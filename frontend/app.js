/* SafeTrack API client. The screens and styles stay as designed. */

const PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s7-7.58 7-12.5A7 7 0 0 0 5 9.5C5 14.42 12 22 12 22z"/><circle cx="12" cy="9.5" r="2.5"/></svg>';
const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17 19 7.5"/></svg>';
const CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg>';
const ALERT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 2.3 18a1.8 1.8 0 0 0 1.5 2.7h16.4a1.8 1.8 0 0 0 1.5-2.7l-8-14.1a1.8 1.8 0 0 0-3.1 0Z"/><path d="M12 9.5v4.2M12 17.3h.01"/></svg>';
const ZONE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 0-5.4 4.9L3 17.5V21h3.5l6.3-6.3a4 4 0 0 0 4.9-5.4l-2.7 2.7-2.1-2.1 2.8-2.6Z"/></svg>';

let session = {
  name: "John Doe",
  firstName: "John",
  surname: "Doe",
  username: "johndoe",
  birthDate: "1991-03-12",
  homeAddress: "123 Main Street, Accra",
  country: "Ghana",
  deviceName: "John Doe",
  deviceId: "12345678",
  email: "john.doe@example.com",
  phone: "+233 24 000 0000",
  avatarUrl: "",
  lat: null,
  lng: null,
  address: "",
  speed: 5,
  updatedLabel: "",
  live: false,
  trail: null,
  arrived: false,
  sosDismissed: false
};

function apiBase() {
  const configured = (window.SAFETRACK_API || "").replace(/\/$/, "");
  const placeholder = !configured || configured.indexOf("YOUR-SERVICE-NAME") !== -1;
  if (!placeholder) return configured;
  return location.origin.replace(/\/$/, "");
}

async function api(path, options) {
  const opts = options || {};
  const headers = Object.assign({}, opts.headers || {});
  const token = localStorage.getItem("safetrack_token");
  if (token) headers.Authorization = "Bearer " + token;
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  if (opts.body && !isForm && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(apiBase() + path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body
    });
  } catch (e) {
    const err = new Error("Can't reach the SafeTrack server. Start Flask, or set the Render URL in config.js.");
    err.network = true;
    throw err;
  }
  const data = await res.json().catch(function () { return {}; });
  if (!res.ok) {
    const err = new Error(data.error || "Request failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

function toggleMenu(open) {
  document.getElementById("menu-backdrop").style.opacity = open ? "1" : "0";
  document.getElementById("menu-backdrop").style.pointerEvents = open ? "auto" : "none";
  document.getElementById("menu-panel").style.transform = open ? "translateX(0)" : "translateX(-100%)";
}
function menuGo(id) { toggleMenu(false); go(id); }

function setSigninNote(msg) {
  const el = document.getElementById("signin-note");
  if (el) el.textContent = msg;
}

function samePersonAndDevice() {
  const deviceName = (session.deviceName || session.name || "").trim().toLowerCase();
  const person = (session.name || "").trim().toLowerCase();
  return !deviceName || deviceName === person;
}

function setFace(photoEl, initialEl, src, label) {
  if (photoEl && src) {
    photoEl.style.display = "";
    photoEl.src = src;
    if (initialEl) initialEl.style.display = "none";
    return;
  }
  if (photoEl) photoEl.style.display = "none";
  if (initialEl) {
    initialEl.style.display = "";
    initialEl.textContent = (label || "?").trim().charAt(0).toUpperCase();
  }
}

function paintIdentity() {
  document.querySelectorAll(".dyn-name").forEach(function (el) { el.textContent = session.name; });
  document.querySelectorAll(".dyn-device-name").forEach(function (el) {
    el.textContent = session.deviceName || session.name;
  });
  document.querySelectorAll(".dyn-devid-label").forEach(function (el) {
    el.textContent = "Device ID: " + session.deviceId;
  });
  if (session.avatarUrl) {
    document.querySelectorAll(".dyn-avatar").forEach(function (img) {
      if (img.getAttribute("data-base") !== session.avatarUrl) {
        img.setAttribute("data-base", session.avatarUrl);
        img.src = session.avatarUrl;
      }
    });
  }
  const deviceLabel = session.deviceName || session.name;
  const fallbackPhoto = document.querySelector(".dyn-avatar") ? document.querySelector(".dyn-avatar").src : "";
  const devicePhoto = samePersonAndDevice() ? (session.avatarUrl || fallbackPhoto) : "";
  setFace(document.getElementById("home-device-photo"), document.getElementById("home-device-initial"), devicePhoto, deviceLabel);
  setFace(document.getElementById("sos-photo"), document.getElementById("sos-initial"), devicePhoto, deviceLabel);
  const devid = document.getElementById("acct-devid");
  if (devid) devid.value = session.deviceId;
}

function paintLocation() {
  const addr = document.getElementById("home-address");
  if (addr && session.address) addr.textContent = session.address;
  const upd = document.getElementById("home-updated");
  if (upd && session.updatedLabel) upd.textContent = session.updatedLabel;
  const sos = document.getElementById("sos-loc-text");
  if (sos && session.address) {
    sos.textContent = session.address + " · " + (session.updatedLabel || "just now");
  }
  document.querySelectorAll(".dyn-motion").forEach(function (motion) {
    if (session.speed == null) return;
    if (session.arrived) {
      motion.classList.remove("moving");
      motion.textContent = "● Arrived";
      return;
    }
    const moving = Number(session.speed) > 0.5;
    const verb = motion.closest("#screen-directions") ? "Walking" : "Moving";
    motion.classList.toggle("moving", moving);
    motion.textContent = moving ? "● " + verb + " • " + Math.round(Number(session.speed)) + " km/h" : "● Online";
  });
  paintTrackCard();
}

function paintDevice(device) {
  if (!device) return;
  const set = function (id, text) {
    const el = document.getElementById(id);
    if (el && text != null && text !== "") el.textContent = text;
  };
    if (device.battery != null) set("dev-battery", Math.round(Number(device.battery)) + "%");
  set("dev-signal", device.signal);
  set("dev-gps", device.gps_status);
  set("dev-updated", device.updated_label || session.updatedLabel);
  if (device.temperature != null) set("dev-temp", Math.round(Number(device.temperature)) + "°C");
  set("dev-sos", device.sos_active ? "Active" : "Inactive");
  set("device-status", device.online ? "● Connected" : "● Offline");
  set("home-status", device.online ? "● Online" : "● Offline");
  const gps = document.getElementById("dev-gps");
  if (gps) gps.style.color = device.gps_status === "Active" ? "var(--green)" : "var(--muted)";
  session.device = device;
}

function applyUser(user, location, device) {
  if (user) {
    session.firstName = user.first_name || session.firstName;
    session.surname = user.surname || "";
    session.username = user.username || session.username;
    session.birthDate = user.birth_date || "";
    session.homeAddress = user.home_address || "";
    session.country = user.country || "";
    const full = [session.firstName, session.surname].filter(Boolean).join(" ");
    session.name = user.name || full || session.name;
    session.deviceName = user.device_name || user.name || session.deviceName;
    session.deviceId = user.device_id || session.deviceId;
    session.email = user.email || "";
    session.phone = user.phone || "";
    if (user.avatar_url) session.avatarUrl = user.avatar_url;
  }
  if (location) applyLocation(location, false);
  if (device) paintDevice(device);
  paintIdentity();
}

function fillAccountForm() {
  const setVal = function (id, value) {
    const el = document.getElementById(id);
    if (!el || document.activeElement === el) return;
    el.value = value || "";
    if (id === "acct-country") paintCountryButton(id);
  };
  setVal("acct-first", session.firstName);
  setVal("acct-surname", session.surname);
  setVal("acct-user", session.username);
  setVal("acct-birth", session.birthDate);
  setVal("acct-address", session.homeAddress);
  setVal("acct-country", session.country);
  setVal("acct-email", session.email);
  setVal("acct-phone", session.phone);
}

function saveAuth(data) {
  localStorage.setItem("safetrack_token", data.token);
  applyUser(data.user, data.location, data.device);
}

function togglePassword(btn) {
  const field = btn.closest(".field");
  const input = field ? field.querySelector("input") : null;
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  btn.classList.toggle("on", show);
  btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  const open = btn.querySelector(".eye-open");
  const shut = btn.querySelector(".eye-shut");
  if (open) open.hidden = show;
  if (shut) shut.hidden = !show;
}

function releaseKeyboard() {
  const el = document.activeElement;
  if (el && el.blur) el.blur();
  window.scrollTo(0, 0);
}

async function signIn() {
  releaseKeyboard();
  const username = document.getElementById("input-user").value.trim();
  const password = document.getElementById("input-pass").value;
  if (!username || !password) {
    setSigninNote("Enter your username and password.");
    return;
  }
  setSigninNote("Signing in…");
  try {
    const data = await api("/api/auth/signin", {
      method: "POST",
      body: JSON.stringify({ username: username, password: password })
    });
    saveAuth(data);
    setSigninNote("Sign in with your username and password.");
    go("connect");
  } catch (err) {
    setSigninNote(err.message);
  }
}

function addRegisterDevice() {
  const list = document.getElementById("register-devices");
  if (!list) return;
  const wrap = document.createElement("div");
  wrap.className = "reg-device";
  wrap.style.marginTop = "4px";
  const nameField = document.createElement("div");
  nameField.className = "field";
  nameField.innerHTML = '<div class="fl"><label>Device name</label><input class="reg-devname" placeholder="Who carries this tracker"></div>';
  const idField = document.createElement("div");
  idField.className = "field";
  idField.innerHTML = '<div class="fl"><label>Device ID</label><input class="reg-devid" placeholder="e.g. 87654321"></div>';
  const remove = document.createElement("div");
  remove.className = "link-blue";
  remove.style.cssText = "font-size:12px;margin:-4px 0 10px;cursor:pointer;";
  remove.textContent = "Remove device";
  remove.onclick = function () { wrap.remove(); };
  wrap.appendChild(nameField);
  wrap.appendChild(idField);
  wrap.appendChild(remove);
  list.appendChild(wrap);
}

function registerDevices() {
  const rows = [];
  document.querySelectorAll(".reg-device").forEach(function (row) {
    const nameInput = row.querySelector(".reg-devname");
    const idInput = row.querySelector(".reg-devid");
    rows.push({
      name: nameInput ? nameInput.value.trim() : "",
      device_id: idInput ? idInput.value.trim() : ""
    });
  });
  return rows;
}

function setRegisterNote(msg) {
  const el = document.getElementById("register-note");
  if (el) el.textContent = msg;
}

async function createAccount() {
  releaseKeyboard();
  const first = document.getElementById("reg-first").value.trim();
  const surname = document.getElementById("reg-surname").value.trim();
  const username = document.getElementById("reg-user").value.trim();
  const password = document.getElementById("reg-pass").value;
  const birth = document.getElementById("reg-birth").value;
  const address = document.getElementById("reg-address").value.trim();
  const country = document.getElementById("reg-country").value;
  const devices = registerDevices().filter(function (row) { return row.name || row.device_id; });
  if (!first || !surname || !username || !password || !birth || !address || !country) {
    setRegisterNote("Enter your name, surname, username, and password, then select your date of birth and country.");
    return;
  }
  if (!devices.length) {
    setRegisterNote("Add at least one device name and Device ID.");
    return;
  }
  setRegisterNote("Creating your account…");
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        first_name: first,
        surname: surname,
        username: username,
        password: password,
        birth_date: birth,
        address: address,
        country: country,
        devices: devices
      })
    });
    saveAuth(data);
    setRegisterNote("Your details are the profile. Add every tracker that belongs with this account.");
    go("connect");
  } catch (err) {
    setRegisterNote(err.message);
  }
}

function signOut() {
  localStorage.removeItem("safetrack_token");
  toggleMenu(false);
  go("signin");
}

async function saveAccount() {
  const first = document.getElementById("acct-first").value.trim();
  const surname = document.getElementById("acct-surname").value.trim();
  const birth = document.getElementById("acct-birth").value;
  const address = document.getElementById("acct-address").value.trim();
  const country = document.getElementById("acct-country").value.trim();
  const email = document.getElementById("acct-email").value.trim();
  const phone = document.getElementById("acct-phone").value.trim();
  if (!localStorage.getItem("safetrack_token")) {
    session.firstName = first;
    session.surname = surname;
    session.name = [first, surname].filter(Boolean).join(" ");
    session.birthDate = birth;
    session.homeAddress = address;
    session.country = country;
    session.email = email;
    session.phone = phone;
    paintIdentity();
    go("settings");
    return;
  }
  try {
    const data = await api("/api/account", {
      method: "PATCH",
      body: JSON.stringify({
        first_name: first,
        surname: surname,
        birth_date: birth,
        address: address,
        country: country,
        email: email,
        phone: phone
      })
    });
    applyUser(data.user, null, null);
    go("settings");
  } catch (err) {
    alert(err.message);
  }
}

function pickPhoto() {
  const input = document.getElementById("photo-input");
  if (input) input.click();
}

async function uploadPhoto(input) {
  const file = input.files && input.files[0];
  input.value = "";
  if (!file) return;
  if (!localStorage.getItem("safetrack_token")) {
    alert("Sign in before changing your photo.");
    return;
  }
  const body = new FormData();
  body.append("photo", file);
  try {
    const data = await api("/api/account/photo", { method: "POST", body: body });
    session.avatarUrl = data.avatar_url;
    const bust = data.avatar_url + (data.avatar_url.indexOf("?") === -1 ? "?" : "&") + "v=" + Date.now();
    document.querySelectorAll(".dyn-avatar").forEach(function (img) {
      img.setAttribute("data-base", data.avatar_url);
      img.src = bust;
    });
  } catch (err) {
    alert(err.message);
  }
}

function mockScan() {
  const id = "ESP32-" + Math.floor(10000 + Math.random() * 89999);
  const inputs = document.querySelectorAll(".reg-devid");
  let target = inputs[0];
  inputs.forEach(function (input) {
    if (target && target.value.trim() && !input.value.trim()) target = input;
  });
  if (target) target.value = id;
  go("register");
}

function go(id) {
  toggleMenu(false);
  document.querySelectorAll(".screen").forEach(function (s) { s.classList.remove("active"); });
  const screen = document.getElementById("screen-" + id);
  if (!screen) return;
  screen.classList.add("active");
  rememberPlace();
  if (id === "home") {
    setTimeout(initHomeMap, 50);
    loadFamily();
  }
  if (id === "tracking") {
    setTimeout(initTrackingMap, 50);
    paintTrackCard();
  }
  if (id === "geofence") {
    setTimeout(initGeofenceMap, 50);
    loadGeofences();
  }
  if (id === "history") loadHistory();
  if (id === "family") loadFamily();
  if (id === "member") paintMember();
  if (id === "device-list") loadDeviceList();
  if (id === "device") loadDevice();
  if (id === "account") fillAccountForm();
  if (id === "directions") {
    setTimeout(initDirectionsMap, 50);
    renderDirections();
    paintLocation();
    paintTrackCard();
  }
  if (id === "connect") {
    setTimeout(function () {
      if (document.getElementById("screen-connect").classList.contains("active")) go("home");
    }, 1800);
  }
}

/* ---------- maps ---------- */
const mockPath = [
  [5.5600, -0.2050], [5.5620, -0.2035], [5.5645, -0.2010],
  [5.5665, -0.1985], [5.5690, -0.1965], [5.5715, -0.1940]
];
let mockIdx = 0;
let routeIdx = 0;
let homeMap, homeMarker, homeRoute;
let trackMap, trackMarker, trackRoute, trackDest;
let dirMap, dirMarker, dirRoute, dirDest;
let watch = {
  deviceId: "",
  name: "",
  photo: "",
  path: null,
  idx: 0,
  lat: null,
  lng: null,
  address: "",
  speed: 0,
  arrived: false,
  live: false
};

function watchingOther() {
  return !!(watch.deviceId && watch.deviceId !== session.deviceId);
}

function clearWatch() {
  watch.deviceId = "";
  watch.name = "";
  watch.photo = "";
  watch.path = null;
  watch.idx = 0;
  watch.lat = null;
  watch.lng = null;
  watch.address = "";
  watch.speed = 0;
  watch.arrived = false;
  watch.live = false;
}

function mapPoint() {
  if (watchingOther() && watch.lat != null && watch.lng != null) return [Number(watch.lat), Number(watch.lng)];
  return currentPoint();
}

function openMyMap() {
  clearWatch();
  go("tracking");
}
let geoMap, geoLayer;

function currentPoint() {
  if (session.lat != null && session.lng != null) return [Number(session.lat), Number(session.lng)];
  return mockPath[0];
}
function homeLine() {
  if (session.live && session.trail && session.trail.length) return session.trail;
  return [currentPoint()];
}
function trackLine() {
  if (session.live && session.trail && session.trail.length) return session.trail;
  return mockPath;
}

function initHomeMap() {
  if (typeof L === "undefined") return;
  if (homeMap) { homeMap.invalidateSize(); applyMapPoint(currentPoint()); return; }
  const point = currentPoint();
  homeMap = L.map("map-home", { zoomControl: true, attributionControl: false }).setView(point, 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(homeMap);
  homeRoute = L.polyline(homeLine(), { color: "#2f7bf6", weight: 5 }).addTo(homeMap);
  homeMarker = L.circleMarker(point, { radius: 8, color: "#fff", weight: 2, fillColor: "#2f7bf6", fillOpacity: 1 }).addTo(homeMap);
}

function trackedLine() {
  if (watchingOther() && watch.path && watch.path.length) return watch.path;
  return trackLine();
}

function initTrackingMap() {
  if (typeof L === "undefined") return;
  const point = mapPoint();
  const line = trackedLine();
  if (trackMap) {
    trackMap.invalidateSize();
    if (trackMarker) trackMarker.setLatLng(point);
    if (trackRoute) trackRoute.setLatLngs(line);
    if (trackDest) trackDest.setLatLng(line[line.length - 1]);
    trackMap.panTo(point);
    return;
  }
  trackMap = L.map("map-tracking", { zoomControl: true, attributionControl: false }).setView(point, 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(trackMap);
  trackRoute = L.polyline(line, { color: "#2f7bf6", weight: 5, opacity: 0.5 }).addTo(trackMap);
  trackMarker = L.circleMarker(point, { radius: 8, color: "#fff", weight: 2, fillColor: "#2f7bf6", fillOpacity: 1 }).addTo(trackMap);
  trackDest = L.circleMarker(line[line.length - 1], { radius: 7, color: "#fff", weight: 2, fillColor: "#e5484d", fillOpacity: 1 }).addTo(trackMap);
}

function routePath() {
  if (watchingOther() && watch.path && watch.path.length > 1) return watch.path;
  if (session.live && session.trail && session.trail.length > 1) return session.trail;
  return mockPath;
}

function metersBetween(a, b) {
  const earth = 6371000;
  const p1 = a[0] * Math.PI / 180;
  const p2 = b[0] * Math.PI / 180;
  const dphi = (b[0] - a[0]) * Math.PI / 180;
  const dlng = (b[1] - a[1]) * Math.PI / 180;
  const h = Math.sin(dphi / 2) * Math.sin(dphi / 2) + Math.cos(p1) * Math.cos(p2) * Math.sin(dlng / 2) * Math.sin(dlng / 2);
  return 2 * earth * Math.asin(Math.min(1, Math.sqrt(h)));
}

function bearingDeg(a, b) {
  const toRad = Math.PI / 180;
  const y = Math.sin((b[1] - a[1]) * toRad) * Math.cos(b[0] * toRad);
  const x = Math.cos(a[0] * toRad) * Math.sin(b[0] * toRad) - Math.sin(a[0] * toRad) * Math.cos(b[0] * toRad) * Math.cos((b[1] - a[1]) * toRad);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

function compassName(deg) {
  const names = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"];
  return names[Math.round(deg / 45) % 8];
}

function formatDist(meters) {
  if (meters >= 1000) return (meters / 1000).toFixed(1) + " km";
  return Math.round(meters) + " m";
}

function buildSteps(path) {
  const steps = [];
  for (let i = 0; i < path.length - 1; i++) {
    const dist = metersBetween(path[i], path[i + 1]);
    const dir = compassName(bearingDeg(path[i], path[i + 1]));
    let title = i === 0 ? "Head " + dir : "Continue " + dir;
    if (i > 0) {
      const prev = bearingDeg(path[i - 1], path[i]);
      const now = bearingDeg(path[i], path[i + 1]);
      const turn = (now - prev + 540) % 360 - 180;
      if (turn > 30) title = "Turn right";
      else if (turn < -30) title = "Turn left";
    }
    steps.push({ title: title, detail: formatDist(dist) + " along the route" });
  }
  if (watchingOther()) {
    steps.push({ title: "Arrive", detail: watch.address || "Their location" });
  } else {
    steps.push({ title: "Arrive at Work Place", detail: "Ring Road, Accra" });
  }
  return steps;
}

function renderDirections() {
  const list = document.getElementById("directions-list");
  const path = routePath();
  if (!list || path.length < 2) return;
  const steps = buildSteps(path);
  const index = Math.max(0, Math.min(routeIdx, steps.length - 1));
  const current = steps[index];
  const next = steps[index + 1];
  const kicker = document.getElementById("dir-kicker");
  const title = document.getElementById("dir-title");
  const detail = document.getElementById("dir-detail");
  if (kicker) {
    kicker.textContent = session.arrived
      ? "Arrived"
      : "Step " + (index + 1) + " of " + steps.length + " · Walking";
  }
  if (title) title.textContent = current.title;
  if (detail) {
    detail.textContent = next && !session.arrived
      ? current.detail + ". Next: " + next.title + "."
      : current.detail;
  }
  list.textContent = "";
  for (let i = 0; i <= index; i++) {
    const step = steps[i];
    const done = i < index;
    const row = document.createElement("div");
    row.className = "row" + (done ? " dir-done" : " dir-on");
    row.appendChild(iconBox(done ? "bg-green" : "bg-blue", done ? CHECK : PIN));
    const text = document.createElement("div");
    const t1 = document.createElement("div");
    t1.className = "t1";
    t1.textContent = step.title;
    const t2 = document.createElement("div");
    t2.className = "t2";
    t2.textContent = done ? "Passed" : step.detail;
    text.appendChild(t1);
    text.appendChild(t2);
    row.appendChild(text);
    list.appendChild(row);
  }
  const openRow = list.querySelector(".dir-on");
  if (openRow && openRow.scrollIntoView) openRow.scrollIntoView({ block: "nearest" });
}

function openDirections() {
  if (watchingOther() && watch.path && watch.path.length > 1) {
    watch.idx = 0;
    watch.arrived = false;
    watch.live = false;
    watch.lat = watch.path[0][0];
    watch.lng = watch.path[0][1];
    routeIdx = 0;
    session.arrived = false;
    go("directions");
    return;
  }
  if (!session.live) {
    routeIdx = 0;
    session.arrived = false;
    session.speed = 5;
    session.lat = mockPath[0][0];
    session.lng = mockPath[0][1];
    session.updatedLabel = "just now";
  } else {
    routeIdx = Math.max(0, routePath().length - 1);
    session.arrived = false;
  }
  go("directions");
}

function followRoute() {
  const path = routePath();
  if (path.length < 2) return;
  if (session.live) {
    routeIdx = path.length - 1;
  } else if (routeIdx < path.length - 1) {
    routeIdx += 1;
    session.lat = path[routeIdx][0];
    session.lng = path[routeIdx][1];
    session.updatedLabel = "just now";
  }
  session.arrived = !session.live && routeIdx >= path.length - 1;
  session.speed = session.arrived ? 0 : (session.speed || 5);
  applyMapPoint([Number(session.lat), Number(session.lng)]);
  paintLocation();
  renderDirections();
  rememberPlace();
}

function initDirectionsMap() {
  if (typeof L === "undefined") return;
  const point = mapPoint();
  const path = routePath();
  if (dirMap) {
    dirMap.invalidateSize();
    if (dirMarker) dirMarker.setLatLng(point);
    if (dirRoute) dirRoute.setLatLngs(path);
    if (dirDest) dirDest.setLatLng(path[path.length - 1]);
    dirMap.panTo(point);
    return;
  }
  dirMap = L.map("map-directions", { zoomControl: true, attributionControl: false }).setView(point, 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(dirMap);
  dirRoute = L.polyline(path, { color: "#2f7bf6", weight: 5, opacity: 0.85 }).addTo(dirMap);
  dirMarker = L.circleMarker(point, { radius: 8, color: "#fff", weight: 2, fillColor: "#2f7bf6", fillOpacity: 1 }).addTo(dirMap);
  dirDest = L.circleMarker(path[path.length - 1], { radius: 7, color: "#fff", weight: 2, fillColor: "#e5484d", fillOpacity: 1 }).addTo(dirMap);
}

function initGeofenceMap() {
  if (typeof L === "undefined") return;
  if (geoMap) { geoMap.invalidateSize(); drawZones(); return; }
  geoMap = L.map("map-geofence", { zoomControl: true, attributionControl: false }).setView(currentPoint(), 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19 }).addTo(geoMap);
  drawZones();
}

function applyMapPoint(point) {
  if (homeMap && homeMarker) {
    homeMarker.setLatLng(point);
    if (homeRoute) homeRoute.setLatLngs(homeLine());
    if (document.getElementById("screen-home").classList.contains("active")) homeMap.panTo(point);
  }
  if (!watchingOther() && trackMap && trackMarker) {
    trackMarker.setLatLng(point);
    if (trackRoute) trackRoute.setLatLngs(trackLine());
    if (trackDest) {
      trackDest.setLatLng(session.live ? point : mockPath[mockPath.length - 1]);
    }
    if (document.getElementById("screen-tracking").classList.contains("active")) trackMap.panTo(point);
  }
  if (!watchingOther() && dirMap && dirMarker) {
    dirMarker.setLatLng(point);
    if (dirRoute) dirRoute.setLatLngs(routePath());
    if (document.getElementById("screen-directions").classList.contains("active")) dirMap.panTo(point);
  }
}

function applyLocation(data, allowSos) {
  if (!data) return;
  if (data.lat != null && data.lng != null && (data.live || session.lat == null)) {
    session.lat = Number(data.lat);
    session.lng = Number(data.lng);
  }
  session.address = data.address || session.address;
  if (data.speed != null) session.speed = data.speed;
  session.updatedLabel = data.updated_label || session.updatedLabel;
  session.live = !!data.live;
  if (Array.isArray(data.trail) && data.trail.length) {
    session.trail = data.trail.map(function (p) { return [Number(p[0]), Number(p[1])]; });
  }
  paintLocation();
  if (data.device) paintDevice(data.device);
  if (session.lat != null) applyMapPoint([session.lat, session.lng]);
  if (allowSos !== false && data.device && data.device.sos_active && !session.sosDismissed) {
    const blocked = ["splash", "signin", "connect", "sos"].some(function (id) {
      return document.getElementById("screen-" + id).classList.contains("active");
    });
    if (!blocked) go("sos");
  }
  if (data.device && !data.device.sos_active) session.sosDismissed = false;
}

function stepMock() {
  if (!homeMap && !trackMap) return;
  const point = mockPath[mockIdx];
  mockIdx = (mockIdx + 1) % mockPath.length;
  if (homeMarker) homeMarker.setLatLng(point);
  if (homeMap && document.getElementById("screen-home").classList.contains("active")) homeMap.panTo(point);
  if (watchingOther()) return;
  if (trackMarker) trackMarker.setLatLng(point);
  if (trackMap && document.getElementById("screen-tracking").classList.contains("active")) trackMap.panTo(point);
  const upd = document.getElementById("home-updated");
  if (upd) upd.textContent = "just now";
}

function accountPhoto() {
  if (session.avatarUrl) return session.avatarUrl;
  const img = document.querySelector(".dyn-avatar");
  return img ? img.src : "";
}

function paintTrackCard() {
  const watching = watchingOther();
  const ownName = session.deviceName || session.name || "John Doe";
  const name = watching ? (watch.name || "Family") : ownName;
  const photo = watching ? (watch.photo || "") : (samePersonAndDevice() ? accountPhoto() : "");
  const speed = watching
    ? Math.round(Number(watch.speed) || (watch.arrived ? 0 : 5))
    : Math.round(Number(session.speed) || 5);
  const arrived = watching ? !!watch.arrived : !!session.arrived;
  const trackName = document.getElementById("track-name");
  const dirName = document.getElementById("dir-name");
  const trackMotion = document.getElementById("track-motion");
  const trackPlace = document.getElementById("track-place");
  const dirMotion = document.getElementById("dir-motion");
  if (trackName) trackName.textContent = name;
  if (dirName) dirName.textContent = name;
  setFace(document.getElementById("track-photo"), document.getElementById("track-initial"), photo, name);
  setFace(document.getElementById("dir-photo"), document.getElementById("dir-initial"), photo, name);
  if (trackMotion) {
    trackMotion.classList.toggle("moving", !arrived);
    trackMotion.textContent = arrived ? "● Arrived" : "● Moving • " + speed + " km/h";
  }
  if (dirMotion) {
    dirMotion.classList.toggle("moving", !arrived);
    dirMotion.textContent = arrived ? "● Arrived" : "● Walking • " + speed + " km/h";
  }
  if (trackPlace) trackPlace.textContent = watching && watch.address ? watch.address : "Destination — Work Place";
}

function moveWatchedMarker(point, path) {
  if (trackMarker) trackMarker.setLatLng(point);
  if (trackRoute && path) trackRoute.setLatLngs(path);
  if (trackMap && document.getElementById("screen-tracking").classList.contains("active")) trackMap.panTo(point);
  if (dirMarker) dirMarker.setLatLng(point);
  if (dirRoute && path) dirRoute.setLatLngs(path);
  if (dirMap && document.getElementById("screen-directions").classList.contains("active")) dirMap.panTo(point);
}

function stepWatch() {
  const path = watch.path;
  if (!path || path.length < 2 || watch.live) return;
  if (watch.idx < path.length - 1) watch.idx += 1;
  const point = path[watch.idx];
  watch.lat = point[0];
  watch.lng = point[1];
  watch.arrived = watch.idx >= path.length - 1;
  if (watch.arrived) watch.speed = 0;
  routeIdx = watch.idx;
  session.arrived = watch.arrived;
  moveWatchedMarker(point, path);
  paintTrackCard();
  if (document.getElementById("screen-directions").classList.contains("active")) renderDirections();
  rememberPlace();
}

async function followWatch() {
  if (!watch.live) {
    stepWatch();
    return;
  }
  try {
    const data = await api("/api/location/" + encodeURIComponent(watch.deviceId));
    if (data.lat != null) {
      watch.lat = Number(data.lat);
      watch.lng = Number(data.lng);
    }
    if (data.address) watch.address = data.address;
    if (data.speed != null) watch.speed = data.speed;
    if (Array.isArray(data.trail) && data.trail.length) {
      watch.path = data.trail.map(function (p) { return [Number(p[0]), Number(p[1])]; });
    }
    moveWatchedMarker([watch.lat, watch.lng], watch.path);
    paintTrackCard();
    rememberPlace();
  } catch (err) {
    if (err.status === 401) signOut();
  }
}

async function pollLocation() {
  const tracking = document.getElementById("screen-tracking").classList.contains("active");
  const directions = document.getElementById("screen-directions").classList.contains("active");
  if (watchingOther() && (tracking || directions)) {
    await followWatch();
    return;
  }
  if (!localStorage.getItem("safetrack_token") || !session.deviceId) {
    stepMock();
    return;
  }
  try {
    const data = await api("/api/location/" + encodeURIComponent(session.deviceId));
    applyLocation(data, true);
    if (directions) followRoute();
  } catch (err) {
    if (err.status === 401) signOut();
    else stepMock();
  }
}
setInterval(pollLocation, 3000);

function iconBox(bg, svg) {
  const ic = document.createElement("div");
  ic.className = "ic " + bg;
  const i = document.createElement("i");
  i.className = "ico";
  i.style.width = "1em";
  i.style.height = "1em";
  i.innerHTML = svg;
  ic.appendChild(i);
  return ic;
}

let selectedMember = null;
let selectedDeviceId = "";

function memberPhoto(member) {
  if (member.name === session.name && session.avatarUrl) return session.avatarUrl;
  return member.avatar_url || "";
}

function renderFamily(list, members, onlyOthers) {
  if (!list) return;
  const rows = onlyOthers
    ? members.filter(function (member) { return member.device_id && member.device_id !== session.deviceId; })
    : members;
  list.textContent = "";
  rows.forEach(function (member) {
    const row = document.createElement("div");
    row.className = "row";
    row.setAttribute("role", "button");
    row.setAttribute("data-name", member.name || "");
    row.setAttribute("data-status", member.status_text || "Offline");
    row.setAttribute("data-device", member.device_id || "");
    row.setAttribute("data-photo", memberPhoto(member));
    row.setAttribute("data-online", member.online ? "1" : "0");
    row.setAttribute("data-address", member.address || "");
    row.setAttribute("data-lat", member.lat != null ? String(member.lat) : "");
    row.setAttribute("data-lng", member.lng != null ? String(member.lng) : "");
    const ic = document.createElement("div");
    ic.className = "ic " + (member.online ? "bg-green" : "bg-muted");
    ic.style.borderRadius = "50%";
    ic.style.overflow = "hidden";
    const photo = memberPhoto(member);
    if (photo) {
      const img = document.createElement("img");
      img.src = photo;
      img.alt = "";
      img.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:inherit;";
      ic.appendChild(img);
    } else {
      ic.textContent = (member.name || "?").trim().charAt(0).toUpperCase();
    }
    const text = document.createElement("div");
    const t1 = document.createElement("div");
    t1.className = "t1";
    t1.textContent = member.name;
    const t2 = document.createElement("div");
    t2.className = "t2";
    const status = member.status_text || "Offline";
    t2.textContent = member.device_id ? member.device_id + " · " + status : status;
    text.appendChild(t1);
    text.appendChild(t2);
    const chev = document.createElement("span");
    chev.className = "chev";
    chev.textContent = "›";
    row.appendChild(ic);
    row.appendChild(text);
    row.appendChild(chev);
    list.appendChild(row);
  });
}

function memberFromRow(row) {
  const lat = row.getAttribute("data-lat");
  const lng = row.getAttribute("data-lng");
  return {
    name: row.getAttribute("data-name") || (row.querySelector(".t1") ? row.querySelector(".t1").textContent : ""),
    status_text: row.getAttribute("data-status") || (row.querySelector(".t2") ? row.querySelector(".t2").textContent : "Offline"),
    device_id: row.getAttribute("data-device") || "",
    avatar_url: row.getAttribute("data-photo") || "",
    online: row.getAttribute("data-online") === "1",
    address: row.getAttribute("data-address") || "",
    lat: lat ? Number(lat) : null,
    lng: lng ? Number(lng) : null
  };
}

function applyWatchLocation(data) {
  watch.live = !!data.live;
  watch.address = data.address || watch.address;
  if (data.speed != null) watch.speed = data.speed;
  if (watch.live) {
    if (data.lat != null) watch.lat = Number(data.lat);
    if (data.lng != null) watch.lng = Number(data.lng);
    watch.path = Array.isArray(data.trail) && data.trail.length
      ? data.trail.map(function (p) { return [Number(p[0]), Number(p[1])]; })
      : (watch.lat != null ? [[watch.lat, watch.lng]] : null);
    watch.idx = watch.path ? Math.max(0, watch.path.length - 1) : 0;
    watch.arrived = false;
    return;
  }
  const path = Array.isArray(data.path)
    ? data.path.map(function (p) { return [Number(p[0]), Number(p[1])]; })
    : [];
  watch.path = path.length > 1 ? path : null;
  if (watch.path) {
    watch.idx = 0;
    watch.lat = watch.path[0][0];
    watch.lng = watch.path[0][1];
  } else if (data.lat != null) {
    watch.lat = Number(data.lat);
    watch.lng = Number(data.lng);
  }
  watch.arrived = false;
}

async function trackMember(member) {
  if (!member || !member.device_id || member.device_id === session.deviceId) {
    openMyMap();
    return;
  }
  watch.deviceId = member.device_id;
  watch.name = member.name || "";
  watch.photo = memberPhoto(member);
  watch.address = member.address || "";
  watch.lat = member.lat != null ? Number(member.lat) : null;
  watch.lng = member.lng != null ? Number(member.lng) : null;
  watch.path = null;
  watch.idx = 0;
  watch.arrived = false;
  watch.live = false;
  watch.speed = 5;
  try {
    const data = await api("/api/location/" + encodeURIComponent(watch.deviceId));
    applyWatchLocation(data);
  } catch (err) {
    watch.address = err.message || "Location unavailable";
  }
  go("tracking");
}

function paintMember() {
  const member = selectedMember;
  if (!member) return;
  const name = document.getElementById("member-name");
  const status = document.getElementById("member-status");
  const detail = document.getElementById("member-detail");
  const device = document.getElementById("member-device");
  const photo = document.getElementById("member-photo");
  const initial = document.getElementById("member-initial");
  if (name) name.textContent = member.name || "Family Member";
  if (detail) detail.textContent = member.status_text || "Offline";
  if (status) {
    status.textContent = member.online ? "● Online" : "● Offline";
    status.style.color = member.online ? "var(--green)" : "var(--muted)";
  }
  if (device) device.textContent = member.device_id ? member.device_id : "Not linked";
  if (photo && initial) {
    if (member.avatar_url) {
      photo.style.display = "";
      photo.src = member.avatar_url;
      initial.style.display = "none";
    } else {
      photo.style.display = "none";
      initial.style.display = "";
      initial.textContent = (member.name || "?").trim().charAt(0).toUpperCase();
    }
  }
}

function openAddFamily() {
  const note = document.getElementById("family-note");
  const name = document.getElementById("family-name");
  const device = document.getElementById("family-devid");
  if (note) note.textContent = "The device name is who carries this tracker.";
  if (name) name.value = "";
  if (device) device.value = "";
  go("add-family");
}

async function submitFamilyMember() {
  const nameInput = document.getElementById("family-name");
  const deviceInput = document.getElementById("family-devid");
  const note = document.getElementById("family-note");
  const name = nameInput ? nameInput.value.trim() : "";
  const deviceId = deviceInput ? deviceInput.value.trim() : "";
  if (!name) {
    if (note) note.textContent = "Enter the device name.";
    return;
  }
  if (!deviceId) {
    if (note) note.textContent = "Each person needs their own Device ID.";
    return;
  }
  if (note) note.textContent = "Adding…";
  try {
    await api("/api/family", {
      method: "POST",
      body: JSON.stringify({ name: name, device_id: deviceId })
    });
    go("family");
  } catch (err) {
    if (note) note.textContent = err.message;
  }
}

async function loadFamily() {
  if (!localStorage.getItem("safetrack_token")) return;
  try {
    const data = await api("/api/family");
    renderFamily(document.getElementById("family-list"), data.members || [], false);
    renderFamily(document.getElementById("home-family"), data.members || [], false);
  } catch (err) { /* keep the designed list if the server is unreachable */ }
}

function bindFamilyList() {
  document.querySelectorAll("[data-family-list]").forEach(function (list) {
    if (list.dataset.bound) return;
    list.dataset.bound = "1";
    list.addEventListener("click", function (event) {
      const row = event.target.closest(".row");
      if (!row || !list.contains(row)) return;
      const member = memberFromRow(row);
      const img = row.querySelector("img");
      if (!member.avatar_url && img) member.avatar_url = img.getAttribute("src") || "";
      selectedMember = member;
      trackMember(member);
    });
  });
}

function renderHistory(groups) {
  const list = document.getElementById("history-list");
  if (!list) return;
  list.textContent = "";
  const icons = { arrived: ["bg-blue", PIN], left: ["bg-muted", CLOCK], sos: ["bg-red", ALERT] };
  groups.forEach(function (group) {
    const title = document.createElement("div");
    title.className = "section-title";
    title.style.paddingLeft = "0";
    title.textContent = group.label;
    list.appendChild(title);
    (group.items || []).forEach(function (item) {
      const meta = icons[item.kind] || icons.arrived;
      const row = document.createElement("div");
      row.className = "row";
      row.appendChild(iconBox(meta[0], meta[1]));
      const text = document.createElement("div");
      const t1 = document.createElement("div");
      t1.className = "t1";
      t1.textContent = item.title;
      const t2 = document.createElement("div");
      t2.className = "t2";
      t2.textContent = item.detail;
      text.appendChild(t1);
      text.appendChild(t2);
      row.appendChild(text);
      list.appendChild(row);
    });
  });
}

async function loadHistory() {
  if (!localStorage.getItem("safetrack_token")) return;
  try {
    const data = await api("/api/history");
    if (data.groups) renderHistory(data.groups);
  } catch (err) { /* keep the designed list */ }
}

let geoZones = null;

function drawZones() {
  if (!geoMap) return;
  if (geoLayer) geoMap.removeLayer(geoLayer);
  geoLayer = L.layerGroup().addTo(geoMap);
  const zones = (geoZones || []).filter(function (z) { return z.configured && z.lat != null && z.lng != null; });
  const draw = zones.length ? zones : [{ lat: mockPath[0][0], lng: mockPath[0][1], radius_m: 200 }];
  draw.forEach(function (z) {
    L.circle([Number(z.lat), Number(z.lng)], {
      radius: z.radius_m || 200,
      color: "#2f7bf6",
      weight: 2,
      fillColor: "#2f7bf6",
      fillOpacity: 0.15
    }).addTo(geoLayer);
    L.circleMarker([Number(z.lat), Number(z.lng)], {
      radius: 7, color: "#fff", weight: 2, fillColor: "#2f7bf6", fillOpacity: 1
    }).addTo(geoLayer);
  });
}

function renderGeofences(zones) {
  const list = document.getElementById("geofence-list");
  if (!list) return;
  list.textContent = "";
  zones.forEach(function (zone) {
    const row = document.createElement("div");
    row.className = "row";
    row.appendChild(iconBox(zone.configured ? "bg-blue" : "bg-muted", ZONE));
    const text = document.createElement("div");
    const t1 = document.createElement("div");
    t1.className = "t1";
    t1.textContent = zone.name;
    const t2 = document.createElement("div");
    t2.className = "t2";
    t2.textContent = zone.detail;
    text.appendChild(t1);
    text.appendChild(t2);
    const chev = document.createElement("span");
    chev.className = "chev";
    chev.textContent = "›";
    row.appendChild(text);
    row.appendChild(chev);
    list.appendChild(row);
  });
}

async function loadGeofences() {
  if (!localStorage.getItem("safetrack_token")) return;
  try {
    const data = await api("/api/geofences");
    geoZones = data.zones || [];
    renderGeofences(geoZones);
    drawZones();
  } catch (err) { /* keep the designed list */ }
}

async function addSafeZone() {
  const name = prompt("Safe zone name");
  if (!name || !name.trim()) return;
  const address = prompt("Address") || "";
  const radius = prompt("Radius in meters", "200") || "200";
  try {
    await api("/api/geofences", {
      method: "POST",
      body: JSON.stringify({
        name: name.trim(),
        address: address.trim(),
        radius_m: Number(radius) || 200,
        lat: session.lat,
        lng: session.lng
      })
    });
    loadGeofences();
  } catch (err) {
    alert(err.message);
  }
}

function paintDeviceQr(deviceId) {
  const box = document.getElementById("dev-qr");
  if (!box) return;
  box.textContent = "";
  if (window.QRCode) {
    new QRCode(box, { text: String(deviceId), width: 148, height: 148 });
    return;
  }
  box.textContent = deviceId;
}

async function loadDeviceList() {
  const list = document.getElementById("device-list");
  if (!list || !localStorage.getItem("safetrack_token")) return;
  try {
    const data = await api("/api/family");
    const members = data.members || [];
    list.textContent = "";
    members.forEach(function (member) {
      if (!member.device_id) return;
      const row = document.createElement("div");
      row.className = "row";
      const ic = document.createElement("div");
      ic.className = "ic " + (member.online ? "bg-green" : "bg-muted");
      ic.style.borderRadius = "50%";
      ic.textContent = (member.name || "?").trim().charAt(0).toUpperCase();
      const text = document.createElement("div");
      const t1 = document.createElement("div");
      t1.className = "t1";
      t1.textContent = member.name || "Device";
      const t2 = document.createElement("div");
      t2.className = "t2";
      const bits = [member.device_id];
      if (member.battery != null) bits.push(Math.round(Number(member.battery)) + "% battery");
      t2.textContent = bits.join(" · ");
      text.appendChild(t1);
      text.appendChild(t2);
      const chev = document.createElement("span");
      chev.className = "chev";
      chev.textContent = "›";
      row.appendChild(ic);
      row.appendChild(text);
      row.appendChild(chev);
      row.addEventListener("click", function () {
        selectedDeviceId = member.device_id;
        go("device");
      });
      list.appendChild(row);
    });
  } catch (err) { /* keep the list empty until the server answers */ }
}

async function loadDevice() {
  const id = selectedDeviceId || session.deviceId;
  if (!id || !localStorage.getItem("safetrack_token")) return;
  selectedDeviceId = id;
  try {
    const data = await api("/api/device/" + encodeURIComponent(id));
    if (data.device) paintDevice(data.device);
    const person = document.getElementById("device-person");
    if (person) person.textContent = data.name || (data.device && data.device.name) || "Device";
    const label = document.getElementById("device-id-label");
    if (label) label.textContent = "Device ID: " + id;
    paintDeviceQr(id);
  } catch (err) {
    const status = document.getElementById("device-status");
    if (status) status.textContent = err.message;
  }
}

async function playBeep() {
  const id = selectedDeviceId || session.deviceId;
  if (!localStorage.getItem("safetrack_token") || !id) return;
  try {
    await api("/api/device/beep", { method: "POST", body: JSON.stringify({ device_id: id }) });
    const el = document.getElementById("device-status");
    if (el) {
      el.textContent = "● Beep sent";
      setTimeout(function () { loadDevice(); }, 1600);
    }
  } catch (err) {
    const el = document.getElementById("device-status");
    if (el) el.textContent = err.message;
  }
}

async function disconnectDevice() {
  const id = selectedDeviceId || session.deviceId;
  if (!id || !localStorage.getItem("safetrack_token")) return;
  if (!window.confirm("Disconnect this device?")) return;
  try {
    const data = await api("/api/device/disconnect", {
      method: "POST",
      body: JSON.stringify({ device_id: id })
    });
    if (data.token) {
      saveAuth(data);
      selectedDeviceId = session.deviceId || "";
    } else {
      selectedDeviceId = "";
    }
    go("device-list");
  } catch (err) {
    const el = document.getElementById("device-status");
    if (el) el.textContent = err.message;
  }
}

async function dismissSos() {
  session.sosDismissed = true;
  try { await api("/api/sos/dismiss", { method: "POST", body: "{}" }); } catch (e) { /* still leave the screen */ }
  go("home");
}

function savedScreen() {
  const fromHash = (location.hash || "").replace(/^#/, "");
  if (fromHash && document.getElementById("screen-" + fromHash)) return fromHash;
  const stored = localStorage.getItem("safetrack_screen");
  if (stored && document.getElementById("screen-" + stored)) return stored;
  return "";
}

function rememberPlace() {
  const active = document.querySelector(".screen.active");
  if (!active) return;
  const id = active.id.replace("screen-", "");
  localStorage.setItem("safetrack_screen", id);
  localStorage.setItem("safetrack_route", JSON.stringify({
    routeIdx: routeIdx,
    lat: session.lat,
    lng: session.lng,
    arrived: !!session.arrived,
    speed: session.speed
  }));
  localStorage.setItem("safetrack_device", selectedDeviceId || "");
  localStorage.setItem("safetrack_watch", JSON.stringify({
    deviceId: watch.deviceId,
    name: watch.name,
    photo: watch.photo,
    path: watch.path,
    idx: watch.idx,
    lat: watch.lat,
    lng: watch.lng,
    address: watch.address,
    speed: watch.speed,
    arrived: !!watch.arrived,
    live: !!watch.live
  }));
  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
}

function restoreWatch() {
  const raw = localStorage.getItem("safetrack_watch");
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    if (!data || !data.deviceId || data.deviceId === session.deviceId) return;
    watch.deviceId = data.deviceId;
    watch.name = data.name || "";
    watch.photo = data.photo || "";
    watch.path = Array.isArray(data.path) ? data.path : null;
    watch.idx = typeof data.idx === "number" ? data.idx : 0;
    watch.lat = data.lat;
    watch.lng = data.lng;
    watch.address = data.address || "";
    watch.speed = data.speed || 0;
    watch.arrived = !!data.arrived;
    watch.live = !!data.live;
    routeIdx = watch.idx;
    session.arrived = watch.arrived;
  } catch (e) { /* keep the signed-in map */ }
}
function restoreRoute() {
  const raw = localStorage.getItem("safetrack_route");
  if (!raw) return;
  try {
    const data = JSON.parse(raw);
    if (typeof data.routeIdx === "number") routeIdx = data.routeIdx;
    if (data.lat != null) session.lat = Number(data.lat);
    if (data.lng != null) session.lng = Number(data.lng);
    session.arrived = !!data.arrived;
    if (data.speed != null) session.speed = data.speed;
  } catch (e) { /* keep the starting step */ }
}

function openDatePicker(input) {
  if (input && input.showPicker) {
    try { input.showPicker(); } catch (err) { /* the field still opens its own calendar */ }
  }
}

const COUNTRIES = [
  "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria",
  "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan",
  "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia",
  "Cameroon", "Canada", "Central African Republic", "Chad", "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica",
  "Croatia", "Cuba", "Cyprus", "Czechia", "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt",
  "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon",
  "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau", "Guyana",
  "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland", "Israel",
  "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos",
  "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Madagascar", "Malawi",
  "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova",
  "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal", "Netherlands",
  "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
  "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania",
  "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal",
  "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea",
  "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan",
  "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu",
  "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City", "Venezuela",
  "Vietnam", "Yemen", "Zambia", "Zimbabwe"
];

function paintCountryButton(id) {
  const input = document.getElementById(id);
  const button = document.querySelector('.country-btn[data-for="' + id + '"]');
  if (!input || !button) return;
  if (input.value) {
    button.textContent = input.value;
    button.classList.remove("placeholder");
  } else {
    button.textContent = "Select country";
    button.classList.add("placeholder");
  }
}

function closeCountryMenu() {
  const menu = document.getElementById("country-menu");
  if (menu) menu.classList.remove("open");
}

function openCountryMenu(button, event) {
  if (event) event.stopPropagation();
  const id = button.getAttribute("data-for");
  const input = document.getElementById(id);
  const phone = document.querySelector(".phone");
  const menu = document.getElementById("country-menu");
  if (!input || !phone || !menu) return;
  if (menu.classList.contains("open") && menu.getAttribute("data-for") === id) {
    closeCountryMenu();
    return;
  }
  menu.textContent = "";
  menu.setAttribute("data-for", id);
  COUNTRIES.forEach(function (name) {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = name;
    if (name === input.value) item.className = "on";
    item.addEventListener("click", function (e) {
      e.stopPropagation();
      input.value = name;
      paintCountryButton(id);
      closeCountryMenu();
    });
    menu.appendChild(item);
  });
  const field = button.closest(".field");
  const phoneRect = phone.getBoundingClientRect();
  const fieldRect = field.getBoundingClientRect();
  const roomBelow = phoneRect.bottom - fieldRect.bottom - 12;
  const roomAbove = fieldRect.top - phoneRect.top - 12;
  const openUp = roomBelow < 180 && roomAbove > roomBelow;
  menu.style.width = fieldRect.width + "px";
  menu.style.left = (fieldRect.left - phoneRect.left) + "px";
  menu.style.maxHeight = Math.max(120, Math.min(240, openUp ? roomAbove : roomBelow)) + "px";
  if (openUp) {
    menu.style.top = "auto";
    menu.style.bottom = (phoneRect.bottom - fieldRect.top + 6) + "px";
  } else {
    menu.style.bottom = "auto";
    menu.style.top = (fieldRect.bottom - phoneRect.top + 6) + "px";
  }
  menu.classList.add("open");
  const selected = menu.querySelector(".on");
  if (selected) selected.scrollIntoView({ block: "nearest" });
}

function fillCountryLists() {
  paintCountryButton("reg-country");
  paintCountryButton("acct-country");
}

function prepareBirthFields() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  const today = now.getFullYear() + "-" + month + "-" + day;
  document.querySelectorAll("#reg-birth, #acct-birth").forEach(function (input) {
    input.min = "1900-01-01";
    input.max = today;
  });
}

document.addEventListener("DOMContentLoaded", async function () {
  fillCountryLists();
  prepareBirthFields();
  selectedDeviceId = localStorage.getItem("safetrack_device") || "";
  document.addEventListener("click", closeCountryMenu);
  document.querySelectorAll(".auth-body").forEach(function (el) {
    el.addEventListener("scroll", closeCountryMenu);
  });
  bindFamilyList();
  restoreRoute();
  restoreWatch();
  const token = localStorage.getItem("safetrack_token");
  if (token) {
    try {
      const data = await api("/api/me");
      applyUser(data.user, data.location, data.device);
    } catch (err) {
      if (err.status === 401) localStorage.removeItem("safetrack_token");
    }
  }
  const id = savedScreen();
  if (id) go(id);
});
