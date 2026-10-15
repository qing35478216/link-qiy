"""数据模型（原型期最小集，对齐 Phase 0 出口标准）。

表命名加 proto_ 前缀，避免与主仓 services/ 的正式表冲突
（主仓用 alembic 管理自己的 schema，这里是独立的原型沙箱）。
"""

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "proto_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False, default="")
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    apps = db.relationship("App", backref="owner", lazy="dynamic")

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class App(db.Model):
    """智能体应用。

    字段对齐 LinkAI 应用配置页「基础配置」Tab（见 docs/04 3.1 / 截图基准）：
    应用名称 / 应用code / 应用类型 / 应用描述 / 开场介绍 / 问题推荐 /
    模型设置（默认模型 / 温度 / 记忆轮数）/ 应用设定（提示词）/ 是否公开。
    """

    __tablename__ = "proto_apps"

    TYPE_LIGHTWEIGHT = "lightweight"  # 轻量应用：一段提示词快速创建
    TYPE_KNOWLEDGE = "knowledge"      # 知识应用：私有数据定制问答

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(32), nullable=False, default=TYPE_LIGHTWEIGHT)
    description = db.Column(db.Text, default="")

    # 对话相关
    opening = db.Column(db.Text, default="")          # 开场介绍
    questions = db.Column(db.JSON, default=list)      # 问题推荐（预设问题列表）

    # 模型设置
    model = db.Column(db.String(128), default="DeepSeek-R1")  # 默认模型
    temperature = db.Column(db.Float, default=0.7)
    memory_turns = db.Column(db.Integer, default=5)           # 记忆轮数

    # 应用设定（提示词）
    prompt = db.Column(db.Text, default="")

    # 分享
    is_public = db.Column(db.Boolean, default=False)

    owner_id = db.Column(db.Integer, db.ForeignKey("proto_users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def share_url(self) -> str:
        return f"/app/{self.code}"

    @property
    def type_label(self) -> str:
        return "知识应用" if self.type == self.TYPE_KNOWLEDGE else "轻量应用"
