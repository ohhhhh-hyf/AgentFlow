# OCR 入库基线记录

- 时间：2026-09-03T19:50:43
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 179.0s；OCR 阶段 5.4s；整理+审校阶段 173.6s；LLM 调用合计 172.8s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 172.8 | 57.6 | 62.6 | 30135 | 16104 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.8 | 57.4 | 0.0 | rec=1 rev=0 | 81条/0.9101/0.8519 | 109条/0.8853 | 0.457 | 0 |
| 2 | 8 | 1.7 | 62.6 | 0.0 | rec=1 rev=0 | 68条/0.8445/0.7794 | 134条/0.8118 | 0.238 | 0 |
| 3 | 5 | 1.9 | 52.7 | 0.0 | rec=1 rev=0 | 49条/0.8541/0.7347 | 86条/0.8533 | 0.219 | 0 |

## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9222，kept80=0.899，contiguous=0.197
- 公式 329 行：avg_char_ratio=0.889，kept80=0.8237
- 6gram recall：正文 0.33244602188701566，全量 0.13746204453441296

## 公式定界（全稿）

- display 块 125；inline 块 527；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 35473；标题 54 个（分级 {"1": 14, "2": 28, "3": 12}）；表格行 0；**加粗** 处 34

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_194740.md", "added": "97", "removed": "0", "unchanged": "0"}]；知识单元增量=20；items 示例数=20

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
