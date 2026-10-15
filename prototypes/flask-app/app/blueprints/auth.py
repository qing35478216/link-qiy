"""登录 / 登出 / 注册。

原型期用 session + flask-login；密码用 werkzeug 的 pbkdf2 哈希。
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.factory"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user = db.session.query(User).filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(request.args.get("next") or url_for("pages.factory"))
        flash("邮箱或密码不正确")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """原型期开放注册（省去邮件验证；正式实现走 services/platform 账户域）。"""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        name = (request.form.get("name") or "").strip()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("邮箱和密码必填")
        elif db.session.query(User).filter_by(email=email).first():
            flash("该邮箱已注册，直接登录")
            return redirect(url_for("auth.login"))
        else:
            user = User(email=email, name=name or email.split("@")[0])
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            return redirect(url_for("pages.factory"))

    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
