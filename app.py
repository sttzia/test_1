import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from flask import Flask, jsonify, render_template, request, g, current_app

# Ensure only one waker thread per process
_WAKER_STARTED = threading.Event()


def _utc_now_iso() -> str:
    # timezone-aware UTC, seconds precision, RFC3339-like with Z suffix
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _connect_db(db_path: str):
    # Support shared in-memory database for tests
    if db_path.startswith("file:"):
        conn = sqlite3.connect(db_path, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def get_db() -> sqlite3.Connection:
    # Prefer request-scoped connection unless configured to persist
    db: Optional[sqlite3.Connection] = getattr(g, "_db", None)
    if db is not None:
        return db

    app = current_app
    db_path: str = app.config["DATABASE"]
    persist: bool = bool(app.config.get("PERSIST_DB_CONN", False))

    if persist:
        # Keep a single connection alive at app-level (useful for shared in-memory DB in tests)
        app_conn: Optional[sqlite3.Connection] = getattr(app, "_db_conn", None)
        if app_conn is None:
            app_conn = _connect_db(db_path)
            _ensure_schema(app_conn)
            setattr(app, "_db_conn", app_conn)
        return app_conn
    else:
        db = _connect_db(db_path)
        _ensure_schema(db)
        g._db = db
        return db


def close_db(e=None):
    db: Optional[sqlite3.Connection] = getattr(g, "_db", None)
    if db is not None:
        db.close()
        g._db = None


def create_app(test_config: Optional[dict] = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # Default DB in instance directory
    default_db = os.path.join(app.instance_path, "notes.db")
    app.config.from_mapping(
        DATABASE=default_db,
        JSON_SORT_KEYS=False,
    )

    if test_config is not None:
        app.config.update(test_config)
    else:
        # Allow environment variable override for deployment (e.g., Render)
        env_db = os.environ.get("DATABASE")
        if env_db:
            app.config["DATABASE"] = env_db

    # Config for background waker (interval and TTL in seconds)
    app.config.setdefault("ENABLE_WAKER", True)
    # Allow env overrides; default to 30 seconds for both interval and TTL
    try:
        interval_env = float(os.environ.get("WAKER_INTERVAL", "30"))
    except ValueError:
        interval_env = 30.0
    try:
        ttl_env = float(os.environ.get("WAKER_TTL", "30"))
    except ValueError:
        ttl_env = 30.0
    app.config.setdefault("WAKER_INTERVAL", interval_env)
    app.config.setdefault("WAKER_TTL", ttl_env)

    # Decide whether to persist a single DB connection (for in-memory DBs this keeps the DB alive across requests)
    db_cfg = str(app.config.get("DATABASE", ""))
    if any(
        s in db_cfg
        for s in (
            ":memory:",
            "mode=memory",
        )
    ):
        app.config.setdefault("PERSIST_DB_CONN", True)
    else:
        app.config.setdefault("PERSIST_DB_CONN", False)

    # Ensure instance dir exists for default DB
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    @app.teardown_appcontext
    def _teardown(exception):
        close_db()

    # Web UI
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.get("/api/notes")
    def list_notes():
        db = get_db()
        rows = db.execute(
            "SELECT id, title, content, updated_at FROM notes ORDER BY updated_at DESC"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/notes/<int:note_id>")
    def get_note(note_id: int):
        db = get_db()
        row = db.execute(
            "SELECT id, title, content, updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(row))

    @app.post("/api/notes")
    def create_note():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "Untitled").strip()
        content = data.get("content") or ""
        ts = _utc_now_iso()
        db = get_db()
        cur = db.execute(
            "INSERT INTO notes (title, content, updated_at) VALUES (?, ?, ?)",
            (title, content, ts),
        )
        db.commit()
        note_id = cur.lastrowid
        row = db.execute(
            "SELECT id, title, content, updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        return jsonify(dict(row)), 201

    @app.put("/api/notes/<int:note_id>")
    def update_note(note_id: int):
        data = request.get_json(silent=True) or {}
        title = data.get("title")
        content = data.get("content")
        if title is None and content is None:
            return jsonify({"error": "Nothing to update"}), 400
        db = get_db()
        # Ensure exists
        exists = db.execute("SELECT 1 FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not exists:
            return jsonify({"error": "Not found"}), 404
        ts = _utc_now_iso()
        if title is not None and content is not None:
            db.execute(
                "UPDATE notes SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                (title, content, ts, note_id),
            )
        elif title is not None:
            db.execute(
                "UPDATE notes SET title = ?, updated_at = ? WHERE id = ?",
                (title, ts, note_id),
            )
        elif content is not None:
            db.execute(
                "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
                (content, ts, note_id),
            )
        db.commit()
        row = db.execute(
            "SELECT id, title, content, updated_at FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()
        return jsonify(dict(row))

    @app.delete("/api/notes/<int:note_id>")
    def delete_note(note_id: int):
        db = get_db()
        cur = db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
        return ("", 204)

    # Background waker: insert a 'Wake Up!' note every 30s and delete it 30s later
    def _delete_note_later(note_id: int, delay: Optional[float] = None):
        if delay is None:
            delay = float(app.config.get("WAKER_TTL", 30.0))

        def _run():
            try:
                time.sleep(delay)
                with app.app_context():
                    db = get_db()
                    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                    db.commit()
            except Exception:
                # swallow errors; this is best-effort housekeeping
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _waker_main():
        # Initial delay so the first note is created after the interval
        try:
            time.sleep(float(app.config.get("WAKER_INTERVAL", 30.0)))
        except Exception:
            pass
        while True:
            try:
                with app.app_context():
                    # 1) Sweep first: delete only notes strictly older than TTL
                    ttl = float(app.config.get("WAKER_TTL", 30.0))
                    cutoff = (
                        (datetime.now(timezone.utc) - timedelta(seconds=ttl))
                        .replace(microsecond=0)
                        .isoformat()
                        .replace("+00:00", "Z")
                    )
                    db = get_db()
                    db.execute(
                        "DELETE FROM notes WHERE title = ? AND content = ? AND updated_at <= ?",
                        ("Wake Up!", "Waking server..", cutoff),
                    )
                    db.commit()

                    # 2) Then insert a fresh Wake Up note
                    ts = _utc_now_iso()
                    cur = db.execute(
                        "INSERT INTO notes (title, content, updated_at) VALUES (?, ?, ?)",
                        ("Wake Up!", "Waking server..", ts),
                    )
                    db.commit()
                    nid = cur.lastrowid
                _delete_note_later(nid, delay=float(app.config.get("WAKER_TTL", 30.0)))
            except Exception:
                # best-effort; skip cycle on error
                pass
            finally:
                time.sleep(float(app.config.get("WAKER_INTERVAL", 30.0)))

    if app.config.get("ENABLE_WAKER", True) and not app.config.get("TESTING"):
        # Start only once per process; with reloader, only in the child process
        should_start = (not app.debug) or (
            os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        )
        if should_start and not _WAKER_STARTED.is_set():
            _WAKER_STARTED.set()
            threading.Thread(target=_waker_main, daemon=True).start()

    return app


# Expose module-level WSGI app for Gunicorn ('gunicorn app:app')
app = create_app()


# Allow `python app.py` to run the dev server
if __name__ == "__main__":
    app.run(debug=True)
