"""GET 知识图谱产物：预览（浏览器渲染）/ 下载 / 打印文本。

交互页面版 graph.html（Cytoscape 自包含）。

用法：
    python get/graph.py --rid <request_id>            # 预览页面版 html
    python get/graph.py --rid <request_id> --mode download   # 下载产物文件
    python get/graph.py --rid <request_id> --mode text       # 打印 md 文本
    python get/graph.py                              # --rid 缺省自动读取最近响应文件
"""

from _common import main

if __name__ == "__main__":
    main("notes", "graph", "知识图谱")
