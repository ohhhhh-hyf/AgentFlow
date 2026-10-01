"""infra.llm.client —— 统一 LLMClient（适配 HTTP、WebSocket、vLLM）。"""
from __future__ import annotations

import infra.llm.llmclient as _mod

for _name in dir(_mod):
    globals()[_name] = getattr(_mod, _name)
