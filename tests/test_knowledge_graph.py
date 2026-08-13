"""knowledge_graph 生成侧校验与增量合并的单元测试（unittest，零外部依赖）。

覆盖两个曾缺失的保证：
1. 生成侧确定性校验 sanitize_graph：悬空边剥离、同名节点合并、边去重、规范化
2. 增量图谱合并 merge_graph / apply_graph_memory：同名节点合并（definition 取长）、
   边三元组去重、悬空边过滤、累积图谱不丢失、注入-解析-合并闭环

运行：python3 -m unittest tests.test_knowledge_graph -v
"""
from __future__ import annotations

import unittest

from tools.memory.graph import (
    apply_graph_memory,
    inject_graph,
    merge_graph,
    parse_graph_from_text,
    sanitize_graph,
)


class SanitizeGraphTest(unittest.TestCase):
    def test_drops_dangling_edges(self):
        draft = {
            "title": "t",
            "nodes": [{"name": "函数", "definition": "d"}],
            "edges": [
                {"source": "函数", "relation": "包含", "target": "参数"},
                {"source": "函数", "relation": "属于", "target": "函数"},
            ],
        }
        out = sanitize_graph(draft)
        self.assertEqual(out["nodes"], [{"name": "函数", "definition": "d"}])
        # 「参数」不在 nodes → 悬空边剥离；自环「函数→函数」保留
        self.assertEqual(len(out["edges"]), 1)
        self.assertEqual(out["edges"][0]["target"], "函数")

    def test_drops_invalid_edges_and_non_dicts(self):
        draft = {
            "nodes": [{"name": "a"}],
            "edges": [
                {"source": "a", "relation": "x"},  # 缺 target
                {"source": "a", "relation": "x", "target": "b"},  # b 悬空
                "not-a-dict",
                {"source": "a", "relation": "y", "target": "a"},
            ],
        }
        out = sanitize_graph(draft)
        self.assertEqual(len(out["edges"]), 1)
        self.assertEqual(out["edges"][0]["relation"], "y")

    def test_merges_same_name_nodes_keep_longest_definition(self):
        draft = {
            "nodes": [
                {"name": "函数", "definition": "短"},
                {"name": "函数", "definition": "较长定义", "section": "函数与极限"},
                {"name": " 导数 ", "definition": "x"},
            ],
            "edges": [],
        }
        out = sanitize_graph(draft)
        names = {n["name"] for n in out["nodes"]}
        self.assertEqual(names, {"函数", "导数"})  # 同名合并 + 空白规范化
        fn = next(n for n in out["nodes"] if n["name"] == "函数")
        self.assertEqual(fn["definition"], "较长定义")  # definition 取更长
        self.assertEqual(fn["section"], "函数与极限")

    def test_dedups_edges_by_triple(self):
        draft = {
            "nodes": [{"name": "a"}, {"name": "b"}],
            "edges": [
                {"source": "a", "relation": "r", "target": "b"},
                {"source": " a ", "relation": "r", "target": "b"},  # 规范化后同三元组
            ],
        }
        out = sanitize_graph(draft)
        self.assertEqual(len(out["edges"]), 1)


class MergeGraphTest(unittest.TestCase):
    def test_node_merge_keeps_old_nodes_and_longest_definition(self):
        old = {
            "graph": {
                "title": "高数",
                "nodes": [
                    {"name": "极限", "definition": "旧定义较长"},
                    {"name": "导数", "definition": "d"},
                ],
                "edges": [{"source": "极限", "relation": "引出", "target": "导数"}],
            }
        }
        incoming = {
            "title": "高数",
            "nodes": [{"name": "极限", "definition": "新"}, {"name": "积分", "definition": "i"}],
            "edges": [{"source": "极限", "relation": "引出", "target": "导数"}],
        }
        rec = merge_graph(old, incoming)
        graph = rec["graph"]
        names = {n["name"] for n in graph["nodes"]}
        self.assertEqual(names, {"极限", "导数", "积分"})  # 累积不丢
        limit = next(n for n in graph["nodes"] if n["name"] == "极限")
        self.assertEqual(limit["definition"], "旧定义较长")  # 取更长

    def test_edge_dedup_and_dangling_filter(self):
        old = {"graph": {"nodes": [{"name": "a"}, {"name": "b"}], "edges": []}}
        incoming = {
            "nodes": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            "edges": [
                {"source": "a", "relation": "r", "target": "b"},
                {"source": "a", "relation": "r", "target": "b"},  # 重复
                {"source": "a", "relation": "r", "target": "幽灵"},  # 悬空
            ],
        }
        graph = merge_graph(old, incoming)["graph"]
        self.assertEqual(len(graph["edges"]), 1)

    def test_empty_incoming_keeps_record(self):
        old = {"graph": {"nodes": [{"name": "a"}], "edges": []}}
        rec = merge_graph(old, {})
        self.assertEqual(len(rec["graph"]["nodes"]), 1)


class ApplyGraphMemoryTest(unittest.TestCase):
    def test_roundtrip_inject_parse_merge(self):
        record = {
            "subject": "高等数学",
            "run_count": 1,
            "graph": {
                "title": "高等数学",
                "nodes": [{"name": "函数", "definition": "已有定义"}],
                "edges": [{"source": "函数", "relation": "属于", "target": "函数"}],
            },
        }
        text = inject_graph(record)
        self.assertIn("已积累图谱数据", text)
        parsed = parse_graph_from_text(text)
        self.assertEqual(parsed["nodes"][0]["name"], "函数")

        # 新草稿与累积图谱合并：旧节点不丢、新节点并入
        draft = {
            "title": "高等数学",
            "nodes": [{"name": "函数", "definition": ""}, {"name": "极限", "definition": "l"}],
            "edges": [{"source": "函数", "relation": "引出", "target": "极限"}],
        }
        merged = apply_graph_memory(draft, text)
        names = {n["name"] for n in merged["nodes"]}
        self.assertEqual(names, {"函数", "极限"})
        fn = next(n for n in merged["nodes"] if n["name"] == "函数")
        self.assertEqual(fn["definition"], "已有定义")  # 旧定义保留（新草稿为空）

    def test_inject_empty_graph_returns_empty(self):
        self.assertEqual(inject_graph({}), "")


if __name__ == "__main__":
    unittest.main()
