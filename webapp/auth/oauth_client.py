"""oauth_client.py — Authlib OAuth client (bound to app in app.py via init_app)."""
from authlib.integrations.flask_client import OAuth

oauth = OAuth()
