# -*- coding: utf-8 -*-
"""merge_catalog / normalize_catalog_enums 单测：占位节点不丢数据、新增节点、枚举归一化。"""
from __future__ import annotations

from domain.notes.tasks.catalog.merge import (
    merge_catalog,
    normalize_catalog_enums,
)


def _existing(chapters: list[dict]) -> dict:
    return {
        "course": "高数",
        "version": "2",
        "mode": "build",
        "chapters": chapters,
        "added_chapters": [],
        "added_topics": [],
        "added_knowledge_points": [],
        "updated_knowledge_points": [],
        "merged_nodes": [],
        "unmatched_content": [],
        "uncertain_nodes": [],
    }


def _limit_chapter() -> dict:
    return {
        "id": "ch_001",
        "name": "极限",
        "change_type": "unchanged",
        "topics": [
            {
                "id": "tp_001",
                "name": "极限概念",
                "change_type": "unchanged",
                "knowledge_points": [
                    {
                        "id": "kp_001",
                        "name": "数列极限定义",
                        "knowledge_type": "concept",
                        "importance": "5",
                        "practice_type": ["证明"],
                    }
                ],
            }
        ],
    }


class TestMergeCatalog:
    def test_占位unchanged节点保留旧内容(self):
        """优化：unchanged 只输出 id+change_type 占位，merge 必须保留旧内容。"""
        existing = _existing([_limit_chapter()])
        incoming = {
            "course": "高数",
            "version": "3",
            "mode": "incremental_update",
            "chapters": [{"id": "ch_001", "change_type": "unchanged"}],
            "unmatched_content": [],
            "uncertain_nodes": [],
        }
        merged = merge_catalog(existing, incoming)
        ch = merged["chapters"][0]
        assert ch["id"] == "ch_001"
        assert ch["name"] == "极限", "占位节点不能清空旧章节名"
        kp = ch["topics"][0]["knowledge_points"][0]
        assert kp["name"] == "数列极限定义"
        assert kp["practice_type"] == ["证明"], "旧 KP 细节必须完整保留"

    def test_新章added并分配新ID(self):
        """新增章节应标记 added，且不破坏已有章节。"""
        existing = _existing([_limit_chapter()])
        incoming = {
            "course": "高数",
            "version": "3",
            "mode": "incremental_update",
            "chapters": [
                {"id": "ch_001", "change_type": "unchanged"},
                {
                    "id": "ch_002",
                    "name": "导数",
                    "change_type": "added",
                    "topics": [
                        {
                            "id": "tp_002",
                            "name": "导数概念",
                            "change_type": "added",
                            "knowledge_points": [
                                {
                                    "id": "kp_002",
                                    "name": "导数定义",
                                    "knowledge_type": "concept",
                                    "importance": "5",
                                    "practice_type": ["计算"],
                                }
                            ],
                        }
                    ],
                },
            ],
            "unmatched_content": [],
            "uncertain_nodes": [],
        }
        merged = merge_catalog(existing, incoming)
        by_id = {c["id"]: c for c in merged["chapters"]}
        assert by_id["ch_001"]["name"] == "极限"
        assert by_id["ch_002"]["name"] == "导数"
        assert by_id["ch_002"]["change_type"] == "added"
        assert by_id["ch_002"]["topics"][0]["id"] == "tp_002"
        assert merged["version"] == "3"

    def test_首次build分配确定性ID(self):
        """无历史目录时 merge 按首次生成处理，程序分配 ch/tp/kp ID。"""
        incoming = {
            "course": "课程",
            "mode": "build",
            "chapters": [
                {
                    "name": "章一",
                    "topics": [
                        {
                            "name": "主题一",
                            "knowledge_points": [{"name": "知识点一", "knowledge_type": "concept"}],
                        }
                    ],
                }
            ],
        }
        merged = merge_catalog(None, incoming)
        ch = merged["chapters"][0]
        assert ch["id"].startswith("ch_")
        assert ch["topics"][0]["id"].startswith("tp_")
        assert ch["topics"][0]["knowledge_points"][0]["id"].startswith("kp_")
        assert merged["mode"] == "build"
        assert merged["version"] == "1"


class TestNormalizeCatalogEnums:
    def test_中文枚举映射为标准值(self):
        catalog = {
            "chapters": [
                {
                    "id": "ch_001",
                    "name": "章",
                    "change_type": "新增",
                    "topics": [
                        {
                            "id": "tp_001",
                            "name": "主题",
                            "change_type": "unchanged",
                            "knowledge_points": [
                                {
                                    "id": "kp_001",
                                    "name": "点",
                                    "knowledge_type": "概念",
                                    "importance": "9",
                                    "difficulty": "高",
                                    "foundational_level": "0",
                                    "teacher_emphasis": "5",
                                    "exam_signal": "强",
                                    "note_coverage": "提及",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        norm = normalize_catalog_enums(catalog)
        ch = norm["chapters"][0]
        kp = ch["topics"][0]["knowledge_points"][0]
        assert ch["change_type"] == "added"
        assert kp["knowledge_type"] == "concept"
        assert kp["importance"] == "5"      # 越界钳制
        assert kp["difficulty"] == "1"
        assert kp["foundational_level"] == "1"
        assert kp["teacher_emphasis"] == "3"
        assert kp["exam_signal"] == "strong"
        assert kp["note_coverage"] == "mentioned"

    def test_合法值保持不变(self):
        catalog = {
            "chapters": [
                {
                    "id": "ch_001",
                    "name": "章",
                    "change_type": "unchanged",
                    "topics": [
                        {
                            "id": "tp_001",
                            "name": "主题",
                            "change_type": "added",
                            "knowledge_points": [
                                {
                                    "id": "kp_001",
                                    "name": "点",
                                    "knowledge_type": "method",
                                    "importance": "3",
                                    "difficulty": "2",
                                    "foundational_level": "4",
                                    "teacher_emphasis": "1",
                                    "exam_signal": "medium",
                                    "note_coverage": "none",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        norm = normalize_catalog_enums(catalog)
        kp = norm["chapters"][0]["topics"][0]["knowledge_points"][0]
        assert kp["knowledge_type"] == "method"
        assert kp["importance"] == "3"
        assert kp["exam_signal"] == "medium"
