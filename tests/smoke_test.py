import json
from app import create_app


def get_client():
    # Use shared in-memory DB for tests
    app = create_app(
        {"TESTING": True, "DATABASE": "file:memdb1?mode=memory&cache=shared"}
    )
    return app.test_client()


def test_crud_flow():
    c = get_client()

    # Initially empty
    rv = c.get("/api/notes")
    assert rv.status_code == 200
    assert rv.get_json() == []

    # Create
    rv = c.post(
        "/api/notes",
        data=json.dumps({"title": "Hello", "content": "World"}),
        content_type="application/json",
    )
    assert rv.status_code == 201
    created = rv.get_json()
    nid = created["id"]

    # List should contain the note
    rv = c.get("/api/notes")
    assert any(n["id"] == nid for n in rv.get_json())

    # Get
    rv = c.get(f"/api/notes/{nid}")
    assert rv.status_code == 200
    assert rv.get_json()["title"] == "Hello"

    # Update title only
    rv = c.put(
        f"/api/notes/{nid}",
        data=json.dumps({"title": "Updated"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["title"] == "Updated"

    # Update content only
    rv = c.put(
        f"/api/notes/{nid}",
        data=json.dumps({"content": "Body"}),
        content_type="application/json",
    )
    assert rv.status_code == 200
    assert rv.get_json()["content"] == "Body"

    # Delete
    rv = c.delete(f"/api/notes/{nid}")
    assert rv.status_code == 204

    # Get 404
    rv = c.get(f"/api/notes/{nid}")
    assert rv.status_code == 404
