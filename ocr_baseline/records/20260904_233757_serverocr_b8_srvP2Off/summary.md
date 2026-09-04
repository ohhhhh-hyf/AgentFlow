# OCR 入库基线记录

- 时间：2026-09-04T23:39:22
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 80.0s；OCR 阶段 5.1s；整理+审校阶段 77.9s；LLM 调用合计 207.7s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 199.3 | 12.5 | 19.4 | 31963 | 17779 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 8.4 | 1.4 | 2.6 | 1694 | 677 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.1 | 74.6 | 0.0 | rec=1 rev=0 | 81条/0.982/0.9877 | 109条/0.95 | 0.625 | 0 |
| 2 | 8 | 1.7 | 65.8 | 0.0 | rec=1 rev=0 | 68条/0.9826/0.9706 | 134条/0.9344 | 0.535 | 0 |
| 3 | 5 | 1.3 | 58.9 | 0.0 | rec=1 rev=0 | 49条/0.9698/0.9796 | 86条/0.954 | 0.343 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 22；补回字符 1720


## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9894，kept80=0.9949，contiguous=0.5303
- 公式 329 行：avg_char_ratio=0.9594，kept80=0.9696
- 6gram recall：正文 0.5409642117716652，全量 0.39163714574898784

## 公式定界（全稿）

- display 块 123；inline 块 555；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 45399；标题 60 个（分级 {"1": 11, "2": 26, "3": 18, "4": 5}）；表格行 2；**加粗** 处 36

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_233757.md", "added": "123", "removed": "0", "unchanged": "0"}]；知识单元增量=25；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
