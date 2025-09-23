import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from flask import Flask, jsonify, render_template, request, g, current_app


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

    # Static file cache headers (dev-friendly)
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    # API
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

    return app


# Allow `python app.py` to run the dev server
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
