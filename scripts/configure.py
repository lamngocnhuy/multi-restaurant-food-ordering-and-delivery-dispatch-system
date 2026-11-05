#!/usr/bin/env python3
"""Create local deployment secrets without installing Python dependencies."""

from pathlib import Path
import os
import secrets
import sys


def main() -> int:
    destination = Path(__file__).resolve().parents[1] / ".env"
    if destination.exists():
        print(".env already exists; keeping its configuration and secrets.")
        return 0
    password = secrets.token_hex(24)
    contents = f"""# Generated locally; do not commit or share this file.
POSTGRES_DB=gather
POSTGRES_USER=gather
POSTGRES_PASSWORD={password}
DATABASE_URL=postgresql+psycopg://gather:{password}@localhost:5432/gather
SECRET_KEY={secrets.token_hex(32)}
PAYMENT_CALLBACK_SECRET={secrets.token_hex(32)}
APP_ENV=development
APP_PORT=8000
BASE_URL=http://localhost:8000
TRUSTED_HOSTS=localhost,127.0.0.1,testserver
COOKIE_SECURE=false
ENABLE_SCHEDULER=true
PAYMENT_PROVIDER=sandbox
SEED_DEMO=true
DEMO_PASSWORD=Demo123!
PUBLIC_HOST=localhost
TLS_EMAIL=
"""
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(contents)
    print("Created private .env with new database, session, and payment secrets.")
    print("Start the website with: docker compose up --build -d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
