import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def database_uri():
    explicit = os.getenv("DATABASE_URL")
    if explicit:
        return explicit.replace("mysql://", "mysql+pymysql://", 1)
    user = quote_plus(os.getenv("MYSQL_USER", "itam_user"))
    password = quote_plus(os.getenv("MYSQL_PASSWORD", "itam_password"))
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = os.getenv("MYSQL_PORT", "3306")
    name = os.getenv("MYSQL_DATABASE", "itam_sbn")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class BaseConfig:
    PORT = int(os.getenv("PORT", "3001"))
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    JWT_SECRET_KEY = os.getenv("JWT_SECRET", "development-only-change-this-secret")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_TOKEN_LOCATION = ['cookies', 'headers']
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SAMESITE = 'Lax'
    JWT_COOKIE_SECURE = False
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', str(Path(__file__).resolve().parents[1] / 'private_uploads'))
    BACKUP_FOLDER = os.getenv('BACKUP_FOLDER', str(Path(__file__).resolve().parents[1] / 'private_backups'))
    CORS_ORIGINS = [value.strip() for value in os.getenv("CORS_ORIGIN", "http://localhost:5173").split(",") if value.strip()]


class DevelopmentConfig(BaseConfig):
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"


class ProductionConfig(BaseConfig):
    DEBUG = False
    JWT_COOKIE_SECURE = True
    JWT_TOKEN_LOCATION = ['cookies']


if os.getenv("FLASK_ENV") == "production" and (BaseConfig.JWT_SECRET_KEY == "development-only-change-this-secret" or len(BaseConfig.JWT_SECRET_KEY) < 32):
    raise RuntimeError("JWT_SECRET debe definirse con al menos 32 caracteres antes de iniciar en producción.")


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


config_by_name = {"development": DevelopmentConfig, "production": ProductionConfig, "testing": TestingConfig}
