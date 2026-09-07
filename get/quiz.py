"""GET 自测题产物：预览（浏览器渲染）/ 下载 / 打印文本。

产物按实际落盘：quiz.html / result.md（取决于本次输入）。

用法：
    python get/quiz.py --rid <request_id>            # 预览页面版 html
    python get/quiz.py --rid <request_id> --mode download   # 下载产物文件
    python get/quiz.py --rid <request_id> --mode text       # 打印 md 文本
    python get/quiz.py                              # --rid 缺省自动读取最近响应文件
"""

from _common import main

if __name__ == "__main__":
    main("notes", "quiz", "自测题")
