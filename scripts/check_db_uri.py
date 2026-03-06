import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
	sys.path.insert(0, ROOT)

from galint_flask import create_app

app = create_app()
uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
uri = uri.strip().strip('"').strip("'")

parsed = urlparse(uri)
safe_part = uri.split("@", 1)[1] if "@" in uri else uri

print(
	"host=%s port=%s db=%s user=%s safe_part=%s"
	% (
		parsed.hostname,
		parsed.port,
		(parsed.path or "").lstrip("/"),
		parsed.username,
		safe_part,
	)
)
