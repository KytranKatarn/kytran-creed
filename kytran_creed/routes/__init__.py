def register_all_routes(app):
    from kytran_creed.routes.api_routes import api_bp
    from kytran_creed.routes.badge_routes import badge_bp
    from kytran_creed.routes.dashboard_routes import dashboard_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(badge_bp)
    app.register_blueprint(dashboard_bp)
