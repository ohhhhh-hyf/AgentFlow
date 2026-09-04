# OCR 入库基线记录

- 时间：2026-09-04T18:07:34
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 166.7s；OCR 阶段 34.7s；整理+审校阶段 153.7s；LLM 调用合计 284.3s；入库 1.6s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 18 | 18 | 0 | 258.1 | 14.3 | 85.7 | 23902 | 23268 |
| ocr/reconstruct/fix | 2 | 2 | 0 | 0.6 | 0.3 | 0.4 | 887 | 34 |
| ocr/review | 3 | 3 | 0 | 25.6 | 8.5 | 17.6 | 15804 | 2016 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 13.0 | 46.9 | 2.2 | rec=1 rev=1 | 19条/0.9868/1.0 | 42条/0.9413 | 0.562 | 0 |
| 2 | 8 | 12.0 | 80.6 | 17.6 | rec=1 rev=1 | 10条/0.9348/0.9 | 56条/0.9149 | 0.289 | 0 |
| 3 | 5 | 9.7 | 130.6 | 5.9 | rec=1 rev=1 | 7条/0.9072/0.8571 | 51条/0.863 | 0.26 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 2；补写调用 2 次；兜底行 0；补回字符 16


## 全稿保真（对最终合并稿）

- 正文 36 行：avg_char_ratio=0.9812，kept80=0.9722，contiguous=0.25
- 公式 149 行：avg_char_ratio=0.9349，kept80=0.9396
- 6gram recall：正文 0.44011976047904194，全量 0.28134277232244803

## 公式定界（全稿）

- display 块 272；inline 块 458；游离 $ 0；$$$ 2；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 55101；标题 52 个（分级 {"1": 2, "2": 24, "3": 23, "4": 3}）；表格行 0；**加粗** 处 52

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_180431.md", "added": "151", "removed": "0", "unchanged": "0"}]；知识单元增量=20；items 示例数=20

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
