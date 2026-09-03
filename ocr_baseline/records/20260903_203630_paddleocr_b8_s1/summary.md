# OCR 入库基线记录

- 时间：2026-09-03T20:41:25
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 278.1s；OCR 阶段 34.0s；整理+审校阶段 244.1s；LLM 调用合计 243.1s；入库 1.6s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 9 | 9 | 0 | 224.0 | 24.9 | 96.0 | 26829 | 20384 |
| ocr/review | 3 | 3 | 0 | 19.1 | 6.4 | 17.1 | 8401 | 1599 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 12.9 | 69.1 | 1.8 | rec=1 rev=1 | 58条/0.9567/0.9483 | 100条/0.8896 | 0.519 | 0 |
| 2 | 8 | 11.6 | 99.4 | 17.1 | rec=1 rev=1 | 46条/0.9538/0.9565 | 122条/0.8742 | 0.383 | 0 |
| 3 | 5 | 9.5 | 55.5 | 0.2 | rec=1 rev=1 | 15条/0.9474/0.9333 | 80条/0.8671 | 0.342 | 0 |

## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9674，kept80=0.958，contiguous=0.3109
- 公式 302 行：avg_char_ratio=0.8935，kept80=0.8642
- 6gram recall：正文 0.4507489786654562，全量 0.1526787069358021

## 公式定界（全稿）

- display 块 147；inline 块 682；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 43762；标题 61 个（分级 {"1": 10, "2": 33, "3": 18}）；表格行 0；**加粗** 处 45

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_203630.md", "added": "119", "removed": "0", "unchanged": "0"}]；知识单元增量=22；items 示例数=22

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
