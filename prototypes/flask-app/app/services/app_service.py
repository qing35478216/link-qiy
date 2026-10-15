"""应用创建 / 更新逻辑（从路由里拆出来，保持路由只做 HTTP）。"""

from ..codegen import generate_unique_code
from ..extensions import db
from ..models import App


def _code_taken(code: str) -> bool:
    return db.session.query(App).filter_by(code=code).first() is not None


def create_app_record(owner_id: int, name: str, app_type: str = App.TYPE_LIGHTWEIGHT) -> App:
    """创建应用并分配 LinkAI 风格 7 位 code。"""
    app = App(
        code=generate_unique_code(_code_taken),
        name=name,
        type=app_type,
        owner_id=owner_id,
        questions=[],
    )
    db.session.add(app)
    db.session.commit()
    return app


def update_app_record(app: App, form: dict) -> App:
    """用表单数据更新应用（对齐配置页字段）。

    questions 是多行文本，一行一个预设问题。
    """
    app.name = (form.get("name") or app.name).strip() or app.name
    app.type = form.get("type") or app.type
    app.description = (form.get("description") or "").strip()
    app.opening = (form.get("opening") or "").strip()
    app.prompt = (form.get("prompt") or "").strip()
    app.model = (form.get("model") or app.model).strip()
    app.is_public = bool(form.get("is_public"))

    questions_raw = (form.get("questions") or "").strip()
    app.questions = [q.strip() for q in questions_raw.splitlines() if q.strip()]

    try:
        app.temperature = float(form.get("temperature") or app.temperature)
    except ValueError:
        pass
    try:
        app.memory_turns = int(form.get("memory_turns") or app.memory_turns)
    except ValueError:
        pass

    db.session.commit()
    return app
