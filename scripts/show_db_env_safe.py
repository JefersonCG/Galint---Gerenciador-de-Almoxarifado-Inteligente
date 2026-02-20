import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url


def safe_part(url: str | None) -> str | None:
    if not url:
        return None

    url = url.strip()
    if (url.startswith('"') and url.endswith('"')) or (url.startswith("'") and url.endswith("'")):
        url = url[1:-1]

    return url.split("@", 1)[1] if "@" in url else url


env_url = os.environ.get("GALINT_DATABASE_URI") or os.environ.get("DATABASE_URL")
env_file = dotenv_values(".env")
file_url = env_file.get("GALINT_DATABASE_URI") or env_file.get("DATABASE_URL") or env_file.get("SQLALCHEMY_DATABASE_URI")


def has_password(url: str | None) -> bool | None:
    if not url:
        return None
    url = url.strip()
    if (url.startswith('"') and url.endswith('"')) or (url.startswith("'") and url.endswith("'")):
        url = url[1:-1]
    parsed = make_url(url)
    return bool(parsed.password)

print(
    "env_override_present=",
    bool(env_url),
    "safe=",
    safe_part(env_url),
    "has_password=",
    has_password(env_url),
)
print(
    "env_file_present=",
    bool(file_url),
    "safe=",
    safe_part(file_url),
    "has_password=",
    has_password(file_url),
)
