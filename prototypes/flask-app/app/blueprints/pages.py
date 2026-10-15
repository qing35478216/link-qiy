"""页面路由（服务端渲染，Jinja2）。

对齐 LinkAI 管理后台信息架构（见 linkai-screenshots/app-*-配置全文.txt）：
- /console/factory          应用列表（卡片网格 + 创建弹窗）
- /console/agent?code=X     应用配置页（基础配置 Tab）
- /console/agent/chat?code=X 调试对话页
"""

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import App
from ..services.app_service import create_app_record, update_app_record

pages_bp = Blueprint("pages", __name__, url_prefix="/console")


@pages_bp.route("/factory")
@login_required
def factory():
    apps = (
        db.session.query(App)
        .filter_by(owner_id=current_user.id)
        .order_by(App.updated_at.desc())
        .all()
    )
    return render_template("factory.html", apps=apps)


@pages_bp.route("/factory/create", methods=["POST"])
@login_required
def factory_create():
    """创建应用（弹窗表单提交）。"""
    app_type = request.form.get("type", App.TYPE_LIGHTWEIGHT)
    name = (request.form.get("name") or "").strip() or "未命名应用"

    app = create_app_record(owner_id=current_user.id, name=name, app_type=app_type)
    return redirect(url_for("pages.agent_config", code=app.code))


@pages_bp.route("/agent")
@login_required
def agent_config():
    code = request.args.get("code", "")
    app = _get_owned_app_or_404(code)
    return render_template("agent_config.html", app=app)


@pages_bp.route("/agent/save", methods=["POST"])
@login_required
def agent_save():
    code = request.form.get("code", "")
    app = _get_owned_app_or_404(code)

    update_app_record(app, request.form)
    return redirect(url_for("pages.agent_config", code=app.code, saved="1"))


@pages_bp.route("/agent/delete", methods=["POST"])
@login_required
def agent_delete():
    code = request.form.get("code", "")
    app = _get_owned_app_or_404(code)
    db.session.delete(app)
    db.session.commit()
    return redirect(url_for("pages.factory"))


@pages_bp.route("/agent/chat")
@login_required
def agent_chat():
    code = request.args.get("code", "")
    app = _get_owned_app_or_404(code)
    return render_template("agent_chat.html", app=app)


def _get_owned_app_or_404(code: str) -> App:
    """取当前用户的应用；不存在或不属于自己一律 404（不暴露存在性）。"""
    if not code:
        abort(404)
    app = db.session.query(App).filter_by(code=code, owner_id=current_user.id).first()
    if not app:
        abort(404)
    return app
