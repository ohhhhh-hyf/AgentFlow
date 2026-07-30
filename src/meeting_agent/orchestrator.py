from __future__ import annotations

import json

from langgraph.graph import END, START, StateGraph

from .agents import (
    ActionItemsAgent,
    FinalIntegrationAgent,
    MeetingUnderstandingAgent,
    MinutesGenerationAgent,
    PerspectiveModelingAgent,
)
from .client import DeepSeekClient
from .models import (
    FinalReport,
    UserIdentity,
)
from .state import MeetingState
from .validation import validate_payload


def _json(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return json.dumps(value, ensure_ascii=False, indent=2)


class MeetingAgentSystem:
    """使用 LangGraph 编排五个会议 Agent。"""

    def __init__(
        self,
        client: DeepSeekClient | None = None,
    ) -> None:
        self.client = client or DeepSeekClient()

        self.meeting_understanding_agent = MeetingUnderstandingAgent(self.client)
        self.perspective_modeling_agent = PerspectiveModelingAgent(self.client)
        self.minutes_generation_agent = MinutesGenerationAgent(self.client)
        self.action_items_agent = ActionItemsAgent(self.client)
        self.final_integration_agent = FinalIntegrationAgent(self.client)

    async def _meeting_understanding_node(
        self,
        state: MeetingState,
    ) -> dict:
        result = await self.meeting_understanding_agent.run(state["transcript"])
        return {"meeting_understanding": result.model_dump()}

    async def _perspective_modeling_node(
        self,
        state: MeetingState,
    ) -> dict:
        result = await self.perspective_modeling_agent.run(
            state["transcript"],
            _json(state["user"]),
        )
        return {"perspective_profile": result.model_dump()}

    @staticmethod
    def _shared_context(state: MeetingState) -> str:
        return (
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"会议原文：\n{state['transcript']}"
        )

    async def _minutes_generation_node(self, state: MeetingState) -> dict:
        result = await self.minutes_generation_agent.run(
            self._shared_context(state)
        )
        return {"minutes_draft": result.model_dump()}

    async def _action_items_node(self, state: MeetingState) -> dict:
        result = await self.action_items_agent.run(
            self._shared_context(state)
        )
        return {"extracted_action_items": result.model_dump()}

    async def _final_integration_node(self, state: MeetingState) -> dict:
        context = (
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"会议理解：\n{_json(state['meeting_understanding'])}\n\n"
            f"用户视角模型：\n{_json(state['perspective_profile'])}\n\n"
            f"个性化纪要草稿：\n{_json(state['minutes_draft'])}\n\n"
            f"待办提取结果：\n{_json(state['extracted_action_items'])}"
        )
        result = await self.final_integration_agent.run(context)
        return {"final_report": result.model_dump()}

    def _build_graph(self) -> object:
        builder = StateGraph(MeetingState)

        builder.add_node(
            "meeting_understanding",
            self._meeting_understanding_node,
        )
        builder.add_node(
            "perspective_modeling",
            self._perspective_modeling_node,
        )
        builder.add_node(
            "minutes_generation",
            self._minutes_generation_node,
        )
        builder.add_node(
            "action_items",
            self._action_items_node,
        )
        builder.add_node(
            "final_integration",
            self._final_integration_node,
        )

        # 第一层：会议理解和用户视角建模并行。
        builder.add_edge(START, "meeting_understanding")
        builder.add_edge(START, "perspective_modeling")

        # 等待第一层全部完成，再并行生成纪要和待办。
        first_layer = ["meeting_understanding", "perspective_modeling"]
        builder.add_edge(first_layer, "minutes_generation")
        builder.add_edge(first_layer, "action_items")

        # 等待第二层全部完成，再进行最终整合。
        builder.add_edge(
            ["minutes_generation", "action_items"],
            "final_integration",
        )
        builder.add_edge("final_integration", END)

        return builder.compile()

    async def run(
        self,
        transcript: str,
        user: UserIdentity | None = None,
    ) -> FinalReport:
        if not transcript.strip():
            raise ValueError("会议文字不能为空")

        initial_state: MeetingState = {
            "transcript": transcript,
            "user": (user or UserIdentity()).model_dump(),
        }
        graph = self._build_graph()
        state = await graph.ainvoke(initial_state)

        return validate_payload(
            FinalReport,
            state["final_report"],
        )
