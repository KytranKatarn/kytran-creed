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
        # Public multi-tenant pages (tasks #3894/#3905) — no login, no setup gate
        if (
            request.path in ("/directory", "/get-scored")
            or request.path.startswith("/org/")
            or request.path.startswith("/verify-email/")
        ):
            return
        if setup_required():
            return redirect("/setup")

    @app.after_request
    def add_cors_pna_headers(resp):
        from flask import request

        # The public read-only API + badges are consumed cross-origin (creed-ai.org
        # governance widget, WTF, etc.). When a visitor's DNS resolves
        # creed.kytranempowerment.com to a PRIVATE/LAN IP — e.g. AdGuard split-horizon
        # on the hub LAN returns 192.168.1.200 — Chrome's Private Network Access blocks
        # the public-origin -> private-address fetch unless the (PNA) preflight answers
        # with Access-Control-Allow-Private-Network: true. Per-route handlers already set
        # Allow-Origin on GETs but nothing answered the OPTIONS preflight. This adds the
        # full CORS + PNA set to every API/badge response (incl. the auto-OPTIONS one),
        # so the live feed works from the LAN too — not just from the public internet.
        if request.path.startswith("/api/") or request.path.startswith("/badge/"):
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS, HEAD"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Private-Network"] = "true"
            resp.headers["Access-Control-Max-Age"] = "86400"
        return resp

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": __version__})

    return app


def main():
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
