from __future__ import annotations

from client import LLMClient

from ....models import LibrarySupervisorReview


class LibrarySupervisor:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def review(self, context: str) -> LibrarySupervisorReview:
        failed = "没有找到入库文件" in (context or "")
        return LibrarySupervisorReview.validate(
            {
                "decision": "reject" if failed else "approve",
                "library_check": {
                    "status": "fail" if failed else "pass",
                    "findings": ["缺少入库文件"] if failed else [],
                },
                "feedback": ["请用 --file 指定一份或多份资料"] if failed else [],
            }
        )

