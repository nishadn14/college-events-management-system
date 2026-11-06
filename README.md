# College Event Management System

Flask + SQLite. Students browse and register for events; admins manage events and export registrations as CSV.

## Run locally
    pip install -r requirements.txt
    python app.py        # http://localhost:10000

## Admin
Go to /admin/login. Default password: `admin123`. Set `ADMIN_PASSWORD` and `SECRET_KEY` env vars before deploying.

## Deploy on Render
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`  (binds 0.0.0.0:$PORT automatically)
- Env vars: `ADMIN_PASSWORD`, `SECRET_KEY`
- Note: Render's free tier has an ephemeral disk, so SQLite data resets on redeploy. Attach a disk and set `DB_PATH` to it, or switch to Render Postgres, for persistent data.
