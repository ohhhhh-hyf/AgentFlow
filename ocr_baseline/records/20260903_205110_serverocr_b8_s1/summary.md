# OCR 入库基线记录

- 时间：2026-09-03T20:55:27
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 252.3s；OCR 阶段 10.3s；整理+审校阶段 242.0s；LLM 调用合计 240.9s；入库 1.8s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 9 | 9 | 0 | 240.9 | 26.8 | 84.6 | 31912 | 22690 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.9 | 89.5 | 0.0 | rec=1 rev=0 | 81条/0.9349/0.9259 | 109条/0.8907 | 0.496 | 0 |
| 2 | 8 | 7.1 | 80.3 | 0.0 | rec=1 rev=0 | 68条/0.8971/0.8529 | 134条/0.8629 | 0.274 | 0 |
| 3 | 5 | 1.3 | 71.1 | 0.0 | rec=1 rev=0 | 49条/0.875/0.7755 | 86条/0.8641 | 0.226 | 0 |

## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9532，kept80=0.9444，contiguous=0.2424
- 公式 329 行：avg_char_ratio=0.9097，kept80=0.8693
- 6gram recall：正文 0.36438923395445133，全量 0.1624493927125506

## 公式定界（全稿）

- display 块 124；inline 块 724；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 48623；标题 57 个（分级 {"1": 8, "2": 28, "3": 21}）；表格行 0；**加粗** 处 56

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_205110.md", "added": "131", "removed": "0", "unchanged": "0"}]；知识单元增量=24；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
