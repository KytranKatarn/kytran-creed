import os
import logging
from flask import Flask, jsonify
from kytran_creed.config import Config
from kytran_creed.db import init_db

__version__ = "0.1.0"

logger = logging.getLogger(__name__)


def create_app(config=None):
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    if config:
        app.config.update(config)
    else:
        app.config.from_object(Config)

    app.config.setdefault("SECRET_KEY", Config.SECRET_KEY)
    db_path = app.config.get("DB_PATH", Config.DB_PATH)
    init_db(db_path)

    from kytran_creed.pg import init_pg
    from kytran_creed.routes import register_all_routes
    from kytran_creed.auth import register_auth_routes, setup_required, create_admin

    init_pg()
    register_all_routes(app)
    register_auth_routes(app)

    # Auto-seed admin from env
    admin_user = app.config.get("ADMIN_USER") or Config.ADMIN_USER
    admin_pass = app.config.get("ADMIN_PASSWORD") or Config.ADMIN_PASSWORD
    if admin_pass and setup_required():
        create_admin(admin_user, admin_pass)

    @app.before_request
    def check_setup():
        from flask import request, redirect
        # Skip auth/setup/API/badge/health endpoints
        if request.endpoint in ("setup", "static", "health", "login", "logout", "dashboard.public_results"):
            return
        if request.path.startswith("/api/") or request.path.startswith("/badge/"):
            return
        if setup_required():
            return redirect("/setup")

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": __version__})

    return app


def main():
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
