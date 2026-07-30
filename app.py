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


MEETING_FILE = PROJECT_ROOT / "examples" / "community_meeting.txt"
PROFILE_FILES = [
    PROJECT_ROOT / "examples" / "property_manager_profile.json",
    PROJECT_ROOT / "examples" / "volunteer_profile.json",
]
ENV_FILE = PROJECT_ROOT / ".env"


async def run() -> None:
    load_env(ENV_FILE)
    transcript = MEETING_FILE.read_text(encoding="utf-8")
    system = MeetingAgentSystem()

    for profile_file in PROFILE_FILES:
        profile_data = json.loads(profile_file.read_text(encoding="utf-8"))
        user = UserIdentity(**profile_data)
        identity = f"{user.name}｜{user.role}"

        print(f"\n正在为 {identity} 生成纪要和待办，请稍候……", flush=True)
        result = await system.run(transcript, user)

        print("\n" + "=" * 64)
        print(f"用户：{identity}")
        print("=" * 64)
        print_result(result)


def main() -> None:
    try:
        asyncio.run(run())
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
