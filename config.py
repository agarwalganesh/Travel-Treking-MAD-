import os
import secrets

# Base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_secret_key():
    """
    Return the secret key used to sign session cookies.

    Order of preference:
      1. The SECRET_KEY environment variable  (required in production / Vercel).
      2. A random key saved in a local '.secret_key' file (local dev only).
      3. An in-memory random key -- used when the filesystem is read-only
         (e.g. Vercel serverless). Set SECRET_KEY in the Vercel dashboard so
         sessions stay valid across cold starts.
    """
    key_from_env = os.environ.get('SECRET_KEY')
    if key_from_env:
        return key_from_env

    key_file = os.path.join(BASE_DIR, '.secret_key')
    try:
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                return f.read().strip()
        # First run without an env var: generate a strong key once and store it.
        new_key = secrets.token_hex(32)
        with open(key_file, 'w') as f:
            f.write(new_key)
        return new_key
    except OSError:
        # Read-only filesystem (serverless) -> fall back to an ephemeral key.
        return secrets.token_hex(32)


def _database_uri():
    """
    Decide where the database lives.

    - If DATABASE_URL is set (e.g. a hosted Postgres), use it. This is the
      recommended option on Vercel, whose filesystem is not durable.
    - Otherwise use a local SQLite file in the project's 'database/' folder.
      If that folder can't be created because the filesystem is read-only
      (Vercel), fall back to the writable '/tmp' directory.

    NOTE: SQLite in /tmp is ephemeral on serverless -- it resets between cold
    starts. That is fine for a demo, but set DATABASE_URL for real persistence.
    """
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # SQLAlchemy needs the 'postgresql://' scheme, not 'postgres://'.
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url

    db_dir = os.path.join(BASE_DIR, 'database')
    try:
        os.makedirs(db_dir, exist_ok=True)
    except OSError:
        db_dir = '/tmp'  # read-only project dir on Vercel; /tmp is writable
    return 'sqlite:///' + os.path.join(db_dir, 'trekking.db')


class Config:
    # --- Session cookie signing key (Fix #1) ---
    SECRET_KEY = _load_secret_key()

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Session cookie hardening (Fix #8) ---
    # HTTPONLY: JavaScript cannot read the cookie (limits damage from XSS).
    # SAMESITE 'Lax': the browser will not send the cookie on cross-site POST
    #                 requests, which is an extra layer of CSRF protection.
    # SECURE: only send the cookie over HTTPS. Kept off by default so the app
    #         still works on http://localhost during development; enable it in
    #         production by setting the SESSION_COOKIE_SECURE=1 environment var.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('1', 'true', 'yes')
