"""生成模型 / 审核模型 / Report 校验。由 tools/scripts/sync_domain.py 写入，勿手改。"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Literal

from tools.validation import (
    OutputValidationError,
    _action,
    _choice,
    _exact_fields,
    _review_check,
    _string,
    _string_list,
    validate_supervisor_semantics,
)

from .models_base import ModelMixin


# ── 生成模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 生成模型生成区结束 ──

# ── 审核模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 审核模型生成区结束 ──

# ── Report 校验生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── Report 校验生成区结束 ──
