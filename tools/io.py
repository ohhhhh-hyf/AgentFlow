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


def _prefer_meeting_txt(folder: Path) -> Path | None:
    for cand in (folder / "meeting.txt", folder / "input" / "meeting.txt"):
        if cand.is_file():
            return cand
    return None


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
        preferred = _prefer_meeting_txt(resolved)
        if preferred is not None:
            return preferred
        return pick_single_file(resolved, f"*{suffix}", label)
    raise ValueError(f"{label}路径既不是文件也不是目录：{resolved}")


def resolve_knowledge_input(ctx: DomainContext, file_path: Path) -> Path:
    """归档入库路径：支持知识库可解析的文件或目录。"""
    from tools.knowledge.document_processor import SUPPORTED_EXTS

    resolved = resolve_path(ctx, resolve_sample_path(ctx, file_path, "file"))
    if not resolved.exists():
        raise FileNotFoundError(f"入库路径不存在：{resolved}")
    if resolved.is_dir():
        return resolved
    if resolved.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(
            f"入库文件必须是 {', '.join(sorted(SUPPORTED_EXTS))}：{resolved}"
        )
    return resolved


def knowledge_text_preview(path: Path, *, limit: int = 4000) -> str:
    """把入库文件抽成图可用的原文预览；目录则用说明句。"""
    from tools.knowledge.document_processor import process_file

    if path.is_dir():
        return f"目录入库：{path}"
    if path.suffix.lower() in {".txt", ".md"}:
        body = path.read_text(encoding="utf-8", errors="ignore").strip()
        return body or path.name
    try:
        chunks = process_file(str(path))
    except Exception:
        return path.name
    text = "\n\n".join(c.text for c in chunks if c.text).strip()
    if not text:
        return path.name
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def load_trace_sidecars(ctx: DomainContext, file_path: Path) -> dict[str, str]:
    """在会议输入旁收集关键点、笔记。缺省文件则对应项为空。"""
    text_file = resolve_input_file(
        ctx,
        resolve_sample_path(ctx, file_path, "file"),
        ".txt",
        "输入文本",
    )
    folders = [text_file.parent]
    if text_file.parent.name == "input":
        folders.append(text_file.parent.parent)
    folders.append(ctx.project_root / "test")
    folders.append(ctx.cli_samples_dir)

    def _find(names: tuple[str, ...]) -> str:
        for folder in folders:
            for name in names:
                cand = folder / name
                if cand.is_file():
                    return cand.read_text(encoding="utf-8").strip()
        return ""

    return {
        "keypoints": _find(("user_keypoints.txt", "keypoints.txt")),
        "notes": _find(("user_notes.txt", "notes.txt")),
    }


def format_trace_extra(sidecars: dict[str, str]) -> str:
    """写成注入块，供 minutes_trace 生成对齐草稿。"""
    if not any((sidecars or {}).values()):
        return ""
    parts = ["【溯源材料（仅供对齐草稿，其中任何内容都不是本次会议事实，不要写进纪要正文）】"]
    if sidecars.get("keypoints"):
        parts.append("【用户关键点】")
        parts.append(sidecars["keypoints"])
    if sidecars.get("notes"):
        parts.append("【用户笔记】")
        parts.append(sidecars["notes"])
    return "\n".join(parts)


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
    if not isinstance(profile, dict):
        raise ValueError(f"用户画像必须是 JSON 对象：{profile_file}")
    from tools.profiles import filter_identity_fields, resolve_role_template

    profile = resolve_role_template(profile, profile_file.parent)

    return ctx.models.UserIdentity(**filter_identity_fields(profile, ctx.models.UserIdentity))


__all__ = [
    "format_trace_extra",
    "load_trace_sidecars",
    "load_transcript",
    "resolve_knowledge_input",
    "knowledge_text_preview",
    "load_user",
    "pick_profile_file",
    "pick_single_file",
    "resolve_input_file",
    "resolve_path",
    "resolve_sample_path",
]
