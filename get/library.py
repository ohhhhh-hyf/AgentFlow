"""GET 资料入库产物：占位说明。

library 不产生产物文件（入库结果文本与统计只在 POST 响应 data.text 中返回），
因此没有可下载/预览的 GET 产物——保留本文件仅为保持"每个接口一个脚本"的完整。
"""
from __future__ import annotations

if __name__ == "__main__":
    print("library 无落盘产物文件：请直接查看 POST /api/v1/notes/library 的响应 data.text。")
