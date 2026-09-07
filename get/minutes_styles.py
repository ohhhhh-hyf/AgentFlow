"""GET 多样式纪要产物：预览（浏览器渲染）/ 下载 / 打印文本。

页面版 minutes_styles.html；文本为 minutes_styles.md。

用法：
    python get/minutes_styles.py --rid <request_id>            # 预览页面版 html
    python get/minutes_styles.py --rid <request_id> --mode download   # 下载产物文件
    python get/minutes_styles.py --rid <request_id> --mode text       # 打印 md 文本
    python get/minutes_styles.py                              # --rid 缺省自动读取最近响应文件
"""

from _common import main

if __name__ == "__main__":
    main("meeting", "minutes_styles", "多样式纪要")
