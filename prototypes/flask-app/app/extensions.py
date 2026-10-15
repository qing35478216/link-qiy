"""扩展实例集中地（避免循环导入）。"""

from flask_login import LoginManager
from flask_restx import Api
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录"

# RESTX：挂在 /api 前缀，自带 Swagger UI（/api/doc）
api = Api(
    title="LinkAI Console API（原型）",
    version="0.1.0",
    prefix="/api",
    doc="/doc",
)
