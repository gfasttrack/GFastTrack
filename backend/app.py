"""GFastTrack API.

Users live in Neon (Postgres). Profile photos live in Cloudinary.
A GFastTrack tracker posts telemetry to /api/ingest/<device_id>.
The web app reads that data from this server. It does not talk to the tracker.
"""

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import urllib.request
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

import cloudinary
import cloudinary.uploader
import psycopg
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parent / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ADMIN = Path(__file__).resolve().parent.parent / "admin"
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{3,32}$")
TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Africa/Accra"))
_db_ready = False
_db_lock = threading.Lock()

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        phone TEXT,
        device_id TEXT UNIQUE NOT NULL,
        device_name TEXT,
        avatar_url TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS device_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS surname TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS address TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS country TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS users_username ON users (username) WHERE username IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        name TEXT,
        battery INTEGER DEFAULT 85,
        signal TEXT DEFAULT 'Good',
        gps_status TEXT DEFAULT 'Active',
        temperature DOUBLE PRECISION,
        speed DOUBLE PRECISION DEFAULT 0,
        sos_active BOOLEAN DEFAULT FALSE,
        online BOOLEAN DEFAULT FALSE,
        has_live_fix BOOLEAN DEFAULT FALSE,
        lat DOUBLE PRECISION,
        lng DOUBLE PRECISION,
        address TEXT,
        last_seen TIMESTAMPTZ
    )
    """,
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS name TEXT",
    """
    CREATE TABLE IF NOT EXISTS locations (
        id SERIAL PRIMARY KEY,
        device_id TEXT NOT NULL,
        lat DOUBLE PRECISION NOT NULL,
        lng DOUBLE PRECISION NOT NULL,
        speed DOUBLE PRECISION,
        address TEXT,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS locations_device_time ON locations (device_id, recorded_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS family_members (
        id SERIAL PRIMARY KEY,
        owner_device_id TEXT NOT NULL,
        name TEXT NOT NULL,
        device_id TEXT,
        avatar_url TEXT,
        status_text TEXT,
        online BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS family_owner ON family_members (owner_device_id)",
    """
    CREATE TABLE IF NOT EXISTS geofences (
        id SERIAL PRIMARY KEY,
        device_id TEXT NOT NULL,
        name TEXT NOT NULL,
        address TEXT,
        lat DOUBLE PRECISION,
        lng DOUBLE PRECISION,
        radius_m INTEGER DEFAULT 200,
        configured BOOLEAN DEFAULT TRUE,
        inside BOOLEAN DEFAULT FALSE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY,
        device_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        place TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS events_device_time ON events (device_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS device_commands (
        id SERIAL PRIMARY KEY,
        device_id TEXT NOT NULL,
        command TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        consumed BOOLEAN DEFAULT FALSE
    )
    """,
]


def cors_origins():
    raw = os.getenv("FRONTEND_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return "*"
    return [item.strip() for item in raw.split(",") if item.strip()]


CORS(
    app,
    resources={r"/api/*": {"origins": cors_origins()}},
    allow_headers=["Content-Type", "Authorization", "X-Device-Key"],
    methods=["GET", "POST", "PATCH", "OPTIONS"],
)


def database_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def connect():
    return psycopg.connect(database_url(), row_factory=dict_row)


def db_exec(sql, params=(), fetch=None):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch == "one":
                return cur.fetchone()
            if fetch == "all":
                return cur.fetchall()
            return None


def fail(message, code):
    return jsonify(error=message), code


def ensure_db():
    global _db_ready
    if _db_ready:
        return
    with _db_lock:
        if _db_ready:
            return
        for statement in SCHEMA:
            db_exec(statement)
        _db_ready = True


def local_mode():
    return not database_url()


def require_db(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if local_mode():
            local_store()
            return fn(*args, **kwargs)
        try:
            ensure_db()
        except Exception:
            app.logger.exception("Neon connection failed")
            return fail("Could not connect to Neon. Check DATABASE_URL.", 503)
        return fn(*args, **kwargs)
    return wrapper


def hash_password(password):
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return f"{salt}${digest}"


def check_password(password, stored):
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return hmac.compare_digest(check, digest)


def clean_username(value):
    value = (value or "").strip()
    if not USERNAME_RE.fullmatch(value):
        return None
    return value


def clean_birth_date(value):
    text = (value or "").strip()
    try:
        day = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = datetime.now(TZ).date()
    if day > today or day.year < 1900:
        return None
    return day.isoformat()


COUNTRIES = {
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
    "Vietnam", "Yemen", "Zambia", "Zimbabwe",
}


def read_devices(data):
    found = []
    raw = data.get("devices")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            found.append(((item.get("name") or "").strip(), clean_device_id(item.get("device_id"))))
    if not found:
        found.append(((data.get("device_name") or "").strip(), clean_device_id(data.get("device_id"))))
    devices = []
    for name, device_id in found:
        if not name and not device_id:
            continue
        if not name or len(name) > 80 or not device_id:
            return None
        devices.append({"name": name, "device_id": device_id})
    if len(devices) != len({item["device_id"] for item in devices}):
        return None
    return devices


def secret():
    return os.getenv("SECRET_KEY", "dev-only-change-me")


def issue_token(user):
    payload = json.dumps(
        {"uid": user["id"], "did": user["device_id"], "exp": int(datetime.now(TZ).timestamp()) + 14 * 24 * 3600},
        separators=(",", ":"),
    ).encode()
    import base64
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    sig = hmac.new(secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def read_token(token):
    import base64
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    padded = body + "=" * (-len(body) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (json.JSONDecodeError, ValueError):
        return None
    if int(data.get("exp", 0)) < int(datetime.now(TZ).timestamp()):
        return None
    return data


def current_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    data = read_token(header[7:].strip())
    if not data or "uid" not in data or "did" not in data:
        return None
    if local_mode():
        user = local_store().users_by_id.get(data["uid"])
        if user and user["device_id"] == data["did"]:
            return user
        return None
    return db_exec(
        "SELECT * FROM users WHERE id = %s AND device_id = %s",
        (data["uid"], data["did"]),
        fetch="one",
    )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return fail("Sign in again.", 401)
        request.user = user
        return fn(*args, **kwargs)
    return wrapper


def clean_device_id(value):
    value = (value or "").strip()
    if not DEVICE_RE.fullmatch(value):
        return None
    return value


def body_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return None


def ago(dt):
    if not isinstance(dt, datetime):
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    secs = int((datetime.now(TZ) - dt.astimezone(TZ)).total_seconds())
    if secs < 20:
        return "just now"
    if secs < 60:
        return f"{secs} sec ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours} h ago"
    return f"{hours // 24} d ago"


def clock(dt):
    local = dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)
    hour = local.hour
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{local.minute:02d} {suffix}"


def day_label(dt):
    local = dt.astimezone(TZ) if dt.tzinfo else dt.replace(tzinfo=TZ)
    today = datetime.now(TZ).date()
    if local.date() == today:
        return "Today"
    if local.date() == today - timedelta(days=1):
        return "Yesterday"
    return local.strftime("%b %d")


def public_user(row):
    first = row.get("first_name") or row["name"]
    surname = row.get("surname") or ""
    full = " ".join(part for part in (first, surname) if part).strip() or row["name"]
    birth = row.get("birth_date")
    if hasattr(birth, "isoformat"):
        birth = birth.isoformat()
    return {
        "id": row["id"],
        "name": full,
        "first_name": first,
        "surname": surname,
        "username": row.get("username") or "",
        "birth_date": birth or "",
        "home_address": row.get("address") or "",
        "country": row.get("country") or "",
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "device_id": row["device_id"],
        "device_name": row.get("device_name") or full,
        "avatar_url": row["avatar_url"] or "",
    }


def device_row(device_id):
    if local_mode():
        return local_store().devices.get(device_id)
    return db_exec("SELECT * FROM devices WHERE device_id = %s", (device_id,), fetch="one")


def public_device(row):
    if not row:
        return None
    seen = row["last_seen"]
    online = False
    if row.get("has_live_fix") and isinstance(seen, datetime):
        moment = seen if seen.tzinfo else seen.replace(tzinfo=TZ)
        online = (datetime.now(TZ) - moment.astimezone(TZ)).total_seconds() < 180
    signal = (row.get("signal") or "").strip()
    return {
        "device_id": row["device_id"],
        "name": row.get("name") or "",
        "battery": row["battery"],
        "signal": signal or None,
        "gps_status": "Active" if row.get("has_live_fix") else "Waiting",
        "temperature": row["temperature"],
        "speed": row["speed"],
        "sos_active": bool(row["sos_active"]),
        "online": online,
        "has_live_fix": bool(row.get("has_live_fix")),
        "lat": row.get("lat") if row.get("has_live_fix") else None,
        "lng": row.get("lng") if row.get("has_live_fix") else None,
        "address": (row.get("address") or "") if row.get("has_live_fix") else "",
        "updated_label": ago(seen) if seen else "No update yet",
    }


def public_location(row):
    device = public_device(row) if row else None
    if not row or not row.get("has_live_fix") or row["lat"] is None or row["lng"] is None:
        return {
            "lat": None,
            "lng": None,
            "address": "",
            "speed": None if not row else row["speed"],
            "updated_label": "No update yet" if not row else (ago(row["last_seen"]) if row.get("last_seen") else "No update yet"),
            "live": False,
            "trail": [],
            "path": [],
            "device": device,
        }
    if local_mode():
        points = [p for p in local_store().locations if p["device_id"] == row["device_id"]][-40:]
    else:
        points = db_exec(
            "SELECT lat, lng FROM locations WHERE device_id = %s ORDER BY recorded_at DESC LIMIT 40",
            (row["device_id"],),
            fetch="all",
        )
        points = list(reversed(points))
    return {
        "lat": row["lat"],
        "lng": row["lng"],
        "address": row["address"] or "",
        "speed": row["speed"],
        "updated_label": ago(row["last_seen"]),
        "live": True,
        "trail": [[p["lat"], p["lng"]] for p in points],
        "path": row.get("path") or [],
        "device": device,
    }


def bundle(user):
    device = device_row(user["device_id"])
    return {
        "token": issue_token(user),
        "user": public_user(user),
        "device": public_device(device),
        "location": public_location(device),
    }


def at_local(days_ago, hour, minute):
    day = (datetime.now(TZ) - timedelta(days=days_ago)).date()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def seed_demo():
    existing = db_exec("SELECT id FROM users WHERE device_id = %s", ("12345678",), fetch="one")
    if existing:
        return
    try:
        user = db_exec(
            """
            INSERT INTO users (name, email, phone, device_id, device_name, avatar_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                "John Doe",
                "john.doe@example.com",
                "+233 24 000 0000",
                "12345678",
                "John Doe",
                "https://randomuser.me/api/portraits/men/32.jpg",
            ),
            fetch="one",
        )
    except UniqueViolation:
        return
    db_exec(
        """
        INSERT INTO devices (
            device_id, user_id, name, battery, signal, gps_status, temperature, speed,
            sos_active, has_live_fix, lat, lng, address, last_seen
        )
        VALUES (%s, %s, %s, 85, 'Good', 'Active', 32, 5, FALSE, FALSE, 5.5600, -0.2050,
                '123 Main Street, Accra, Ghana', NOW())
        """,
        (user["device_id"], user["id"], user.get("device_name") or user["name"]),
    )
    members = [
        ("John Doe", "https://randomuser.me/api/portraits/men/32.jpg", "Online • 5 km/h", True),
        ("Sarah Doe", "https://randomuser.me/api/portraits/women/44.jpg", "Online • 2 km/h", True),
        ("James Doe", "https://randomuser.me/api/portraits/men/76.jpg", "Offline • 3 h ago", False),
        ("Mary Doe", "https://randomuser.me/api/portraits/women/65.jpg", "Offline • 5 h ago", False),
    ]
    for name, avatar, status, online in members:
        db_exec(
            """
            INSERT INTO family_members (owner_device_id, name, avatar_url, status_text, online)
            VALUES (%s, %s, %s, %s, %s)
            """,
            ("12345678", name, avatar, status, online),
        )
    zones = [
        ("Home", "123 Main Street, Accra", 5.5600, -0.2050, 200, True),
        ("Work Place", "Ring Road, Accra", 5.5715, -0.1940, 150, True),
        ("School", None, None, None, 200, False),
    ]
    for name, address, lat, lng, radius, configured in zones:
        db_exec(
            """
            INSERT INTO geofences (device_id, name, address, lat, lng, radius_m, configured)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            ("12345678", name, address, lat, lng, radius, configured),
        )
    history = [
        ("arrived", "Arrived at Work Place", "123 Main Street, Accra", at_local(0, 9, 52)),
        ("left", "Left Home", "123 Main Street, Accra", at_local(0, 9, 38)),
        ("sos", "SOS Alert triggered", "Near Ring Road", at_local(0, 8, 15)),
        ("arrived", "Arrived Home", "123 Main Street, Accra", at_local(1, 18, 40)),
        ("left", "Left Work Place", "123 Main Street, Accra", at_local(1, 17, 58)),
        ("arrived", "Arrived at Work Place", "123 Main Street, Accra", at_local(1, 9, 5)),
    ]
    for kind, title, place, moment in history:
        db_exec(
            "INSERT INTO events (device_id, kind, title, place, created_at) VALUES (%s, %s, %s, %s, %s)",
            ("12345678", kind, title, place, moment),
        )


def device_key_ok():
    expected = os.getenv("DEVICE_INGEST_KEY", "").strip()
    if not expected:
        return True
    provided = request.headers.get("X-Device-Key", "")
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)


def reverse_geocode(lat, lng):
    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lng}"
    req = urllib.request.Request(url, headers={"User-Agent": "GFastTrack/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read().decode())
            return payload.get("display_name")
    except Exception:
        app.logger.info("reverse geocode skipped")
        return None


def moved(old_lat, old_lng, lat, lng):
    if old_lat is None or old_lng is None:
        return True
    return abs(old_lat - lat) > 0.0004 or abs(old_lng - lng) > 0.0004


def distance_m(lat1, lng1, lat2, lng2):
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def check_geofences(device_id, lat, lng):
    zones = db_exec(
        "SELECT * FROM geofences WHERE device_id = %s AND configured = TRUE AND lat IS NOT NULL",
        (device_id,),
        fetch="all",
    )
    for zone in zones:
        inside = distance_m(lat, lng, zone["lat"], zone["lng"]) <= (zone["radius_m"] or 200)
        if inside == bool(zone["inside"]):
            continue
        db_exec("UPDATE geofences SET inside = %s WHERE id = %s", (inside, zone["id"]))
        if inside:
            kind, title = "arrived", f"Arrived at {zone['name']}"
        else:
            kind, title = "left", f"Left {zone['name']}"
        db_exec(
            "INSERT INTO events (device_id, kind, title, place) VALUES (%s, %s, %s, %s)",
            (device_id, kind, title, zone["address"] or zone["name"]),
        )


def cloudinary_ready():
    return all(os.getenv(key) for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"))


def save_photo_locally():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return fail("Choose a photo first.", 400)
    ext = Path(photo.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return fail("Use a JPG, PNG, WEBP, or GIF photo.", 400)
    folder = Path(__file__).resolve().parent / "uploads"
    folder.mkdir(exist_ok=True)
    filename = f"user_{request.user['id']}{ext}"
    photo.save(folder / filename)
    url = request.host_url.rstrip("/") + "/uploads/" + filename
    user = request.user
    user["avatar_url"] = url
    for member in local_store().family:
        if (
            member["owner_device_id"] == user["device_id"]
            and member["device_id"] == user["device_id"]
            and (user.get("device_name") or user["name"]) == user["name"]
        ):
            member["avatar_url"] = url
    return jsonify(avatar_url=url, user=public_user(user))


class LocalStore:
    """In-memory stand-in used only when DATABASE_URL is missing, so the app can be tried locally."""

    def __init__(self):
        self.users_by_id = {}
        self.users_by_device = {}
        self.users_by_username = {}
        self.devices = {}
        self.family = []
        self.geofences = []
        self.events = []
        self.commands = []
        self.locations = []
        self._seq = 1

    def next_id(self):
        self._seq += 1
        return self._seq

    def ensure_user(
        self, first_name, surname, username, password, device_id, device_name,
        email="", phone="", birth_date="", address="", country="", speed=0, avatar="", extras=True,
    ):
        existing = self.users_by_username.get(username.strip().lower()) or self.users_by_device.get(device_id)
        if existing:
            return existing
        device_name = (device_name or first_name).strip()
        full = " ".join(part for part in (first_name.strip(), (surname or "").strip()) if part)
        user = {
            "id": self.next_id(),
            "name": full,
            "first_name": first_name.strip(),
            "surname": (surname or "").strip(),
            "username": username.strip(),
            "password_hash": password if password and "$" in password else hash_password(password),
            "birth_date": birth_date or "",
            "address": address or "",
            "country": country or "",
            "device_name": device_name,
            "email": email or "",
            "phone": phone or "",
            "device_id": device_id,
            "avatar_url": avatar or "https://randomuser.me/api/portraits/men/32.jpg",
        }
        self.users_by_id[user["id"]] = user
        self.users_by_device[device_id] = user
        self.users_by_username[username.strip().lower()] = user
        prior = self.devices.get(device_id)
        if prior and not prior.get("user_id"):
            prior["user_id"] = user["id"]
            prior["name"] = device_name
            if prior.get("lat") is None:
                prior["lat"] = 5.5600
                prior["lng"] = -0.2050
                prior["address"] = address or "123 Main Street, Accra, Ghana"
                prior["last_seen"] = datetime.now(TZ)
        else:
            self.devices[device_id] = {
                "device_id": device_id,
                "user_id": user["id"],
                "name": device_name,
                "battery": 85,
                "signal": "Good",
                "gps_status": "Active",
                "temperature": 32,
                "speed": speed,
                "sos_active": False,
                "has_live_fix": False,
                "lat": 5.5600,
                "lng": -0.2050,
                "address": "123 Main Street, Accra, Ghana",
                "last_seen": datetime.now(TZ),
            }
        self._seed_screens(device_id, device_name, user["avatar_url"], extras=extras)
        return user

    def add_owned_device(self, user, device_name, device_id, lat, lng, address, speed=3):
        existing = self.devices.get(device_id)
        if existing and existing.get("user_id") not in (None, user["id"]):
            return False
        if existing is None:
            self.place_device(device_id, lat, lng, address, speed)
        device = self.devices[device_id]
        device["user_id"] = user["id"]
        device["name"] = device_name
        self.family.append({
            "id": self.next_id(),
            "owner_device_id": user["device_id"],
            "name": device_name,
            "device_id": device_id,
            "avatar_url": "",
            "status_text": f"Online • {(address or 'Accra').split(',')[0]}",
            "online": True,
        })
        return True

    def rename(self, user, name):
        if user["name"] == name:
            return
        user["name"] = name

    def set_device_name(self, user, device_name):
        device_name = (device_name or user["name"]).strip()
        user["device_name"] = device_name
        device = self.devices.get(user["device_id"])
        if device:
            device["name"] = device_name
        for member in self.family:
            if member["owner_device_id"] == user["device_id"] and member["device_id"] == user["device_id"]:
                member["name"] = device_name
                if device_name.casefold() != user["name"].casefold():
                    member["avatar_url"] = ""
                break

    def place_device(self, device_id, lat, lng, address, speed):
        path = [[round(lat + i * 0.0018, 5), round(lng + i * 0.0014, 5)] for i in range(6)]
        self.devices[device_id] = {
            "device_id": device_id,
            "user_id": None,
            "battery": 80,
            "signal": "Good",
            "gps_status": "Active",
            "temperature": 31,
            "speed": speed,
            "sos_active": False,
            "has_live_fix": False,
            "lat": path[0][0],
            "lng": path[0][1],
            "address": address,
            "last_seen": datetime.now(TZ),
            "path": path,
        }

    def _seed_screens(self, device_id, name, avatar, extras=True):
        others = [
            ("Sarah Doe", "https://randomuser.me/api/portraits/women/44.jpg", "ST-SARAH", 5.6037, -0.1870, "Oxford Street, Osu", 2),
            ("James Doe", "https://randomuser.me/api/portraits/men/76.jpg", "ST-JAMES", 5.5502, -0.2360, "Kaneshie, Accra", 4),
            ("Mary Doe", "https://randomuser.me/api/portraits/women/65.jpg", "ST-MARY", 5.6140, -0.2056, "Labone, Accra", 3),
        ]
        self.family.append({
            "id": self.next_id(),
            "owner_device_id": device_id,
            "name": name,
            "device_id": device_id,
            "avatar_url": avatar,
            "status_text": "Online • 5 km/h",
            "online": True,
        })
        if extras:
            for member_name, photo, tracker_id, lat, lng, address, speed in others:
                if tracker_id not in self.devices:
                    self.place_device(tracker_id, lat, lng, address, speed)
                self.family.append({
                    "id": self.next_id(),
                    "owner_device_id": device_id,
                    "name": member_name,
                    "device_id": tracker_id,
                    "avatar_url": photo,
                    "status_text": f"Online • {address.split(',')[0]}",
                    "online": True,
                })
        zones = [
            ("Home", "123 Main Street, Accra", 5.5600, -0.2050, 200, True),
            ("Work Place", "Ring Road, Accra", 5.5715, -0.1940, 150, True),
            ("School", None, None, None, 200, False),
        ]
        for zone_name, address, lat, lng, radius, configured in zones:
            self.geofences.append({
                "id": self.next_id(),
                "device_id": device_id,
                "name": zone_name,
                "address": address,
                "lat": lat,
                "lng": lng,
                "radius_m": radius,
                "configured": configured,
                "inside": False,
            })
        history = [
            ("arrived", "Arrived at Work Place", "123 Main Street, Accra", at_local(0, 9, 52)),
            ("left", "Left Home", "123 Main Street, Accra", at_local(0, 9, 38)),
            ("sos", "SOS Alert triggered", "Near Ring Road", at_local(0, 8, 15)),
            ("arrived", "Arrived Home", "123 Main Street, Accra", at_local(1, 18, 40)),
            ("left", "Left Work Place", "123 Main Street, Accra", at_local(1, 17, 58)),
            ("arrived", "Arrived at Work Place", "123 Main Street, Accra", at_local(1, 9, 5)),
        ]
        for kind, title, place, moment in history:
            self.events.append({
                "id": self.next_id(),
                "device_id": device_id,
                "kind": kind,
                "title": title,
                "place": place,
                "created_at": moment,
            })

    def disconnect(self, user, device_id):
        owned = [row for row in self.devices.values() if row.get("user_id") == user["id"]]
        if len(owned) <= 1:
            return None
        if not any(row["device_id"] == device_id for row in owned):
            return False
        old_id = user["device_id"]
        target = self.devices.get(device_id)
        if target:
            target["user_id"] = None
        if device_id == old_id:
            nxt = next(row for row in owned if row["device_id"] != device_id)
            self.users_by_device.pop(old_id, None)
            user["device_id"] = nxt["device_id"]
            user["device_name"] = nxt.get("name") or nxt["device_id"]
            self.users_by_device[user["device_id"]] = user
        return user

    def _drop_device(self, owner_id, device_id):
        self.family = [
            member for member in self.family
            if not (member["owner_device_id"] == owner_id and member.get("device_id") == device_id)
        ]
        self.devices.pop(device_id, None)
        self.locations = [point for point in self.locations if point["device_id"] != device_id]
        self.commands = [command for command in self.commands if command["device_id"] != device_id]

    def provision(self, device_id, name):
        if device_id in self.devices or device_id in self.users_by_device:
            return None
        self.devices[device_id] = {
            "device_id": device_id,
            "user_id": None,
            "name": name or device_id,
            "battery": None,
            "signal": "",
            "gps_status": "Waiting",
            "temperature": None,
            "speed": 0,
            "sos_active": False,
            "has_live_fix": False,
            "lat": None,
            "lng": None,
            "address": "",
            "last_seen": None,
        }
        return self.devices[device_id]


_local_store = None


def local_store():
    global _local_store
    if _local_store is None:
        _local_store = LocalStore()
    return _local_store


def local_signin(username, password):
    user = local_store().users_by_username.get((username or "").strip().lower())
    if not user or not check_password(password or "", user.get("password_hash")):
        return fail("That username or password is not right.", 401)
    return jsonify(bundle(user))


def claimable_device(device_id):
    row = device_row(device_id)
    if not row:
        return None, fail("This tracker is not registered. Check the Device ID.", 404)
    if row.get("user_id"):
        return None, fail("This Device ID is already linked to an account.", 409)
    return row, None


def local_register(profile, devices):
    store = local_store()
    if profile["username"].lower() in store.users_by_username:
        return fail("That username is already taken.", 409)
    seen = set()
    for item in devices:
        if item["device_id"] in seen:
            return fail("Each tracker needs its own Device ID.", 400)
        seen.add(item["device_id"])
        row, error = claimable_device(item["device_id"])
        if error:
            return error
    first = devices[0]
    full = f"{profile['first_name']} {profile['surname']}".strip()
    user = {
        "id": store.next_id(),
        "name": full,
        "first_name": profile["first_name"],
        "surname": profile["surname"],
        "username": profile["username"],
        "password_hash": hash_password(profile["password"]),
        "birth_date": profile["birth_date"],
        "address": profile["address"],
        "country": profile["country"],
        "device_name": first["name"],
        "email": "",
        "phone": "",
        "device_id": first["device_id"],
        "avatar_url": "",
    }
    store.users_by_id[user["id"]] = user
    store.users_by_device[first["device_id"]] = user
    store.users_by_username[profile["username"].lower()] = user
    for item in devices:
        row = store.devices[item["device_id"]]
        row["user_id"] = user["id"]
        row["name"] = item["name"]
    return jsonify(bundle(user))


def profile_from_body(data):
    first = (data.get("first_name") or data.get("name") or "").strip()
    surname = (data.get("surname") or "").strip()
    username = clean_username(data.get("username"))
    password = data.get("password") or ""
    birth_date = clean_birth_date(data.get("birth_date"))
    address = (data.get("address") or "").strip()
    country = (data.get("country") or "").strip()
    if not first or len(first) > 80 or not surname or len(surname) > 80:
        return None, fail("Enter your first name and surname.", 400)
    if not username:
        return None, fail("Choose a username with letters or numbers, 3 to 32 characters.", 400)
    if len(password) < 4 or len(password) > 80:
        return None, fail("Choose a password of at least 4 characters.", 400)
    if not birth_date:
        return None, fail("Select your date of birth.", 400)
    if not address or len(address) > 160:
        return None, fail("Enter your address.", 400)
    if country not in COUNTRIES:
        return None, fail("Select your country.", 400)
    return {
        "first_name": first,
        "surname": surname,
        "username": username,
        "password": password,
        "birth_date": birth_date,
        "address": address,
        "country": country,
    }, None


@app.get("/api/health")
def health():
    database = False
    if database_url():
        try:
            ensure_db()
            db_exec("SELECT 1 AS ok", fetch="one")
            database = True
        except Exception:
            app.logger.exception("health check could not reach Neon")
    return jsonify(ok=True, database=database, cloudinary=cloudinary_ready())


@app.get("/api/devices/check/<device_id>")
@require_db
def check_device(device_id):
    device_id = clean_device_id(device_id)
    if not device_id:
        return fail("This tracker is not registered.", 404)
    _row, error = claimable_device(device_id)
    if error:
        return error
    return jsonify(ok=True, device_id=device_id)


def tracker_card(row):
    view = public_device(row)
    if not row.get("has_live_fix"):
        status = "Waiting for first report"
    elif view["online"]:
        status = f"Online · {round(view['speed'])} km/h" if view["speed"] is not None else "Online"
    else:
        status = f"Offline · {view['updated_label']}"
    if view["sos_active"]:
        status = "SOS · " + status
    return {
        "name": view["name"] or row["device_id"],
        "device_id": row["device_id"],
        "avatar_url": "",
        "status_text": status,
        "online": view["online"],
        "address": view["address"],
        "lat": view["lat"],
        "lng": view["lng"],
        "battery": view["battery"],
        "signal": view["signal"],
        "temperature": view["temperature"],
        "speed": view["speed"],
        "sos_active": view["sos_active"],
        "updated_label": view["updated_label"],
    }


@app.get("/api/trackers")
@require_db
@login_required
def trackers():
    return jsonify(members=[tracker_card(row) for row in account_devices(request.user)])


@app.post("/api/trackers")
@require_db
@login_required
def add_tracker():
    data = body_json()
    name = (data.get("name") or "").strip()
    device_id = clean_device_id(data.get("device_id"))
    if not name or len(name) > 80:
        return fail("Enter a name for this tracker.", 400)
    if not device_id:
        return fail("This tracker is not registered.", 404)
    row, error = claimable_device(device_id)
    if error:
        return error
    if local_mode():
        row["user_id"] = request.user["id"]
        row["name"] = name
        return jsonify(ok=True)
    db_exec(
        "UPDATE devices SET user_id = %s, name = %s WHERE device_id = %s AND user_id IS NULL",
        (request.user["id"], name, device_id),
    )
    return jsonify(ok=True)


@app.post("/api/auth/register")
@require_db
def register():
    data = body_json()
    profile, error = profile_from_body(data)
    if error:
        return error
    devices = read_devices(data)
    if not devices:
        return fail("Add at least one device, each with its own name and Device ID.", 400)
    if local_mode():
        return local_register(profile, devices)
    taken = db_exec(
        "SELECT username FROM users WHERE lower(username) = lower(%s)",
        (profile["username"],),
        fetch="one",
    )
    if taken:
        return fail("That username is already taken.", 409)
    seen = set()
    for item in devices:
        if item["device_id"] in seen:
            return fail("Each tracker needs its own Device ID.", 400)
        seen.add(item["device_id"])
        _row, error = claimable_device(item["device_id"])
        if error:
            return error
    full = f"{profile['first_name']} {profile['surname']}".strip()
    first = devices[0]
    try:
        user = db_exec(
            """
            INSERT INTO users (
                name, first_name, surname, username, password_hash, birth_date, address, country,
                device_name, device_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                full, profile["first_name"], profile["surname"], profile["username"],
                hash_password(profile["password"]), profile["birth_date"], profile["address"],
                profile["country"], first["name"], first["device_id"],
            ),
            fetch="one",
        )
    except UniqueViolation:
        return fail("That username or Device ID is already registered.", 409)
    for item in devices:
        db_exec(
            "UPDATE devices SET user_id = %s, name = %s WHERE device_id = %s AND user_id IS NULL",
            (user["id"], item["name"], item["device_id"]),
        )
    return jsonify(bundle(user))


@app.post("/api/auth/signin")
@require_db
def signin():
    data = body_json()
    username = clean_username(data.get("username"))
    password = data.get("password") or ""
    if not username or not password:
        return fail("Enter your username and password.", 400)
    if local_mode():
        return local_signin(username, password)
    user = db_exec(
        "SELECT * FROM users WHERE lower(username) = lower(%s)",
        (username,),
        fetch="one",
    )
    if not user or not check_password(password, user.get("password_hash")):
        return fail("That username or password is not right.", 401)
    return jsonify(bundle(user))


@app.get("/api/me")
@require_db
@login_required
def me():
    user = request.user
    device = device_row(user["device_id"])
    return jsonify(user=public_user(user), device=public_device(device), location=public_location(device))


@app.patch("/api/account")
@require_db
@login_required
def update_account():
    data = body_json()
    first = (data.get("first_name") or data.get("name") or "").strip()
    surname = (data.get("surname") or "").strip()
    birth_date = clean_birth_date(data.get("birth_date"))
    address = (data.get("address") or "").strip()
    country = (data.get("country") or "").strip()
    email = (data.get("email") or "").strip() or None
    phone = (data.get("phone") or "").strip() or None
    if not first or len(first) > 80:
        return fail("Enter your first name.", 400)
    if surname and len(surname) > 80:
        return fail("Enter a shorter surname.", 400)
    if not birth_date:
        return fail("Select your date of birth.", 400)
    if country not in COUNTRIES:
        return fail("Select your country.", 400)
    if email and ("@" not in email or len(email) > 120):
        return fail("Enter a valid email.", 400)
    if phone and len(phone) > 30:
        return fail("Enter a shorter phone number.", 400)
    full = " ".join(part for part in (first, surname) if part)
    if local_mode():
        user = request.user
        user["first_name"] = first
        user["surname"] = surname
        user["name"] = full
        user["birth_date"] = birth_date
        user["address"] = address
        user["country"] = country
        user["email"] = email or ""
        user["phone"] = phone or ""
        return jsonify(user=public_user(user))
    try:
        user = db_exec(
            """
            UPDATE users
            SET name = %s, first_name = %s, surname = %s, birth_date = %s, address = %s,
                country = %s, email = %s, phone = %s
            WHERE id = %s
            RETURNING *
            """,
            (full, first, surname, birth_date, address, country, email, phone, request.user["id"]),
            fetch="one",
        )
    except UniqueViolation:
        return fail("That email is already in use.", 409)
    return jsonify(user=public_user(user))


@app.post("/api/account/photo")
@require_db
@login_required
def upload_photo():
    if local_mode() and not cloudinary_ready():
        return save_photo_locally()
    if not cloudinary_ready():
        return fail("Cloudinary is not configured yet. Add the three Cloudinary keys on Render.", 503)
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return fail("Choose a photo first.", 400)
    ext = Path(photo.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return fail("Use a JPG, PNG, WEBP, or GIF photo.", 400)
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    try:
        uploaded = cloudinary.uploader.upload(
            photo,
            folder="safetrack/avatars",
            public_id=f"user_{request.user['id']}",
            overwrite=True,
            resource_type="image",
            invalidate=True,
        )
    except Exception:
        app.logger.exception("Cloudinary upload failed")
        return fail("The photo could not be saved to Cloudinary.", 502)
    url = uploaded.get("secure_url")
    if not url:
        return fail("Cloudinary did not return a photo URL.", 502)
    user = db_exec(
        "UPDATE users SET avatar_url = %s WHERE id = %s RETURNING *",
        (url, request.user["id"]),
        fetch="one",
    )
    db_exec(
        """
        UPDATE family_members SET avatar_url = %s
        WHERE owner_device_id = %s AND device_id = %s
          AND COALESCE(name, '') = %s
        """,
        (url, user["device_id"], user["device_id"], user["name"]),
    )
    return jsonify(avatar_url=url, user=public_user(user))


@app.get("/api/location/<device_id>")
@require_db
@login_required
def location(device_id):
    device_id = clean_device_id(device_id)
    if not device_id:
        return fail("Unknown device.", 404)
    if device_id != request.user["device_id"]:
        if local_mode():
            linked = next(
                (
                    member for member in local_store().family
                    if member["owner_device_id"] == request.user["device_id"] and member["device_id"] == device_id
                ),
                None,
            )
        else:
            linked = db_exec(
                "SELECT 1 AS ok FROM family_members WHERE owner_device_id = %s AND device_id = %s",
                (request.user["device_id"], device_id),
                fetch="one",
            )
        if not linked:
            return fail("That device is not on your account.", 403)
    row = device_row(device_id)
    if not row:
        return fail("That device is not registered yet.", 404)
    payload = public_location(row) or {}
    return jsonify(payload)


def account_devices(user):
    if local_mode():
        rows = [
            row for row in local_store().devices.values()
            if row.get("user_id") == user["id"] or row["device_id"] == user["device_id"]
        ]
        rows.sort(key=lambda row: (row["device_id"] != user["device_id"], row["device_id"]))
        return rows
    return db_exec(
        """
        SELECT * FROM devices
        WHERE user_id = %s OR device_id = %s
        ORDER BY CASE WHEN device_id = %s THEN 0 ELSE 1 END, device_id
        """,
        (user["id"], user["device_id"], user["device_id"]),
        fetch="all",
    )


def device_on_account(user, device_id):
    device_id = clean_device_id(device_id)
    if not device_id:
        return None
    linked = device_id == user["device_id"] or any(
        row["device_id"] == device_id for row in account_devices(user)
    )
    if not linked:
        return None
    return device_row(device_id)


def wearer_name(user, device_id):
    for row in account_devices(user):
        if row["device_id"] == device_id:
            return row.get("name") or user.get("device_name") or ""
    if device_id == user["device_id"]:
        return user.get("device_name") or user.get("name") or ""
    return ""


@app.get("/api/device")
@require_db
@login_required
def device_status():
    row = device_row(request.user["device_id"])
    return jsonify(device=public_device(row), location=public_location(row))


@app.get("/api/device/<device_id>")
@require_db
@login_required
def device_detail(device_id):
    row = device_on_account(request.user, device_id)
    if not row:
        return fail("That device is not on your account.", 404)
    return jsonify(
        name=wearer_name(request.user, row["device_id"]),
        device=public_device(row),
        location=public_location(row),
    )


@app.post("/api/device/beep")
@require_db
@login_required
def beep():
    requested = clean_device_id((body_json().get("device_id") or request.user["device_id"]))
    row = device_on_account(request.user, requested)
    if not row:
        return fail("That device is not on your account.", 404)
    if local_mode():
        local_store().commands.append({
            "id": local_store().next_id(),
            "device_id": row["device_id"],
            "command": "beep",
            "consumed": False,
        })
        return jsonify(ok=True)
    db_exec(
        "INSERT INTO device_commands (device_id, command) VALUES (%s, 'beep')",
        (row["device_id"],),
    )
    return jsonify(ok=True)


@app.post("/api/device/disconnect")
@require_db
@login_required
def disconnect_device():
    requested = clean_device_id(body_json().get("device_id") or "")
    if not requested or not device_on_account(request.user, requested):
        return fail("That device is not on your account.", 404)
    owned = account_devices(request.user)
    if len(owned) <= 1:
        return fail("Keep at least one device on the account.", 400)
    if local_mode():
        previous = request.user["device_id"]
        user = local_store().disconnect(request.user, requested)
        if user is None:
            return fail("Keep at least one device on the account.", 400)
        if user is False:
            return fail("That device is not on your account.", 404)
        if requested == previous:
            return jsonify(bundle(user))
        return jsonify(ok=True)
    return disconnect_postgres(request.user, requested)


def disconnect_postgres(user, device_id):
    owned = account_devices(user)
    nxt = next((row for row in owned if row["device_id"] != device_id), None)
    if nxt is None:
        return fail("Keep at least one device on the account.", 400)
    old_id = user["device_id"]
    if device_id != old_id:
        db_exec("UPDATE devices SET user_id = NULL WHERE device_id = %s", (device_id,))
        return jsonify(ok=True)
    new_id = nxt["device_id"]
    db_exec(
        "UPDATE users SET device_id = %s, device_name = %s WHERE id = %s",
        (new_id, nxt.get("name") or new_id, user["id"]),
    )
    db_exec("UPDATE devices SET user_id = NULL WHERE device_id = %s", (old_id,))
    fresh = db_exec("SELECT * FROM users WHERE id = %s", (user["id"],), fetch="one")
    return jsonify(bundle(fresh))


@app.post("/api/sos/dismiss")
@require_db
@login_required
def dismiss_sos():
    if local_mode():
        row = device_row(request.user["device_id"])
        if row:
            row["sos_active"] = False
        return jsonify(ok=True)
    db_exec(
        "UPDATE devices SET sos_active = FALSE WHERE device_id = %s",
        (request.user["device_id"],),
    )
    return jsonify(ok=True)


@app.get("/api/family")
@require_db
@login_required
def family():
    if local_mode():
        rows = [m for m in local_store().family if m["owner_device_id"] == request.user["device_id"]]
    else:
        rows = db_exec(
        """
        SELECT * FROM family_members
        WHERE owner_device_id = %s
        ORDER BY id
        """,
        (request.user["device_id"],),
        fetch="all",
    )
    members = []
    for row in rows:
        status = row["status_text"] or "Offline"
        online = bool(row["online"])
        if row["device_id"]:
            device = device_row(row["device_id"])
            if device:
                view = public_device(device)
                online = view["online"]
                speed = view["speed"] or 0
                place = (device.get("address") or "").split(",")[0]
                if online and place and row["device_id"] != request.user["device_id"]:
                    status = f"Online • {place}"
                elif online and speed > 0.5:
                    status = f"Online • {round(speed)} km/h"
                elif online:
                    status = "Online"
                else:
                    status = f"Offline • {view['updated_label']}"
        place = ""
        lat = lng = None
        battery = None
        if row["device_id"]:
            device = device_row(row["device_id"])
            if device:
                place = device.get("address") or ""
                lat = device.get("lat")
                lng = device.get("lng")
                battery = device.get("battery")
        members.append({
            "id": row["id"],
            "name": row["name"],
            "device_id": row["device_id"] or "",
            "avatar_url": row["avatar_url"] or "",
            "status_text": status,
            "online": online,
            "address": place,
            "lat": lat,
            "lng": lng,
            "battery": battery,
        })
    return jsonify(members=members)


@app.post("/api/family")
@require_db
@login_required
def add_family():
    data = body_json()
    name = (data.get("name") or "").strip()
    device_id = (data.get("device_id") or "").strip()
    if not name or len(name) > 80:
        return fail("Enter the family member's name.", 400)
    if not device_id or not clean_device_id(device_id):
        return fail("Each family member needs their own Device ID.", 400)
    if local_mode():
        store = local_store()
        if device_id and device_id not in store.devices:
            store.place_device(device_id, 5.5800, -0.2100, "Accra, Ghana", 3)
        row = {
            "id": store.next_id(),
            "owner_device_id": request.user["device_id"],
            "name": name,
            "device_id": device_id or None,
            "avatar_url": "",
            "status_text": "Online • Accra",
            "online": bool(device_id),
        }
        store.family.append(row)
        return jsonify(id=row["id"], name=row["name"])
    row = db_exec(
        """
        INSERT INTO family_members (owner_device_id, name, device_id, status_text, online)
        VALUES (%s, %s, %s, 'Offline', FALSE)
        RETURNING *
        """,
        (request.user["device_id"], name, device_id or None),
        fetch="one",
    )
    return jsonify(id=row["id"], name=row["name"])


@app.get("/api/geofences")
@require_db
@login_required
def geofences():
    if local_mode():
        rows = [z for z in local_store().geofences if z["device_id"] == request.user["device_id"]]
    else:
        rows = db_exec(
        "SELECT * FROM geofences WHERE device_id = %s ORDER BY id",
        (request.user["device_id"],),
        fetch="all",
    )
    zones = []
    for row in rows:
        if row["configured"] and row["address"]:
            detail = f"{row['address']} · {row['radius_m']}m radius"
        else:
            detail = "Not yet configured"
        zones.append({
            "id": row["id"],
            "name": row["name"],
            "address": row["address"] or "",
            "lat": row["lat"],
            "lng": row["lng"],
            "radius_m": row["radius_m"],
            "configured": bool(row["configured"]),
            "detail": detail,
        })
    return jsonify(zones=zones)


@app.post("/api/geofences")
@require_db
@login_required
def add_geofence():
    data = body_json()
    name = (data.get("name") or "").strip()
    address = (data.get("address") or "").strip() or None
    radius = as_float(data.get("radius_m")) or 200
    lat = as_float(data.get("lat"))
    lng = as_float(data.get("lng"))
    if not name or len(name) > 80:
        return fail("Enter a name for the safe zone.", 400)
    radius = max(50, min(5000, int(radius)))
    configured = lat is not None and lng is not None
    if local_mode():
        row = {
            "id": local_store().next_id(),
            "device_id": request.user["device_id"],
            "name": name,
            "address": address,
            "lat": lat,
            "lng": lng,
            "radius_m": radius,
            "configured": configured,
            "inside": False,
        }
        local_store().geofences.append(row)
        return jsonify(id=row["id"])
    row = db_exec(
        """
        INSERT INTO geofences (device_id, name, address, lat, lng, radius_m, configured)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (request.user["device_id"], name, address, lat, lng, radius, configured),
        fetch="one",
    )
    return jsonify(id=row["id"])


def history_groups(rows):
    groups = []
    index = {}
    for row in rows:
        moment = row["recorded_at"]
        label = day_label(moment)
        if label not in index:
            index[label] = {"label": label, "items": []}
            groups.append(index[label])
        place = (row.get("address") or "").strip()
        title = place or f"{row['lat']:.5f}, {row['lng']:.5f}"
        detail = clock(moment)
        if row.get("speed") is not None:
            detail = f"{detail} · {round(row['speed'])} km/h"
        index[label]["items"].append({
            "kind": "arrived",
            "title": title,
            "detail": detail,
            "lat": row["lat"],
            "lng": row["lng"],
        })
    return groups


@app.get("/api/history")
@require_db
@login_required
def history():
    device_id = request.user["device_id"]
    if local_mode():
        rows = [point for point in local_store().locations if point["device_id"] == device_id]
        rows.sort(key=lambda item: item["recorded_at"], reverse=True)
        rows = rows[:80]
    else:
        rows = db_exec(
            """
            SELECT lat, lng, speed, address, recorded_at
            FROM locations
            WHERE device_id = %s
            ORDER BY recorded_at DESC
            LIMIT 80
            """,
            (device_id,),
            fetch="all",
        )
    return jsonify(groups=history_groups(rows))


@app.post("/api/ingest/<device_id>")
@require_db
def ingest(device_id):
    device_id = clean_device_id(device_id)
    if not device_id:
        return fail("Unknown device.", 404)
    if not device_key_ok():
        return fail("Invalid device key.", 401)
    row = device_row(device_id)
    if not row:
        return fail("This tracker is not registered.", 404)
    data = body_json()
    lat = as_float(data.get("lat"))
    lng = as_float(data.get("lng"))
    if lat is None or lng is None or not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return fail("Missing or invalid lat or lng.", 400)
    if "speed" in data and data.get("speed") not in (None, ""):
        speed = as_float(data.get("speed"))
        if speed is None:
            return fail("Speed must be a number.", 400)
    else:
        speed = row["speed"]
    if "battery" in data and data.get("battery") not in (None, ""):
        try:
            battery = int(data.get("battery"))
        except (TypeError, ValueError):
            return fail("Battery must be a number from 0 to 100.", 400)
        if battery < 0 or battery > 100:
            return fail("Battery must be a number from 0 to 100.", 400)
    else:
        battery = row["battery"]
    if "temperature" in data and data.get("temperature") not in (None, ""):
        temperature = as_float(data.get("temperature"))
        if temperature is None:
            return fail("Temperature must be a number.", 400)
    else:
        temperature = row["temperature"]
    if "signal" in data and data.get("signal") not in (None, ""):
        signal = str(data.get("signal")).strip()[:40]
    else:
        signal = row["signal"] or ""
    if "sos" in data and data.get("sos") is not None:
        sos = as_bool(data.get("sos"))
        if sos is None:
            return fail("sos must be true or false.", 400)
    else:
        sos = bool(row["sos_active"])
    address = (data.get("address") or "").strip()
    if not address and moved(row["lat"], row["lng"], lat, lng):
        address = reverse_geocode(lat, lng) or row["address"]
    if not address:
        address = row["address"]
    if local_mode():
        row["lat"] = lat
        row["lng"] = lng
        row["speed"] = speed
        row["battery"] = battery
        row["temperature"] = temperature
        row["signal"] = signal
        row["gps_status"] = "Active"
        row["sos_active"] = sos
        row["has_live_fix"] = True
        row["address"] = address
        row["last_seen"] = datetime.now(TZ)
        local_store().locations.append({
            "device_id": device_id,
            "lat": lat,
            "lng": lng,
            "speed": speed,
            "address": address,
            "recorded_at": datetime.now(TZ),
        })
        if sos:
            local_store().events.append({
                "id": local_store().next_id(),
                "device_id": device_id,
                "kind": "sos",
                "title": "SOS Alert triggered",
                "place": address,
                "created_at": datetime.now(TZ),
            })
        return jsonify(ok=True)
    db_exec(
        """
        UPDATE devices SET
            lat = %s, lng = %s, speed = %s, battery = %s, temperature = %s,
            signal = %s, gps_status = 'Active', sos_active = %s, has_live_fix = TRUE,
            address = %s, last_seen = NOW()
        WHERE device_id = %s
        """,
        (lat, lng, speed, battery, temperature, signal, sos, address, device_id),
    )
    last = db_exec(
        "SELECT lat, lng, recorded_at FROM locations WHERE device_id = %s ORDER BY recorded_at DESC LIMIT 1",
        (device_id,),
        fetch="one",
    )
    should_store = last is None or moved(last["lat"], last["lng"], lat, lng)
    if last and isinstance(last["recorded_at"], datetime):
        moment = last["recorded_at"]
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=TZ)
        if (datetime.now(TZ) - moment.astimezone(TZ)).total_seconds() > 30:
            should_store = True
    if should_store:
        db_exec(
            "INSERT INTO locations (device_id, lat, lng, speed, address) VALUES (%s, %s, %s, %s, %s)",
            (device_id, lat, lng, speed, address),
        )
        check_geofences(device_id, lat, lng)
    if sos and not row["sos_active"]:
        db_exec(
            "INSERT INTO events (device_id, kind, title, place) VALUES (%s, 'sos', 'SOS Alert triggered', %s)",
            (device_id, address),
        )
    return jsonify(ok=True)


@app.get("/api/ingest/<device_id>/commands")
@require_db
def ingest_commands(device_id):
    device_id = clean_device_id(device_id)
    if not device_id:
        return fail("This tracker is not registered.", 404)
    if not device_key_ok():
        return fail("Invalid device key.", 401)
    if not device_row(device_id):
        return fail("This tracker is not registered.", 404)
    if local_mode():
        pending = [item for item in local_store().commands if item["device_id"] == device_id and not item["consumed"]]
        for item in pending:
            item["consumed"] = True
        return jsonify(commands=[item["command"] for item in pending])
    rows = db_exec(
        """
        SELECT id, command FROM device_commands
        WHERE device_id = %s AND consumed = FALSE
        ORDER BY id
        """,
        (device_id,),
        fetch="all",
    )
    if rows:
        db_exec(
            "UPDATE device_commands SET consumed = TRUE WHERE device_id = %s AND consumed = FALSE",
            (device_id,),
        )
    return jsonify(commands=[row["command"] for row in rows])


@app.errorhandler(413)
def too_large(_err):
    return fail("Photo must be under 6 MB.", 413)


@app.get("/uploads/<path:name>")
def serve_upload(name):
    folder = Path(__file__).resolve().parent / "uploads"
    if not (folder / name).is_file():
        abort(404)
    return send_from_directory(folder, name)


def issue_admin_token():
    payload = json.dumps(
        {"role": "admin", "exp": int(datetime.now(TZ).timestamp()) + 14 * 24 * 3600},
        separators=(",", ":"),
    ).encode()
    import base64
    body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    sig = hmac.new(secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + sig


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        data = read_token(header[7:].strip()) if header.startswith("Bearer ") else None
        if not data or data.get("role") != "admin":
            return fail("Sign in to the admin site.", 401)
        return fn(*args, **kwargs)
    return wrapper


def same_secret(given, expected):
    given = given or ""
    expected = expected or ""
    if len(given) != len(expected):
        return False
    return hmac.compare_digest(given, expected)


def public_base():
    configured = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    return request.host_url.rstrip("/")


def device_urls(device_id):
    base = public_base()
    return {
        "ingest_url": f"{base}/api/ingest/{device_id}",
        "commands_url": f"{base}/api/ingest/{device_id}/commands",
    }


def admin_device_payload(row, owner_name="", owner_username=""):
    waiting = not row.get("last_seen") and not row.get("has_live_fix")
    if waiting:
        status = "Waiting"
    else:
        view = public_device(row) or {}
        status = "Online" if view.get("online") else "Offline"
    urls = device_urls(row["device_id"])
    return {
        "device_id": row["device_id"],
        "name": row.get("name") or "",
        "battery": row.get("battery"),
        "signal": row.get("signal") or "",
        "gps_status": row.get("gps_status") or "",
        "temperature": row.get("temperature"),
        "address": row.get("address") or "",
        "status": status,
        "updated_label": ago(row.get("last_seen")),
        "owner_name": owner_name or "",
        "owner_username": owner_username or "",
        "assigned": bool(owner_name or owner_username or row.get("user_id")),
        "ingest_url": urls["ingest_url"],
        "commands_url": urls["commands_url"],
    }


def fresh_device_id(taken):
    while True:
        device_id = "ST-" + secrets.token_hex(3).upper()
        if device_id not in taken:
            return device_id


def admin_user_payload(user, devices):
    username = user.get("username") or ""
    owned = [item for item in devices if item.get("owner_username") == username]
    birth = user.get("birth_date") or ""
    if hasattr(birth, "isoformat"):
        birth = birth.isoformat()
    return {
        "name": user.get("name") or "",
        "username": username,
        "email": user.get("email") or "",
        "phone": user.get("phone") or "",
        "country": user.get("country") or "",
        "address": user.get("address") or "",
        "birth_date": birth,
        "devices": owned,
        "device_count": len(owned),
        "connected": sum(1 for item in owned if item["status"] != "Waiting"),
        "alive": sum(1 for item in owned if item["status"] == "Online"),
    }


def local_owner(row):
    store = local_store()
    if row.get("user_id"):
        user = store.users_by_id.get(row["user_id"])
        if user:
            return user
    for member in store.family:
        if member.get("device_id") == row["device_id"]:
            user = store.users_by_device.get(member["owner_device_id"])
            if user:
                return user
    return store.users_by_device.get(row["device_id"])


@app.post("/api/admin/login")
def admin_login():
    data = body_json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    expected_user = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
    expected_pass = os.getenv("ADMIN_PASSWORD", "admin")
    if not same_secret(username, expected_user) or not same_secret(password, expected_pass):
        return fail("That admin username or password is not right.", 401)
    return jsonify(token=issue_admin_token())


@app.get("/api/admin/overview")
@require_db
@admin_required
def admin_overview():
    if local_mode():
        store = local_store()
        devices = []
        for row in store.devices.values():
            owner = local_owner(row)
            devices.append(admin_device_payload(
                row,
                owner.get("name") if owner else "",
                owner.get("username") if owner else "",
            ))
        users = [admin_user_payload(user, devices) for user in store.users_by_id.values()]
        devices.sort(key=lambda item: item["device_id"])
        users.sort(key=lambda item: item["username"])
        return jsonify(users=users, devices=devices)
    device_rows = db_exec(
        """
        SELECT DISTINCT ON (d.device_id)
            d.*,
            COALESCE(u.name, owner.name, '') AS owner_name,
            COALESCE(u.username, owner.username, '') AS owner_username
        FROM devices d
        LEFT JOIN users u ON u.id = d.user_id
        LEFT JOIN family_members f ON f.device_id = d.device_id
        LEFT JOIN users owner ON owner.device_id = f.owner_device_id
        ORDER BY d.device_id
        """,
        fetch="all",
    )
    user_rows = db_exec(
        """
        SELECT id, name, username, email, phone, country, address, birth_date, device_id, device_name
        FROM users
        ORDER BY username
        """,
        fetch="all",
    )
    devices = [
        admin_device_payload(row, row.get("owner_name") or "", row.get("owner_username") or "")
        for row in device_rows
    ]
    users = [admin_user_payload(user, devices) for user in user_rows]
    users.sort(key=lambda item: item["username"])
    return jsonify(users=users, devices=devices)


@app.post("/api/admin/devices")
@require_db
@admin_required
def admin_create_device():
    if local_mode():
        store = local_store()
        device_id = fresh_device_id(set(store.devices) | set(store.users_by_device))
        created = store.provision(device_id, device_id)
        urls = device_urls(device_id)
        return jsonify(device_id=device_id, device=admin_device_payload(created), **urls)
    taken = {
        row["device_id"]
        for row in db_exec("SELECT device_id FROM devices", fetch="all")
    }
    device_id = fresh_device_id(taken)
    db_exec(
        """
        INSERT INTO devices (
            device_id, user_id, name, battery, signal, gps_status, temperature, speed,
            sos_active, has_live_fix, lat, lng, address, last_seen
        )
        VALUES (%s, NULL, %s, NULL, '', 'Waiting', NULL, 0, FALSE, FALSE, NULL, NULL, '', NULL)
        """,
        (device_id, device_id),
    )
    row = device_row(device_id)
    urls = device_urls(device_id)
    return jsonify(device_id=device_id, device=admin_device_payload(row), **urls)


@app.get("/admin")
@app.get("/admin/")
def serve_admin():
    if not (ADMIN / "index.html").is_file():
        abort(404)
    return send_from_directory(ADMIN, "index.html")


@app.get("/admin/admin.js")
def serve_admin_js():
    if not (ADMIN / "admin.js").is_file():
        abort(404)
    return send_from_directory(ADMIN, "admin.js")


@app.get("/")
def serve_index():
    if not (FRONTEND / "index.html").is_file():
        return jsonify(ok=True, service="safetrack-api")
    return send_from_directory(FRONTEND, "index.html")


@app.get("/config.js")
def serve_config():
    if not (FRONTEND / "config.js").is_file():
        abort(404)
    return send_from_directory(FRONTEND, "config.js")


@app.get("/app.js")
def serve_app_js():
    if not (FRONTEND / "app.js").is_file():
        abort(404)
    return send_from_directory(FRONTEND, "app.js")


@app.get("/manifest.webmanifest")
def serve_manifest():
    if not (FRONTEND / "manifest.webmanifest").is_file():
        abort(404)
    response = send_from_directory(FRONTEND, "manifest.webmanifest")
    response.headers["Content-Type"] = "application/manifest+json"
    return response


@app.get("/icons/<path:name>")
def serve_icon(name):
    folder = FRONTEND / "icons"
    if not name.endswith(".png") or not (folder / name).is_file():
        abort(404)
    return send_from_directory(folder, name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
