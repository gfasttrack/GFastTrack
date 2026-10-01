# SafeTrack

The phone screens stay as designed. This repo splits them from the API so you can host each part where you planned.

| Part | Folder | Host | Stores |
| --- | --- | --- | --- |
| Screens (HTML, CSS, JavaScript) | `frontend/` | GitHub Pages | nothing |
| API | `backend/` | Render | — |
| Accounts, devices, locations, family, safe zones | Neon | Postgres | user information |
| Profile photos | Cloudinary | image files | pictures |

`SafeTrack - GPS Tracking App (6).html` is the original design file. Deploy `frontend/`, not that file.

## Run it on your computer

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Put your Neon connection string in `backend/.env` as `DATABASE_URL`. Then:

```bash
python app.py
```

Open http://127.0.0.1:5000

The demo account is already in the database the first time the API starts:

- Name: `John Doe`
- Device ID: `12345678`

Create Account uses the same name and Device ID fields. Email and phone are saved later from the Account screen. Change Photo uploads the picture to Cloudinary and stores only the link in Neon.

## GitHub Pages

The phone app is only the `frontend/` folder. The admin site stays on Render at `/admin`.

1. Push this project to GitHub.
2. In the repo, open Settings → Pages → Build and deployment, and choose **GitHub Actions**.
3. The workflow `.github/workflows/pages.yml` publishes `frontend/` on every push to `main` or `master`.
4. In `frontend/config.js`, set `window.SAFETRACK_API` to your Render URL, for example `https://safetrack-api.onrender.com`, then push again.
5. On Render, set `FRONTEND_ORIGINS` to your Pages URL, for example `https://yourname.github.io` or `https://yourname.github.io/your-repo`. Use `*` only while testing.

## Render

Create a Neon database and a Cloudinary account first. Then:

1. New Web Service from this repo.
2. Root directory: `backend`
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`
5. Environment variables from `backend/.env.example`:
   - `DATABASE_URL` — Neon connection string (`sslmode=require`)
   - `SECRET_KEY` — a long random string
   - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
   - `DEVICE_INGEST_KEY` — the same value you put on the ESP32
   - `FRONTEND_ORIGINS` — your GitHub Pages origin

Health check: `GET /api/health`

## ESP32

After the device ID exists on an account, the tracker posts:

```http
POST /api/ingest/12345678
Content-Type: application/json
X-Device-Key: YOUR_DEVICE_INGEST_KEY

{"lat": 5.56, "lng": -0.205, "speed": 5, "battery": 85, "temperature": 32, "signal": "Good", "sos": false}
```

Play Beep queues a command. The device collects it with:

```http
GET /api/ingest/12345678/commands
X-Device-Key: YOUR_DEVICE_INGEST_KEY
```

`sos: true` opens the SOS screen for anyone signed in on that device and adds a history row.
