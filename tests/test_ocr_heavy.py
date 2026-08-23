from __future__ import annotations

from pathlib import Path

from tools.ocr.levels.heavy import apply_heavy_symbol_corrections, generate_heavy_meta, run_heavy_ocr
from tools.ocr.levels.medium import MediumOcrResult


class FakeLlm:
    async def text(self, system, user, **kwargs):
        return """
        ```json
        {
          "catalog_hints": [
            {
              "title": "变量分离法",
              "parent": "一阶微分方程",
              "level": 2,
              "reason": "笔记中作为方法出现",
              "confidence": 0.86
            }
          ],
          "knowledge_points": [
            {
              "id": "kp_001",
              "title": "变量分离法",
              "type": "method",
              "summary": "整理为两边分别积分的形式。",
              "topic": "一阶微分方程",
              "importance": "high",
              "confidence": 0.84
            }
          ],
          "review_items": [
            {
              "id": "ri_001",
              "topic": "变量分离法",
              "question": "变量分离法的核心步骤是什么？",
              "answer": "将变量分离后分别积分。",
              "priority": "high",
              "source_knowledge_id": "kp_001"
            }
          ],
          "relations": [
            {
              "source": "一阶微分方程",
              "target": "变量分离法",
              "type": "contains",
              "reason": "变量分离法是一种解法"
            }
          ],
          "action_items": [
            {
              "task": "补做变量分离法例题",
              "reason": "高优先级方法",
              "priority": "high",
              "related_topic": "变量分离法"
            }
          ]
        }
        ```
        """


def _medium_result(tmp_path: Path) -> MediumOcrResult:
    txt = tmp_path / "raw.txt"
    md = tmp_path / "note_llmv2.md"
    txt.write_text("变量分离法", encoding="utf-8")
    md.write_text("# 一阶微分方程\n\n## 变量分离法\n\n$y'=f(x)g(y)$", encoding="utf-8")
    return MediumOcrResult(
        raw_text=txt.read_text(encoding="utf-8"),
        reviewed_markdown=md.read_text(encoding="utf-8"),
        raw_path=txt,
        reviewed_path=md,
    )


def test_generate_heavy_meta_from_llm(tmp_path):
    image_path = tmp_path / "page.jpg"
    image_path.write_bytes(b"fake")
    meta, reason = generate_heavy_meta(
        image_path,
        user_id="u1",
        subject="math",
        medium_result=_medium_result(tmp_path),
        llm_client=FakeLlm(),
    )

    assert reason == ""
    assert set(meta) == {
        "catalog_hints",
        "knowledge_points",
        "review_items",
        "relations",
        "action_items",
    }
    assert meta["catalog_hints"][0]["title"] == "变量分离法"
    assert meta["knowledge_points"][0]["type"] == "method"
    assert meta["action_items"][0]["priority"] == "high"


def test_apply_heavy_symbol_corrections_is_conservative():
    text = (
        "4(x) = 4(-x)\n"
        "4_t 不应处理，但 4(t) 应处理\n"
        "4_n 和 4_m 是函数符号\n"
        "E=(n+1/2)hw，另有 ħw 与 \\hbar w\n"
        "T=e^{-Ba}，T=e^{-2Ba}\n"
        "普通数字 4、4Ω、第4步、x=4 不应改变"
    )

    fixed = apply_heavy_symbol_corrections(text)

    assert "φ(x) = φ(-x)" in fixed
    assert "4_t" in fixed
    assert "φ(t)" in fixed
    assert "φ_n" in fixed
    assert "φ_m" in fixed
    assert "hω" in fixed
    assert "ħω" in fixed
    assert "\\hbar ω" in fixed
    assert "e^{-βa}" in fixed
    assert "e^{-2βa}" in fixed
    assert "普通数字 4、4Ω、第4步、x=4" in fixed


def test_run_heavy_ocr_saves_meta(tmp_path, monkeypatch):
    image_path = tmp_path / "page.jpg"
    image_path.write_bytes(b"fake")
    medium_result = _medium_result(tmp_path)
    medium_result.reviewed_path.write_text("4(x) 与 hw", encoding="utf-8")
    medium_result = MediumOcrResult(
        raw_text=medium_result.raw_text,
        reviewed_markdown="4(x) 与 hw",
        raw_path=medium_result.raw_path,
        reviewed_path=medium_result.reviewed_path,
    )

    def fake_medium(*args, **kwargs):
        return medium_result

    monkeypatch.setattr("tools.ocr.levels.heavy.run_medium_ocr", fake_medium)

    result = run_heavy_ocr(
        image_path,
        user_id="u1",
        subject="math",
        project_root=tmp_path,
        llm_client=FakeLlm(),
    )

    assert result.raw_path == medium_result.raw_path
    assert result.reviewed_path == medium_result.reviewed_path
    assert result.reviewed_markdown == "φ(x) 与 hω"
    assert result.reviewed_path.read_text(encoding="utf-8") == "φ(x) 与 hω"
    assert result.meta_path.exists()
    assert result.meta_path.parent == tmp_path / "data" / "u1" / "knowledge" / "catalogs"
    assert result.meta_path.name.endswith("_meta.json")
    assert str(result.meta_path) in result.files
