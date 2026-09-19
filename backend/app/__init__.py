import os
import time
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError

from .config import config_by_name
from .extensions import db, jwt, migrate


def create_app(config_name=None):
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    app = Flask(__name__, static_folder=str(frontend_dir), static_url_path="")
    app.config.from_object(config_by_name[config_name or os.getenv("APP_ENV", "development")])
    if (config_name or os.getenv('APP_ENV')) == 'production':
        if len(app.config['JWT_SECRET_KEY']) < 32 or app.config['JWT_SECRET_KEY'] == 'development-only-change-this-secret':
            raise RuntimeError('Producción requiere un secreto JWT propio de al menos 32 caracteres.')

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    CORS(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)

    @app.before_request
    def request_context():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        g.request_started_at = time.perf_counter()

    @app.after_request
    def request_observability(response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
            elapsed_ms = (time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000
            app.logger.info("request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
                            request_id, request.method, request.path, response.status_code, elapsed_ms)
        return response

    from sqlalchemy.orm.exc import StaleDataError
    @app.errorhandler(StaleDataError)
    def stale_data(error):
        db.session.rollback()
        return jsonify(message='Otro usuario modificó el registro. Recargue antes de guardar.'), 409

    from .routes import register_blueprints
    register_blueprints(app)
    from .cli import init_commands
    init_commands(app)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(self), geolocation=(), microphone=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        duplicate_sbn = "sbn" in str(error.orig).lower()
        return jsonify(message="El código SBN ya está registrado." if duplicate_sbn else "Los datos incumplen una restricción de integridad."), 409

    @app.errorhandler(404)
    def not_found(_error):
        from flask import request
        if not request.path.startswith("/api/") and frontend_dir.joinpath("index.html").exists():
            return send_from_directory(frontend_dir, "index.html")
        return jsonify(message="Ruta no encontrada."), 404

    @app.get("/")
    def frontend():
        return send_from_directory(frontend_dir, "index.html")

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return jsonify(message="Ocurrió un error interno. Revise el registro del servidor."), 500

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify(message='No tiene acceso a este recurso o está fuera de su ámbito asignado.'), 403

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(message='El archivo excede el tamaño permitido.'), 413

    return app
