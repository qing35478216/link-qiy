"""Flask 应用工厂。

原型沙箱约定（与主仓 services/ 的边界）：
- 这里只做「快速验证想法」，不进主仓四层架构，不写 tenant_id/OTel 等铁律
- 想法验证满意后，按 docs/03 的 ADR 落到 services/ 时用 FastAPI 重写

技术栈对齐 LinkAI 对标物（Dify）：Flask 同步 + RESTX + SQLAlchemy + PostgreSQL。
"""

from flask import Flask

from .config import Config


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # 中文不转义（Flask 2.3 起 JSON_AS_ASCII 配置项已废弃，必须走 app.json）
    app.json.ensure_ascii = False

    # —— 扩展注册 ——
    from .extensions import api, db, login_manager

    db.init_app(app)
    login_manager.init_app(app)
    api.init_app(app)

    # flask-login 用户加载器
    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # —— 蓝图注册 ——
    from .blueprints.auth import auth_bp
    from .blueprints.pages import pages_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)

    # RESTX 命名空间挂在 api 上（Swagger: /api/doc）
    from .blueprints.console_api import console_ns

    api.add_namespace(console_ns, path="/console")

    # 根路径：已登录进应用工厂，否则去登录
    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("pages.factory"))
        return redirect(url_for("auth.login"))

    # 首次启动时建表（原型期免去 alembic；正式环境请改用迁移）
    with app.app_context():
        db.create_all()

    return app
