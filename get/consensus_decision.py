"""GET 共识决策产物：预览（浏览器渲染）/ 下载 / 打印文本。

页面版 consensus_decision.html；文本为 consensus_decision.md。

用法：
    python get/consensus_decision.py --rid <request_id>            # 预览页面版 html
    python get/consensus_decision.py --rid <request_id> --mode download   # 下载产物文件
    python get/consensus_decision.py --rid <request_id> --mode text       # 打印 md 文本
    python get/consensus_decision.py                              # --rid 缺省自动读取最近响应文件
"""

from _common import main

if __name__ == "__main__":
    main("meeting", "consensus_decision", "共识决策")
