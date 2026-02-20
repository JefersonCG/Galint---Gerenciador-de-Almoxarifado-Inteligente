import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
	sys.path.insert(0, ROOT)

from urllib.parse import urlparse

from galint_flask import create_app


def _sanitize_db_url(url: str) -> dict:
	url = (url or "").strip().strip('"').strip("'")
	parsed = urlparse(url)
	return {
		"driver": parsed.scheme,
		"user": parsed.username,
		"host": parsed.hostname,
		"port": parsed.port,
		"database": (parsed.path or "").lstrip("/"),
		"has_password": bool(parsed.password),
		"safe_part": (url.split("@", 1)[1] if "@" in url else url),
	}


app = create_app()
uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
info = _sanitize_db_url(uri)
print("DB:", info)
