import sys
from pathlib import Path
root = Path(r"D:\study\AgentFlow")
sys.path.insert(0, str(root))

from domain.notes.tasks.catalog.gather import build_catalog_briefing

shared_ctx = """
【用户ID】1
【学科/课程】物理
"""

briefing = build_catalog_briefing(shared_ctx)
print("=== BRIEFING PREVIEW ===")
print(briefing[:1500])
