# OCR 入库基线记录

- 时间：2026-09-05T00:04:00
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 92.9s；OCR 阶段 37.0s；整理+审校阶段 78.4s；LLM 调用合计 215.6s；入库 1.5s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 21 | 21 | 0 | 204.2 | 9.7 | 14.5 | 29982 | 17526 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 8.4 | 1.4 | 4.8 | 2424 | 761 |
| ocr/review | 3 | 3 | 0 | 3.0 | 1.0 | 2.1 | 8886 | 168 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 14.5 | 83.6 | 0.4 | rec=1 rev=1 | 24条/0.9878/1.0 | 133条/0.9324 | 0.382 | 0 |
| 2 | 8 | 12.5 | 64.1 | 0.5 | rec=1 rev=1 | 58条/0.9666/0.9483 | 98条/0.9256 | 0.607 | 0 |
| 3 | 5 | 10.0 | 56.5 | 2.1 | rec=1 rev=1 | 37条/0.9428/0.9189 | 71条/0.8834 | 0.385 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 22；补回字符 1385


## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9818，kept80=0.9748，contiguous=0.437
- 公式 302 行：avg_char_ratio=0.9381，kept80=0.947
- 6gram recall：正文 0.49659555152065366，全量 0.21179238124146305

## 公式定界（全稿）

- display 块 103；inline 块 693；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 38351；标题 63 个（分级 {"1": 7, "2": 33, "3": 23}）；表格行 0；**加粗** 处 59

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260905_000210.md", "added": "108", "removed": "0", "unchanged": "0"}]；知识单元增量=26；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
