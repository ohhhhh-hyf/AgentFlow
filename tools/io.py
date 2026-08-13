"""Input path resolution and loading for domain runs."""
from __future__ import annotations

import json
from pathlib import Path

from .runtime_context import DomainContext


def resolve_path(ctx: DomainContext, path: Path) -> Path:
    if path.is_absolute():
        return path
    root_candidate = (ctx.project_root / path).resolve()
    if root_candidate.exists():
        return root_candidate
    samples_candidate = (ctx.cli_samples_dir / path).resolve()
    if samples_candidate.exists():
        return samples_candidate
    return (ctx.samples_dir / path).resolve()


def resolve_sample_path(ctx: DomainContext, path: Path, sample_kind: str) -> Path:
    """Resolve a CLI path against samples/{domain}/{sample_kind} first."""
    if path.is_absolute():
        return path
    root_candidate = (ctx.project_root / path).resolve()
    if root_candidate.exists():
        return root_candidate
    kind_candidate = (ctx.cli_samples_dir / sample_kind / path).resolve()
    if kind_candidate.exists():
        return kind_candidate
    samples_candidate = (ctx.cli_samples_dir / path).resolve()
    if samples_candidate.exists():
        return samples_candidate
    return (ctx.cli_samples_dir / sample_kind / path).resolve()


def pick_single_file(folder: Path, pattern: str, label: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"请在 {folder} 中放入一个{label}文件")
    if len(files) > 1:
        names = "\n".join(f"- {file.name}" for file in files)
        raise ValueError(
            f"{folder} 中发现多个{label}文件，请直接指定其中一个文件：\n{names}"
        )
    return files[0]


def resolve_input_file(
    ctx: DomainContext, path: Path, suffix: str, label: str
) -> Path:
    resolved = resolve_path(ctx, path)
    if not resolved.exists():
        raise FileNotFoundError(f"{label}路径不存在：{resolved}")
    if resolved.is_file():
        if resolved.suffix.lower() != suffix:
            raise ValueError(f"{label}文件必须是 {suffix}：{resolved}")
        return resolved
    if resolved.is_dir():
        return pick_single_file(resolved, f"*{suffix}", label)
    raise ValueError(f"{label}路径既不是文件也不是目录：{resolved}")


def load_transcript(ctx: DomainContext, file_path: Path) -> str:
    text_file = resolve_input_file(
        ctx,
        resolve_sample_path(ctx, file_path, "file"),
        ".txt",
        "输入文本",
    )
    transcript = text_file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise ValueError(f"{text_file} 是空文件，请写入内容")
    return transcript


def pick_profile_file(folder: Path) -> Path:
    """多画像时优先客观样例；个人视角请显式指定 personal_profile.json。"""
    objective = folder / "object_profile.json"
    if objective.is_file():
        return objective
    personal = folder / "personal_profile.json"
    if personal.is_file():
        return personal
    return pick_single_file(folder, "*.json", "用户画像")


def load_user(ctx: DomainContext, profile_path: Path):
    resolved = resolve_sample_path(ctx, profile_path, "profile")
    if not resolved.exists():
        # 兼容：未传具体文件时走 samples/{domain}/profile
        resolved = resolve_path(ctx, profile_path)
    if resolved.is_dir():
        profile_file = pick_profile_file(resolved)
    else:
        profile_file = resolve_input_file(
            ctx,
            resolve_sample_path(ctx, profile_path, "profile"),
            ".json",
            "用户画像",
        )
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    return ctx.models.UserIdentity(**profile)


__all__ = [
    "load_transcript",
    "load_user",
    "pick_profile_file",
    "pick_single_file",
    "resolve_input_file",
    "resolve_path",
    "resolve_sample_path",
]
