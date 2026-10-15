"""原型配置。

数据库指向本机 colima 里的 linkai-postgres（docker-compose.yml 默认值）。
"""

import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    # colima 容器 linkai-postgres（compose 默认账号）
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://linkai:linkai_dev_password@127.0.0.1:5432/linkai",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 中文不转义（Flask 2.3 起 JSON_AS_ASCII 配置项已废弃）
    JSON_AS_ASCII = False

    # flask-restx 不用 app.json，而是读自己的 RESTX_JSON 配置
    RESTX_JSON = {"ensure_ascii": False}
