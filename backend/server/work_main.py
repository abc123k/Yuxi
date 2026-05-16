import subprocess
import asyncio
import sys
import os

# 必须放在最顶层！
if sys.platform == "win32":
    # 把当前文件 (main.py) 的上一级的上一级 (即根目录 Yuxi) 加入到 sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


if __name__ == "__main__":
    # 将 backend 目录加入 path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    # 直接调用 arq 命令
    subprocess.run([
        sys.executable, "-m", "arq",
        "server.worker_main.WorkerSettings"
    ])
