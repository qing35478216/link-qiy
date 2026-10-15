"""路由：一个页面 + 一组 JSON API。

页面走 Jinja2 模板，API 走 JSON——原型期两种渲染方式都留好示例，
你要哪种就往哪种上加。
"""

from flask import Blueprint, jsonify, render_template, request

bp = Blueprint("main", __name__)

# 原型期用内存数据；接数据库时换掉
_IDEAS: list[dict] = []


@bp.get("/")
def index():
    return render_template("index.html", ideas=_IDEAS)


@bp.get("/api/health")
def health():
    return jsonify(status="ok")


@bp.post("/api/ideas")
def create_idea():
    """接收 JSON，存内存并回显——最省事的「先跑通链路」示例。"""
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    if not text:
        return jsonify(error="text 不能为空"), 400

    idea = {"id": len(_IDEAS) + 1, "text": text}
    _IDEAS.append(idea)
    return jsonify(idea), 201


@bp.get("/api/ideas")
def list_ideas():
    return jsonify(ideas=_IDEAS)
