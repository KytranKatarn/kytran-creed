import os


class Config:
    SECRET_KEY = os.environ.get("KCR_SECRET_KEY", "change-me-in-production")
    DATA_DIR = os.environ.get("KCR_DATA_DIR", os.path.expanduser("~/.kytran-creed"))
    DB_PATH = os.path.join(DATA_DIR, "creed.db")
    HOST = os.environ.get("KCR_HOST", "0.0.0.0")
    PORT = int(os.environ.get("KCR_PORT", "8086"))
    DEBUG = os.environ.get("KCR_DEBUG", "false").lower() == "true"
    ADMIN_USER = os.environ.get("KCR_ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("KCR_ADMIN_PASSWORD", "")
    PG_HOST = os.environ.get("DB_HOST", "")
    PG_PORT = int(os.environ.get("DB_PORT", "5432"))
    PG_NAME = os.environ.get("DB_NAME", "creed")
    PG_USER = os.environ.get("DB_USER", "creed")
    PG_PASSWORD_FILE = os.environ.get("DB_PASSWORD_FILE", "")

    @classmethod
    def pg_password(cls):
        if cls.PG_PASSWORD_FILE and os.path.exists(cls.PG_PASSWORD_FILE):
            return open(cls.PG_PASSWORD_FILE).read().strip()
        return os.environ.get("DB_PASSWORD", "")
