"""让测试无需安装即可 import task_runner（把包根目录塞进 sys.path）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
