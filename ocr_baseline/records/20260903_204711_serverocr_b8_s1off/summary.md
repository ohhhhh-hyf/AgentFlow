# OCR 入库基线记录

- 时间：2026-09-03T20:51:00
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 224.3s；OCR 阶段 5.2s；整理+审校阶段 219.0s；LLM 调用合计 218.1s；入库 1.8s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 218.1 | 72.7 | 83.7 | 30135 | 20443 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.1 | 83.7 | 0.0 | rec=1 rev=0 | 81条/0.917/0.8765 | 109条/0.8927 | 0.485 | 0 |
| 2 | 8 | 1.8 | 66.6 | 0.0 | rec=1 rev=0 | 68条/0.8747/0.8088 | 134条/0.8443 | 0.257 | 0 |
| 3 | 5 | 1.3 | 67.7 | 0.0 | rec=1 rev=0 | 49条/0.8558/0.7347 | 86条/0.8554 | 0.226 | 0 |

## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9354，kept80=0.9192，contiguous=0.2323
- 公式 329 行：avg_char_ratio=0.8929，kept80=0.8267
- 6gram recall：正文 0.35374149659863946，全量 0.15757844129554655

## 公式定界（全稿）

- display 块 111；inline 块 660；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 44188；标题 53 个（分级 {"1": 8, "2": 28, "3": 17}）；表格行 0；**加粗** 处 47

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_204711.md", "added": "117", "removed": "0", "unchanged": "0"}]；知识单元增量=21；items 示例数=21

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
