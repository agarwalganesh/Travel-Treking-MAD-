import os
import secrets

# Base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _load_secret_key():
    """
    Return the secret key used to sign session cookies.

    Order of preference:
      1. The SECRET_KEY environment variable  (best choice for production).
      2. A random key saved in a local '.secret_key' file, so the value stays
         the same across restarts without ever being written into source code.

    This replaces the old hard-coded fallback key, which anyone could read from
    the source and use to forge admin session cookies. (Fix #1)
    """
    key_from_env = os.environ.get('SECRET_KEY')
    if key_from_env:
        return key_from_env

    key_file = os.path.join(BASE_DIR, '.secret_key')
    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            return f.read().strip()

    # First run without an env var: generate a strong key once and store it.
    new_key = secrets.token_hex(32)
    with open(key_file, 'w') as f:
        f.write(new_key)
    return new_key


class Config:
    # --- Session cookie signing key (Fix #1) ---
    SECRET_KEY = _load_secret_key()

    # --- Database (SQLite) ---
    DB_DIR = os.path.join(BASE_DIR, 'database')
    os.makedirs(DB_DIR, exist_ok=True)  # make sure the folder exists
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(DB_DIR, 'trekking.db')
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
