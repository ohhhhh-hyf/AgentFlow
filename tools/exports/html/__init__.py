"""各任务线的 HTML/交互产物渲染器（离线单文件）。

- ``knowledge_graph``：notes.graph 的 Cytoscape.js 交互图 + 学习地图 Markdown
- ``checklist_graph``：notes.checklist 的可嵌入知识图谱
- ``mindmap``：导图大纲 → markmap HTML / Playwright PNG
- ``consensus_decision``：共识决策的决策备忘录（Markdown + 交互 HTML）

2026-09-22 从 ``tools/exports/`` 顶层收进本子包：``exports/`` 只留通用落盘编排
（``outputs.py``），渲染器按职责归到 ``html/``。
"""
