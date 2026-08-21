"""AgentFlow Web UI 入口。

启动地址/端口在这里配置（环境变量可覆盖）：
- GRADIO_SERVER_NAME  监听地址（默认 127.0.0.1；服务器部署用 0.0.0.0）
- GRADIO_SERVER_PORT  端口（默认 7860）
- GRADIO_SHARE        是否生成临时公网分享链接（默认关）
"""
from __future__ import annotations

from web.app import main

if __name__ == "__main__":
    main(
        host="127.0.0.1",
        port=7860,
    )
