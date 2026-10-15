"""启动入口。

用法：
    cd prototypes/flask-app
    .venv/bin/python run.py

然后打开 http://127.0.0.1:5001
（5000 在 macOS 常被 AirDrop 占用，特意避开）

注意：debug 开着但**禁用 reloader**（use_reloader=False）——debug 的自动重启在
频繁改代码时会出现端口占用冲突导致进程静默退出，原型期改完手动重启更稳。
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)
