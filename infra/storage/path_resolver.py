"""infra.storage.path_resolver —— 统一且严格的多租户用户路径解析器。

核心原则：
1. 任何与用户相关的数据路径必须通过本模块统一获取；
2. 严格校验 user_id，严禁路径遍历字符（如 '..'、'/'、'\\'）；
3. 严格限制在 data/{user_id}/ 内部，严禁未经授权回退到公共无主目录。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class StoragePathResolver:
    """多租户存储路径解析器。"""

    def __init__(self, data_root: Path | None = None) -> None:
        if data_root is not None:
            self._root = Path(data_root).resolve()
        else:
            env_dir = os.getenv("AGENTFLOW_DATA_DIR", "").strip()
            self._root = (Path(env_dir) if env_dir else (PROJECT_ROOT / "data")).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def validate_user_id(self, user_id: str) -> str:
        uid = (user_id or "").strip()
        if not uid:
            raise ValueError("user_id 不能为空")
        if "/" in uid or "\\" in uid or uid in {".", ".."}:
            raise ValueError(f"非法 user_id: {user_id!r}")
        return uid

    def user_root(self, user_id: str) -> Path:
        uid = self.validate_user_id(user_id)
        p = self._root / uid
        p.mkdir(parents=True, exist_ok=True)
        return p

    def docs_dir(self, user_id: str) -> Path:
        p = self.user_root(user_id) / "docs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def output_dir(self, user_id: str, request_id: str) -> Path:
        uid = self.validate_user_id(user_id)
        rid = (request_id or "").strip()
        if not rid or "/" in rid or "\\" in rid or rid in {".", ".."}:
            raise ValueError(f"非法 request_id: {request_id!r}")
        p = self.user_root(uid) / "output" / rid
        p.mkdir(parents=True, exist_ok=True)
        return p

    def knowledge_dir(self, user_id: str) -> Path:
        p = self.user_root(user_id) / "knowledge"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def chromadb_dir(self, user_id: str) -> Path:
        p = self.knowledge_dir(user_id) / "chromadb"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def catalogs_dir(self, user_id: str, subject: str = "") -> Path:
        p = self.knowledge_dir(user_id) / "catalogs"
        if subject:
            p = p / subject
        p.mkdir(parents=True, exist_ok=True)
        return p

    def memory_dir(self, user_id: str) -> Path:
        p = self.user_root(user_id) / "memory"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def resolve_input_file(self, user_id: str, kind: str, filename: str) -> Path:
        """安全解析用户输入文件（严格限制在 data/{user_id}/{kind}/ 内）。"""
        uid = self.validate_user_id(user_id)
        raw = (filename or "").strip()
        if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
            raise ValueError(f"非法文件名: {filename!r}")
        target_dir = self.user_root(uid) / kind
        target_file = (target_dir / raw).resolve()
        if not target_file.is_file() or target_dir.resolve() not in target_file.parents:
            raise FileNotFoundError(f"用户文件不存在：{kind}/{raw}（请放入 data/{uid}/{kind}/）")
        return target_file


# 全局单例
default_resolver = StoragePathResolver()

__all__ = ["StoragePathResolver", "default_resolver"]
