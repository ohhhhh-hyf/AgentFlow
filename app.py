from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from meeting_agent.config import load_env
from meeting_agent.models import UserIdentity, is_objective_perspective
from meeting_agent.orchestrator import MeetingAgentSystem
from meeting_agent.presenter import ProgressPrinter, print_result


DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "summary"
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "profile"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成用户视角会议纪要和待办事项",
    )
    parser.add_argument(
        "--summary",
        "--summary-dir",
        dest="summary",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="会议文本文件或目录。传目录时，目录中需要包含一个 .txt 文件",
    )
    parser.add_argument(
        "--profile",
        "--profile-dir",
        dest="profile",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="用户画像 JSON 文件或目录。传目录时，目录中需要包含一个 .json 文件",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="环境变量文件路径",
    )
    return parser


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _pick_single_file(folder: Path, pattern: str, label: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"请在 {folder} 中放入一个{label}文件")
    if len(files) > 1:
        names = "\n".join(f"- {file.name}" for file in files)
        raise ValueError(
            f"{folder} 中发现多个{label}文件，请直接指定其中一个文件：\n{names}"
        )
    return files[0]


def _resolve_input_file(path: Path, suffix: str, label: str) -> Path:
    path = _resolve_path(path)
    if not path.exists():
        raise FileNotFoundError(f"{label}路径不存在：{path}")

    if path.is_file():
        if path.suffix.lower() != suffix:
            raise ValueError(f"{label}文件必须是 {suffix}：{path}")
        return path

    if path.is_dir():
        return _pick_single_file(path, f"*{suffix}", label)

    raise ValueError(f"{label}路径既不是文件也不是目录：{path}")


def _load_transcript(summary_path: Path) -> str:
    meeting_file = _resolve_input_file(summary_path, ".txt", "会议文本")
    transcript = meeting_file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise ValueError(f"{meeting_file} 是空文件，请写入会议内容")
    return transcript


def _load_user(profile_path: Path) -> UserIdentity:
    profile_file = _resolve_input_file(profile_path, ".json", "用户画像")
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    return UserIdentity(**profile)


async def run(summary: Path, profile: Path, env_file: Path) -> None:
    load_env(_resolve_path(env_file))

    transcript = _load_transcript(summary)
    user = _load_user(profile)

    system = MeetingAgentSystem(progress_handler=ProgressPrinter())
    result = await system.run(transcript, user)
    print_result(result, objective_perspective=is_objective_perspective(user))


def main() -> None:
    args = _parser().parse_args()
    try:
        asyncio.run(
            run(
                args.summary,
                args.profile,
                args.env,
            )
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
