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

    init_pg()
    register_all_routes(app)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "version": __version__})

    return app


def main():
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
