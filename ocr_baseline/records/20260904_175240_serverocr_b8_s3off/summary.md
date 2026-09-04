# OCR 入库基线记录

- 时间：2026-09-04T17:54:05
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 80.3s；OCR 阶段 4.7s；整理+审校阶段 78.4s；LLM 调用合计 206.3s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 199.6 | 12.5 | 19.3 | 31963 | 17474 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 6.8 | 1.1 | 2.4 | 1688 | 497 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.9 | 75.9 | 0.0 | rec=1 rev=0 | 81条/0.9763/0.9753 | 109条/0.9489 | 0.61 | 0 |
| 2 | 8 | 1.6 | 65.1 | 0.0 | rec=1 rev=0 | 68条/0.9826/0.9706 | 134条/0.935 | 0.539 | 0 |
| 3 | 5 | 1.2 | 58.6 | 0.0 | rec=1 rev=0 | 49条/0.9698/0.9796 | 86条/0.9528 | 0.343 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 25；补回字符 1411


## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.988，kept80=0.9899，contiguous=0.5202
- 公式 329 行：avg_char_ratio=0.9595，kept80=0.9696
- 6gram recall：正文 0.5365276545400769，全量 0.3903087044534413

## 公式定界（全稿）

- display 块 96；inline 块 572；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 43961；标题 54 个（分级 {"1": 10, "2": 23, "3": 18, "4": 3}）；表格行 2；**加粗** 处 45

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_175240.md", "added": "117", "removed": "0", "unchanged": "0"}]；知识单元增量=21；items 示例数=21

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
