"""GET 知识目录产物：预览（浏览器渲染）/ 下载 / 打印文本。

文本产物为目录树（output/{rid}/result.md）；目录数据 json 在 data/{user}/knowledge/catalogs/{学科}/ 下。

用法：
    python get/catalog.py --rid <request_id>            # 预览页面版 html
    python get/catalog.py --rid <request_id> --mode download   # 下载产物文件
    python get/catalog.py --rid <request_id> --mode text       # 打印 md 文本
    python get/catalog.py                              # --rid 缺省自动读取最近响应文件
"""

from _common import main

if __name__ == "__main__":
    main("notes", "catalog", "知识目录")
