from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from meeting_agent.config import load_env
from meeting_agent.models import UserIdentity
from meeting_agent.orchestrator import MeetingAgentSystem
from meeting_agent.presenter import print_result


DEFAULT_SUMMARY_DIR = PROJECT_ROOT / "summary"
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "profile"


class ProgressPrinter:
    def __init__(self) -> None:
        self.index = 0
        self.active: dict[str, int] = {}

    def __call__(self, event: str, label: str) -> None:
        if event == "start":
            self.index += 1
            self.active[label] = self.index
            print(f"{self.index:02d}  {label}  ...", flush=True)
            return

        number = self.active.get(label, self.index)
        print(f"{number:02d}  {label}  完成", flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成用户视角会议纪要和待办事项",
    )
    parser.add_argument(
        "--summary-dir",
        type=Path,
        default=DEFAULT_SUMMARY_DIR,
        help="会议文本目录，目录中需要包含一个 .txt 文件",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="用户画像目录，目录中需要包含一个 .json 文件",
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
    if not folder.exists():
        raise FileNotFoundError(f"{label}目录不存在：{folder}")
    if not folder.is_dir():
        raise ValueError(f"{label}路径不是目录：{folder}")

    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"请在 {folder} 中放入一个{label}文件")
    if len(files) > 1:
        names = "\n".join(f"- {file.name}" for file in files)
        raise ValueError(
            f"{folder} 中发现多个{label}文件，请先只保留一个：\n{names}"
        )
    return files[0]


def _load_transcript(summary_dir: Path) -> str:
    meeting_file = _pick_single_file(summary_dir, "*.txt", "会议文本 .txt")
    transcript = meeting_file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise ValueError(f"{meeting_file} 是空文件，请写入会议内容")
    return transcript


def _load_user(profile_dir: Path) -> UserIdentity:
    profile_file = _pick_single_file(profile_dir, "*.json", "用户画像 .json")
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    return UserIdentity(**profile)


async def _review_preview(result) -> str:
    print_result(result)

    while True:
        decision = await asyncio.to_thread(
            input,
            "\n确认请输入 pass：",
        )
        if decision.strip().lower() == "pass":
            return "pass"
        print("请输入 pass 后继续。", flush=True)


async def run(summary_dir: Path, profile_dir: Path, env_file: Path) -> None:
    load_env(_resolve_path(env_file))

    transcript = _load_transcript(_resolve_path(summary_dir))
    user = _load_user(_resolve_path(profile_dir))

    print("正在生成会议纪要和待办事项，请稍候...\n", flush=True)
    system = MeetingAgentSystem(progress_handler=ProgressPrinter())
    await system.run(
        transcript,
        user,
        review_handler=_review_preview,
    )


def main() -> None:
    args = _parser().parse_args()
    try:
        asyncio.run(
            run(
                args.summary_dir,
                args.profile_dir,
                args.env,
            )
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
