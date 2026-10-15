"""RESTX 控制台 API（/api/console/*）。

原型期同时提供「页面」与「API」两条路：
- 页面：服务端渲染（Jinja2），见 blueprints/pages.py
- API：RESTX，供后续接 SPA 前端或外部调用，Swagger 在 /api/doc
"""

from flask_restx import Namespace, Resource, fields

from ..extensions import db
from ..models import App
from ..services.app_service import create_app_record

console_ns = Namespace("console", description="管理台接口（原型）")

app_model = console_ns.model(
    "App",
    {
        "id": fields.Integer(readonly=True),
        "code": fields.String(readonly=True, description="LinkAI 风格 7 位随机码"),
        "name": fields.String(required=True),
        "type": fields.String(description="lightweight | knowledge"),
        "description": fields.String(),
        "opening": fields.String(description="开场介绍"),
        "questions": fields.List(fields.String(), description="问题推荐"),
        "model": fields.String(description="默认模型"),
        "temperature": fields.Float(),
        "memory_turns": fields.Integer(),
        "prompt": fields.String(description="应用设定（提示词）"),
        "is_public": fields.Boolean(),
        "created_at": fields.DateTime(readonly=True),
    },
)

create_model = console_ns.model(
    "AppCreate",
    {
        "name": fields.String(required=True),
        "type": fields.String(default="lightweight"),
    },
)


@console_ns.route("/apps")
class AppList(Resource):
    @console_ns.marshal_list_with(app_model)
    def get(self):
        return db.session.query(App).all()

    @console_ns.expect(create_model)
    @console_ns.marshal_with(app_model, code=201)
    def post(self):
        payload = console_ns.payload or {}
        return create_app_record(
            owner_id=1,  # 原型期未接鉴权，默认归 1 号用户
            name=payload.get("name", "未命名应用"),
            app_type=payload.get("type", App.TYPE_LIGHTWEIGHT),
        ), 201


@console_ns.route("/apps/<string:code>")
@console_ns.param("code", "应用 code")
class AppItem(Resource):
    @console_ns.marshal_with(app_model)
    def get(self, code: str):
        app = db.session.query(App).filter_by(code=code).first()
        if not app:
            console_ns.abort(404, f"应用 {code} 不存在")
        return app
