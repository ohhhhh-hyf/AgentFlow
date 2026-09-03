# OCR 入库基线记录

- 时间：2026-09-03T23:25:54
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 249.8s；OCR 阶段 5.2s；整理+审校阶段 244.7s；LLM 调用合计 243.5s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 230.9 | 77.0 | 82.5 | 30135 | 22220 |
| ocr/reconstruct/fix | 8 | 8 | 0 | 12.6 | 1.6 | 4.2 | 2577 | 1279 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.0 | 78.8 | 0.0 | rec=1 rev=0 | 81条/0.9749/0.9753 | 109条/0.9361 | 0.585 | 0 |
| 2 | 8 | 1.9 | 82.5 | 0.0 | rec=1 rev=0 | 68条/0.9766/0.9559 | 134条/0.8907 | 0.507 | 0 |
| 3 | 5 | 1.2 | 69.6 | 0.0 | rec=1 rev=0 | 49条/0.9618/0.9592 | 86条/0.8862 | 0.371 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 46；补回字符 2039


## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9864，kept80=0.9848，contiguous=0.4798
- 公式 329 行：avg_char_ratio=0.9355，kept80=0.9271
- 6gram recall：正文 0.5202602780242532，全量 0.2045167004048583

## 公式定界（全稿）

- display 块 133；inline 块 702；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 50328；标题 62 个（分级 {"1": 16, "2": 27, "3": 19}）；表格行 1；**加粗** 处 49

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_232139.md", "added": "136", "removed": "0", "unchanged": "0"}]；知识单元增量=22；items 示例数=22

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
