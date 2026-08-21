"""知识库配置：Embedding（硅基流动）+ LLM（复用项目根目录 .env 的 DeepSeek）。

配置优先级：代码默认值 → 项目根 .env → 环境变量 → KnowledgeTool 显式参数。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from llm_client.config import load_env
except Exception:  # pragma: no cover - 单测/脚手架时允许无 llm_client
    def load_env(path: Path) -> None:  # type: ignore[misc]
        if not path.exists():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env(PROJECT_ROOT / ".env")

ENV_EMBEDDING_API_KEY = "SILICONFLOW_API_KEY"
ENV_EMBEDDING_API_KEY_ALT = "EMBEDDING_API_KEY"
ENV_LLM_API_KEY = "DEEPSEEK_API_KEY"
ENV_LLM_API_KEY_EXPLICIT = "KNOWLEDGE_LLM_API_KEY"

DEFAULT_EMBEDDING_BASE_URL = os.getenv(
    "KNOWLEDGE_EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1"
)
DEFAULT_EMBEDDING_MODEL = os.getenv("KNOWLEDGE_EMBEDDING_MODEL", "BAAI/bge-m3")


def _knowledge_llm_config() -> tuple[str, str]:
    """知识库 LLM 的 base_url / model：跟随 Agent 后端（LLM_BACKEND）。

    - 显式 KNOWLEDGE_LLM_BASE_URL / KNOWLEDGE_LLM_MODEL 始终优先；
    - LLM_BACKEND=vllm 时复用 vLLM 服务器（LLM_VLLM_*），
      与 Agent 共用同一套 OpenAI 兼容 HTTP 接口；
    - 其它后端（http / websocket）回退 DeepSeek 官方（DEEPSEEK_*）。
    """
    explicit_base = os.getenv("KNOWLEDGE_LLM_BASE_URL")
    explicit_model = os.getenv("KNOWLEDGE_LLM_MODEL")
    backend = os.getenv("LLM_BACKEND", "").strip().lower()
    if backend == "vllm":
        base = (
            explicit_base
            or os.getenv("LLM_VLLM_BASE_URL")
            or "http://127.0.0.1:8000/v1"
        )
        model = (
            explicit_model
            or os.getenv("LLM_VLLM_MODEL")
            or "deepseek-v4-flash-0731"
        )
    else:
        base = explicit_base or os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        model = explicit_model or os.getenv("DEEPSEEK_MODEL") or "deepseek-chat"
    return base, model


def _knowledge_llm_key() -> str:
    """知识库 LLM 的 api_key：显式 KNOWLEDGE_LLM_API_KEY 优先，否则跟随后端。

    当显式 key 与当前端点提供方不匹配（如 LLM_BACKEND=vllm 却配置了
    DeepSeek 的 sk- key）时告警，避免把一家提供方的凭据发给另一家端点。
    """
    explicit = os.getenv(ENV_LLM_API_KEY_EXPLICIT, "").strip()
    backend = os.getenv("LLM_BACKEND", "").strip().lower()
    if explicit:
        base = (os.getenv("KNOWLEDGE_LLM_BASE_URL") or "").strip()
        if not base and backend == "vllm":
            import logging

            logging.getLogger(__name__).warning(
                "KNOWLEDGE_LLM_API_KEY 与 vLLM 端点（LLM_VLLM_BASE_URL）"
                "可能不匹配：显式 key 会发给 vLLM 服务器。"
                "若确需 vLLM，请改用 LLM_VLLM_API_KEY。"
            )
        return explicit
    if backend == "vllm":
        return os.getenv("LLM_VLLM_API_KEY", "").strip()
    return os.getenv(ENV_LLM_API_KEY, "").strip()


DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL = _knowledge_llm_config()
DEFAULT_PERSIST_DIR = os.getenv(
    "KNOWLEDGE_PERSIST_DIR",
    str(PROJECT_ROOT / "data" / "knowledge" / "chromadb"),
)


def persist_dir_for_user(user_id: str) -> str:
    """按用户隔离的知识库向量目录：``data/{user_id}/knowledge/chromadb``。

    user 顶层物理隔离：每个用户一个独立 chroma 库；学科仍用
    metadata where 细分（见 ``_scope``）。
    """
    uid = (user_id or "").strip()
    if not uid:
        return DEFAULT_PERSIST_DIR
    from tools.memory.store import safe_id

    return str(PROJECT_ROOT / "data" / safe_id(uid) / "knowledge" / "chromadb")

def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").split("#", 1)[0].strip().strip("'\"")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").split("#", 1)[0].strip().strip("'\"")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").split("#", 1)[0].strip().strip("'\"")
    if not raw:
        return default
    return str(raw).lower() not in {"0", "false", "off", "no", "disable", "disabled"}


DEFAULT_CHUNK_SIZE = _env_int("KNOWLEDGE_CHUNK_SIZE", 500)
DEFAULT_CHUNK_OVERLAP = _env_int("KNOWLEDGE_CHUNK_OVERLAP", 100)
DEFAULT_TOP_K = _env_int("KNOWLEDGE_TOP_K", 5)
DEFAULT_MAX_TOKENS = _env_int("KNOWLEDGE_MAX_TOKENS", 1024)
# 检索质量：score 阈值过滤（低于该相似度的块不进结果）+ 混合检索开关与关键词数
# 默认 0.50：实测相关块 0.60-0.78、无关块 0.32-0.46，0.50 保住相关且滤掉无关
DEFAULT_MIN_SCORE = _env_float("KNOWLEDGE_MIN_SCORE", 0.50)
DEFAULT_HYBRID_SEARCH = _env_bool("KNOWLEDGE_HYBRID_SEARCH", True)
DEFAULT_HYBRID_KEYWORDS = _env_int("KNOWLEDGE_HYBRID_KEYWORDS", 6)
DEFAULT_EMBEDDING_VERIFY_SSL = _env_bool("KNOWLEDGE_EMBEDDING_VERIFY_SSL", True)


def _embedding_key() -> str:
    return (
        os.getenv(ENV_EMBEDDING_API_KEY, "").strip()
        or os.getenv(ENV_EMBEDDING_API_KEY_ALT, "").strip()
    )


@dataclass
class KnowledgeToolConfig:
    """知识库工具配置。api_key 缺省时从项目 .env / 环境变量读取。"""

    embedding_api_key: str = ""
    embedding_base_url: str = DEFAULT_EMBEDDING_BASE_URL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    llm_api_key: str = ""
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model: str = DEFAULT_LLM_MODEL
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    top_k: int = DEFAULT_TOP_K
    max_tokens: int = DEFAULT_MAX_TOKENS
    persist_dir: str = DEFAULT_PERSIST_DIR
    # 检索质量：min_score 过滤低相关块；hybrid_search 开启向量+关键词混合召回
    min_score: float = DEFAULT_MIN_SCORE
    hybrid_search: bool = DEFAULT_HYBRID_SEARCH
    hybrid_keywords: int = DEFAULT_HYBRID_KEYWORDS
    embedding_verify_ssl: bool = DEFAULT_EMBEDDING_VERIFY_SSL

    def __post_init__(self) -> None:
        if not self.embedding_api_key:
            self.embedding_api_key = _embedding_key()
        if not self.llm_api_key:
            self.llm_api_key = _knowledge_llm_key()

    def ensure_keys(self) -> "KnowledgeToolConfig":
        missing = []
        if not self.embedding_api_key:
            missing.append(
                f"embedding_api_key（环境变量 {ENV_EMBEDDING_API_KEY}）"
            )
        if not self.llm_api_key:
            backend = os.getenv("LLM_BACKEND", "").strip().lower()
            llm_key_env = (
                "LLM_VLLM_API_KEY"
                if backend == "vllm"
                else ENV_LLM_API_KEY
            )
            missing.append(f"llm_api_key（环境变量 {llm_key_env}）")
        if missing:
            raise ValueError(
                "缺少 API Key: "
                + "、".join(missing)
                + "。请写入项目根目录 .env，或在 KnowledgeTool(...) 传入。"
            )
        return self
