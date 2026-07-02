import os

# Base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Key for signing cookies and session data securely
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'trek-secret-key-12345'
    
    # Absolute path to the SQLite database file in the trekking_management/database/ folder
    DB_DIR = os.path.join(BASE_DIR, 'database')
    
    # Ensure the database directory exists
    os.makedirs(DB_DIR, exist_ok=True)
    
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(DB_DIR, 'trekking.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
