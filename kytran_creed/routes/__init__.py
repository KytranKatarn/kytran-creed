def register_all_routes(app):
    from kytran_creed.routes.aia_routes import aia_bp
    from kytran_creed.routes.api_routes import api_bp
    from kytran_creed.routes.badge_routes import badge_bp
    from kytran_creed.routes.dashboard_routes import dashboard_bp
    from kytran_creed.routes.internal_routes import internal_bp
    from kytran_creed.routes.onboarding_routes import onboarding_bp
    from kytran_creed.routes.orgs_routes import org_pages_bp, orgs_bp
    from kytran_creed.routes.public_routes import public_bp
    from kytran_creed.routes.standard_routes import standard_bp
    from kytran_creed.routes.tenant_portal_routes import tenant_portal_bp
    from kytran_creed.routes.welfare_routes import welfare_bp

    app.register_blueprint(aia_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(badge_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(internal_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(orgs_bp)
    app.register_blueprint(org_pages_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(standard_bp)
    app.register_blueprint(tenant_portal_bp)
    app.register_blueprint(welfare_bp)
