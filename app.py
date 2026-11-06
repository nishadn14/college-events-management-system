import os, sqlite3, csv, io
from functools import wraps
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, Response, abort)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "events.db"))
CATEGORIES = ["Technical", "Cultural", "Sports", "Workshop", "Seminar", "Other"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, category TEXT NOT NULL,
  date TEXT NOT NULL, time TEXT NOT NULL, venue TEXT NOT NULL,
  description TEXT, capacity INTEGER NOT NULL DEFAULT 100);
CREATE TABLE IF NOT EXISTS registrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  name TEXT NOT NULL, email TEXT NOT NULL, roll_no TEXT NOT NULL,
  department TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_id, email));
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    d = g.pop("db", None)
    if d: d.close()

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
        con.execute("INSERT INTO events (title,category,date,time,venue,description,capacity) VALUES (?,?,?,?,?,?,?)",
            ("Hackathon 2026", "Technical", "2026-12-05", "09:00", "Main Auditorium",
             "A 24-hour coding contest. Form teams, build something useful, and pitch it to the judges.", 120))
        con.commit()
    con.close()

init_db()

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrap

def event_or_404(eid):
    e = db().execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    if not e: abort(404)
    return e

LIST_SQL = """SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS taken
              FROM events e {where} ORDER BY date, time"""

@app.route("/")
def index():
    q, cat = request.args.get("q", "").strip(), request.args.get("category", "")
    where, args = [], []
    if q:
        where.append("(title LIKE ? OR venue LIKE ?)"); args += [f"%{q}%"] * 2
    if cat:
        where.append("category=?"); args.append(cat)
    sql = LIST_SQL.format(where=("WHERE " + " AND ".join(where)) if where else "")
    return render_template("index.html", events=db().execute(sql, args).fetchall(),
                           categories=CATEGORIES, q=q, cat=cat)

@app.route("/event/<int:eid>", methods=["GET", "POST"])
def event(eid):
    e = event_or_404(eid)
    taken = db().execute("SELECT COUNT(*) FROM registrations WHERE event_id=?", (eid,)).fetchone()[0]
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in ("name", "email", "roll_no", "department")}
        if not (f["name"] and f["email"] and f["roll_no"]):
            flash("Name, email and roll number are required.", "error")
        elif taken >= e["capacity"]:
            flash("This event is full.", "error")
        else:
            try:
                db().execute("INSERT INTO registrations (event_id,name,email,roll_no,department) VALUES (?,?,?,?,?)",
                             (eid, f["name"], f["email"].lower(), f["roll_no"], f["department"]))
                db().commit()
                flash("You're registered. See you there!", "ok")
            except sqlite3.IntegrityError:
                flash("This email is already registered for this event.", "error")
        return redirect(url_for("event", eid=eid))
    return render_template("event.html", e=e, taken=taken)

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin"))
        flash("Wrong password.", "error")
    return render_template("login.html")

@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@admin_required
def admin():
    events = db().execute(LIST_SQL.format(where="")).fetchall()
    return render_template("admin.html", events=events)

def form_event():
    f = request.form
    return (f["title"].strip(), f["category"], f["date"], f["time"], f["venue"].strip(),
            f.get("description", "").strip(), int(f.get("capacity") or 100))

@app.route("/admin/event/new", methods=["GET", "POST"])
@app.route("/admin/event/<int:eid>/edit", methods=["GET", "POST"])
@admin_required
def edit_event(eid=None):
    e = event_or_404(eid) if eid else None
    if request.method == "POST":
        v = form_event()
        if eid:
            db().execute("UPDATE events SET title=?,category=?,date=?,time=?,venue=?,description=?,capacity=? WHERE id=?", v + (eid,))
        else:
            db().execute("INSERT INTO events (title,category,date,time,venue,description,capacity) VALUES (?,?,?,?,?,?,?)", v)
        db().commit()
        flash("Event saved.", "ok")
        return redirect(url_for("admin"))
    return render_template("form.html", e=e, categories=CATEGORIES)

@app.route("/admin/event/<int:eid>/delete", methods=["POST"])
@admin_required
def delete_event(eid):
    db().execute("DELETE FROM events WHERE id=?", (eid,)); db().commit()
    flash("Event deleted.", "ok")
    return redirect(url_for("admin"))

@app.route("/admin/event/<int:eid>/registrations")
@admin_required
def registrations(eid):
    e = event_or_404(eid)
    rows = db().execute("SELECT * FROM registrations WHERE event_id=? ORDER BY created", (eid,)).fetchall()
    return render_template("registrations.html", e=e, rows=rows)

@app.route("/admin/event/<int:eid>/export.csv")
@admin_required
def export(eid):
    e = event_or_404(eid)
    rows = db().execute("SELECT name,email,roll_no,department,created FROM registrations WHERE event_id=?", (eid,)).fetchall()
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["Name", "Email", "Roll no", "Department", "Registered at"])
    w.writerows([tuple(r) for r in rows])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=event-{eid}-registrations.csv"})

@app.route("/registration/<int:rid>/delete", methods=["POST"])
@admin_required
def delete_reg(rid):
    r = db().execute("SELECT event_id FROM registrations WHERE id=?", (rid,)).fetchone()
    if not r: abort(404)
    db().execute("DELETE FROM registrations WHERE id=?", (rid,)); db().commit()
    return redirect(url_for("registrations", eid=r["event_id"]))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
