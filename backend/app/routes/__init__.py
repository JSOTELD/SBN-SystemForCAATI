def register_blueprints(app):
    from .admin import admin_bp
    from .assets import assets_bp
    from .auth import auth_bp
    from .inventory import inventory_bp
    from .research import research_bp
    from .study import study_bp
    from .guide_audit import guide_audit_bp
    from ..validation import register_validation

    for blueprint in (auth_bp, assets_bp, research_bp, study_bp, guide_audit_bp, inventory_bp, admin_bp):
        app.register_blueprint(blueprint, url_prefix="/api")
    register_validation(app)
