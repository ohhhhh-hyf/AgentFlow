"""测试 demo/api_test/ 批处理脚本功能 (Excel 读写、模板解析、首字时延提取与回写)."""
import sys
from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

from openpyxl import Workbook, load_workbook
from api_test.test_stream import make_template_resolver, save_workbook


def test_api_test_template_resolver():
    """测试 api_test 模板解析器."""
    resolve, suggest = make_template_resolver()

    # 1. 有效英文 ID
    assert resolve("general_minutes") is True
    assert resolve("general_minutes.md") is True
    assert resolve("team_meeting") is True
    assert resolve("project_progress") is True

    # 2. 中文常见词
    assert resolve("通用纪要") is True
    assert resolve("常规纪要") is True

    # 3. 自动模式
    assert resolve("") is True
    assert resolve("auto") is True

    # 4. 推荐
    assert suggest("general") == "general_minutes"


def test_api_test_excel_roundtrip(tmp_path: Path):
    """测试创建 Excel、模拟写入纪要与时延回盘."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # 表头
    ws.append(["文本", "场景", "纪要", "消耗时间", "文本长度", "首字时延"])
    # 待处理行
    ws.append(["张总：今天例会推进小艺语音项目。", "general_minutes", "", "", "", ""])

    excel_file = tmp_path / "test_run.xlsx"
    wb.save(excel_file)
    assert excel_file.is_file()

    # 读取并修改模拟结果
    wb_load = load_workbook(excel_file)
    ws_load = wb_load.active
    assert ws_load.cell(row=2, column=1).value == "张总：今天例会推进小艺语音项目。"

    # 写入模拟输出
    ws_load.cell(row=2, column=3, value="# 全文摘要\n会议顺利召开。")
    ws_load.cell(row=2, column=4, value=2.35)
    ws_load.cell(row=2, column=5, value="18/25")
    ws_load.cell(row=2, column=6, value=0.88)
    save_workbook(wb_load, excel_file)

    # 重新加载断言
    wb_verify = load_workbook(excel_file)
    ws_verify = wb_verify.active
    assert "# 全文摘要" in ws_verify.cell(row=2, column=3).value
    assert ws_verify.cell(row=2, column=4).value == 2.35
    assert ws_verify.cell(row=2, column=6).value == 0.88
