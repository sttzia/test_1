# Notes App (Flask + Vanilla JS)

A simple notes application with a Flask backend (SQLite) and a lightweight HTML/CSS/JS frontend.

## Features

- Create, read, update, delete notes
- Search notes client-side
- Auto-sorted by last updated
- Minimal dependencies (Flask only)

## Quickstart (Windows PowerShell)

1. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Run the server

```powershell
$env:FLASK_APP = "app:create_app"
flask run
```

Then open http://127.0.0.1:5000 in your browser.

Alternatively, you can run `python app.py`:

```powershell
python app.py
```

This uses the dev server with debug enabled.

## Project Structure

- `app.py` — Flask app factory, SQLite schema, and REST API
- `templates/index.html` — Frontend HTML
- `static/app.css` — Styles
- `static/app.js` — Client-side logic for CRUD
- `requirements.txt` — Python dependency list
- `tests/smoke_test.py` — Minimal API test

## API

- GET `/api/notes` → `[{ id, title, content, updated_at }]`
- GET `/api/notes/<id>` → `{ id, title, content, updated_at }`
- POST `/api/notes` body `{ title, content }` → 201 with created note
- PUT `/api/notes/<id>` body `{ title?, content? }` → updated note
- DELETE `/api/notes/<id>` → 204

## Testing

Tests use Flask's test client and an in-memory SQLite database.

```powershell
# PowerShell
$env:PYTHONPATH = "."; python -m pytest -q
```

If pytest isn't installed:

```powershell
pip install pytest
```

## Notes

- The default database is stored at `%PROJECT%/instance/notes.db`. The `instance` folder is created automatically.
- Cache busting is disabled in development via a no-store header.
- For production, consider enabling proper static caching and using a WSGI server like `waitress` or `gunicorn`.
