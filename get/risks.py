"""GET 风险分析产物：预览（浏览器渲染）/ 下载 / 打印文本。

页面版 risks.html；文本为 risks.md。

用法：
    python get/risks.py --rid <request_id>            # 预览页面版 html
    python get/risks.py --rid <request_id> --mode download   # 下载产物文件
    python get/risks.py --rid <request_id> --mode text       # 打印 md 文本
    python get/risks.py                              # --rid 缺省自动读取最近响应文件
"""

from _common import main

if __name__ == "__main__":
    main("meeting", "risks", "风险分析")
