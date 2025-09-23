from app import create_app

# Expose WSGI callable for Gunicorn / Render
app = create_app()
