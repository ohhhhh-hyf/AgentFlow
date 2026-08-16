"""题库检索配置。凭据优先读项目根 .env，缺省回退到题库文档里的实测值。"""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
DEFAULT_DATA_DIR = PACKAGE_DIR / "data" / "高中"

try:
    from llm_client.config import load_env
except Exception:  # pragma: no cover
    def load_env(path: Path) -> None:  # type: ignore[misc]
        if not path.exists():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.split("#", 1)[0].strip().strip("'\""))


load_env(PROJECT_ROOT / ".env")

DEFAULT_APP = "1786782559"
DEFAULT_APP_SECRET = "2woup7ftf4dx5ssq242zcot8ikhlgbtvsaefdg34"
DEFAULT_BASE = "https://dnfyyds.tech/server1"
DEFAULT_BANK_BASE = "https://dnfyyds.tech/server1/bank"
SUCCESS_CODE = 10000
STAGE_HIGH_SCHOOL = 3
MAX_PAGE_SIZE = 20
REQUEST_TIMEOUT = 90


def exercise_app() -> str:
    return (os.getenv("EXERCISE_SEARCH_APP") or DEFAULT_APP).strip()


def exercise_app_secret() -> str:
    return (os.getenv("EXERCISE_SEARCH_APP_SECRET") or DEFAULT_APP_SECRET).strip()


def exercise_base() -> str:
    return (os.getenv("EXERCISE_SEARCH_BASE") or DEFAULT_BASE).rstrip("/")


def exercise_bank_base() -> str:
    override = (os.getenv("EXERCISE_SEARCH_BANK_BASE") or "").strip()
    if override:
        return override.rstrip("/")
    root = exercise_base()
    if root.endswith("/bank"):
        return root
    return DEFAULT_BANK_BASE if root == DEFAULT_BASE.rstrip("/") else f"{root}/bank"
