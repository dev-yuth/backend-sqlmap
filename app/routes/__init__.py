# app/routes/__init__.py
def register_routes(app):
    from .auth import bp as auth_bp
    from .sqlmap_api import bp as sqlmap_bp
    from .view.views import bp as views_bp  # แก้ชื่อ import ให้ตรงกับ blueprint
    from .user import bp as user_bp  # ต้องมีไฟล์ app/routes/user.py
    from .crawler import bp as crawler_bp
    from .sqlmap_urls import bp as sqlmap_urls_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(sqlmap_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(crawler_bp)
    app.register_blueprint(sqlmap_urls_bp)

