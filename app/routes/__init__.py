# app/routes/__init__.py
def register_routes(app):
    from .auth import bp as auth_bp
    from .sqlmap_api import bp as sqlmap_bp
 

    app.register_blueprint(auth_bp)
    app.register_blueprint(sqlmap_bp)

