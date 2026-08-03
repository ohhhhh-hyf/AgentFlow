from __future__ import annotations

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


SUMMARY_DIR = PROJECT_ROOT / "summary"
PROFILE_DIR = PROJECT_ROOT / "profile"


def _pick_single_file(folder: Path, pattern: str, label: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"请在 {folder} 中放入一个{label}文件")
    if len(files) > 1:
        names = "\n".join(f"- {file.name}" for file in files)
        raise ValueError(
            f"{folder} 中发现多个{label}文件，请先只保留一个：\n{names}"
        )
    return files[0]


def _load_transcript() -> str:
    meeting_file = _pick_single_file(SUMMARY_DIR, "*.txt", "会议文本 .txt")
    transcript = meeting_file.read_text(encoding="utf-8").strip()
    if not transcript:
        raise ValueError(f"{meeting_file} 是空文件，请写入会议内容")
    print(f"会议文件：{meeting_file.name}", flush=True)
    return transcript


def _load_user() -> UserIdentity:
    profile_file = _pick_single_file(PROFILE_DIR, "*.json", "用户画像 .json")
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    user = UserIdentity(**profile)
    print(f"用户画像：{profile_file.name}", flush=True)
    return user


async def _review_preview(result) -> str:
    print("\n" + "-" * 64)
    print("审核预览：以下内容尚未正式输出")
    print("-" * 64)
    print_result(result)

    while True:
        decision = await asyncio.to_thread(
            input,
            "\n确认内容无误请输入 pass：",
        )
        if decision.strip().lower() == "pass":
            return "pass"
        print("尚未通过审核，请输入 pass 后继续。", flush=True)


async def run() -> None:
    load_env(PROJECT_ROOT / ".env")
    transcript = _load_transcript()
    user = _load_user()

    identity = f"{user.name or '未命名用户'}｜{user.role or '未设置角色'}"
    print(f"\n正在为 {identity} 生成用户视角会议纪要和待办事项……", flush=True)

    result = await MeetingAgentSystem().run(
        transcript,
        user,
        review_handler=_review_preview,
    )

    print("\n" + "=" * 64)
    print(f"正式输出｜用户：{identity}")
    print("=" * 64)
    print_result(result)


def main() -> None:
    try:
        asyncio.run(run())
    except (OSError, ValueError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
