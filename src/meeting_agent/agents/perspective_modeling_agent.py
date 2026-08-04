from __future__ import annotations

from ..client import LLMClient
from ..models import PerspectiveProfile


class PerspectiveModelingAgent:
    """把静态用户画像转换为本次会议中的关注视角（支持个人/客观两种模式）。"""

    SYSTEM_PROMPT = """你是视角建模 Agent。你的任务是结合用户身份画像和会议原文，构建本次会议的「视角模型」。

### 模式选择（最高优先级）
请先读取用户画像中的 `perspective` 字段，严格按以下规则选择模式：

1. **当 perspective = "objective"** → 进入【客观全员视角】
2. **当 perspective 缺省、为空、或为其他任何值** → 进入【个人用户视角】（默认）

不得自行切换模式，不得混合两种视角的规则。

---

### 【客观全员视角】（perspective = "objective"）
目标：建立一份中立、完整、不绑定任何真实个人的会议事实视角。

规则：
- name 保持 null（除非画像中明确给出记录员名称）。
- inferred_role 固定描述为中立角色，例如「客观会议记录 / 全员视角」。
- responsibilities / goals：完整覆盖会议目的、已形成的决策、风险、未决问题，以及各方明确的分工与待办。
- concerns：重点关注决策口径不一致、责任未明确分配、证据不足、遗漏相关方任务等问题。
- relevant_topics：覆盖会议主要议题，禁止只聚焦某一个角色相关的内容。
- evidence：只引用原文中体现「需要全员知晓 / 多方协作 / 整体推进」的依据。
- 严禁虚构任何具体个人身份，严禁把客观记录视角伪装成某个参会人的个人视角。

---

### 【个人用户视角】（默认）
目标：围绕当前用户，构建与其职责和利益相关的会议视角。

规则：
- 用户画像中明确提供的姓名、角色、部门、职责视为既定事实，模型不得覆盖或修改。
- 仅允许补充「画像中缺失、且能从会议原文中谨慎、有直接依据推断」的信息。
- 证据不足时，相关字段必须留空，并相应降低 confidence。
- 重点关注：用户的职责范围、目标、关注点，以及与用户直接相关的议题、决策、风险和待办。
- 禁止把与用户无关的全局信息强行纳入个人视角。

---

### 通用强制规则（两种模式都必须遵守）
1. 不得创造会议原文中不存在的事实、结论、责任人或时间节点。
2. 所有推断必须有原文直接支撑，禁止合理想象或过度延伸。
3. confidence 字段必须真实反映本次视角建模的整体可靠程度（证据越充分，confidence 越高）。
4. 输出保持客观中性，不添加个性化建议或评价性语言。

请严格按照所选模式执行，优先保证事实忠实性与视角一致性。"""

    OUTPUT_CONTRACT = """{
  "confidence": "high|medium|low",
  "name": "字符串或null",
  "inferred_role": "字符串或null",
  "responsibilities": ["字符串"],
  "goals": ["字符串"],
  "concerns": ["字符串"],
  "relevant_topics": ["字符串"],
  "evidence": ["字符串"]
}"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        transcript: str,
        user_json: str,
    ) -> PerspectiveProfile:
        return await self.client.structured(
            self.SYSTEM_PROMPT,
            f"用户画像：\n{user_json}\n\n会议原文：\n{transcript}",
            PerspectiveProfile,
            self.OUTPUT_CONTRACT,
        )
