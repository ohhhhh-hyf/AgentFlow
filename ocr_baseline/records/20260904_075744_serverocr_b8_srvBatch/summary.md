# OCR 入库基线记录

- 时间：2026-09-04T08:02:02
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 252.8s；OCR 阶段 4.9s；整理+审校阶段 250.9s；LLM 调用合计 249.6s；入库 1.8s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 246.5 | 82.2 | 88.1 | 30135 | 22656 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 3.2 | 0.5 | 1.0 | 1729 | 178 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.9 | 88.1 | 0.0 | rec=1 rev=0 | 81条/0.9683/0.963 | 109条/0.9296 | 0.574 | 0 |
| 2 | 8 | 1.7 | 87.6 | 0.0 | rec=1 rev=0 | 68条/0.9739/0.9412 | 134条/0.8861 | 0.51 | 0 |
| 3 | 5 | 1.3 | 70.8 | 0.0 | rec=1 rev=0 | 49条/0.9153/0.8367 | 86条/0.8729 | 0.333 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 40；补回字符 1009


## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9804，kept80=0.9848，contiguous=0.4192
- 公式 329 行：avg_char_ratio=0.9289，kept80=0.921
- 6gram recall：正文 0.5031055900621118，全量 0.19313006072874495

## 公式定界（全稿）

- display 块 120；inline 块 726；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 50412；标题 56 个（分级 {"1": 7, "2": 29, "3": 20}）；表格行 1；**加粗** 处 62

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_075744.md", "added": "138", "removed": "0", "unchanged": "0"}]；知识单元增量=21；items 示例数=21

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
