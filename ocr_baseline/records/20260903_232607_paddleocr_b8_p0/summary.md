# OCR 入库基线记录

- 时间：2026-09-03T23:30:02
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 217.9s；OCR 阶段 34.1s；整理+审校阶段 183.8s；LLM 调用合计 183.0s；入库 1.6s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 168.9 | 56.3 | 60.5 | 24496 | 15684 |
| ocr/reconstruct/fix | 7 | 7 | 0 | 12.2 | 1.7 | 4.2 | 1792 | 1049 |
| ocr/review | 3 | 3 | 0 | 1.9 | 0.6 | 1.4 | 8405 | 96 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 12.1 | 60.5 | 0.2 | rec=1 rev=1 | 58条/0.9412/0.931 | 100条/0.9017 | 0.487 | 0 |
| 2 | 8 | 11.6 | 58.7 | 1.4 | rec=1 rev=1 | 46条/0.974/0.9783 | 122条/0.8812 | 0.465 | 0 |
| 3 | 5 | 10.4 | 49.7 | 0.3 | rec=1 rev=1 | 15条/0.9625/0.9333 | 80条/0.9157 | 0.453 | 1 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 20；补回字符 1953


## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9721，kept80=0.9664，contiguous=0.3025
- 公式 302 行：avg_char_ratio=0.9222，kept80=0.9139
- 6gram recall：正文 0.4834316840671811，全量 0.16193656093489148

## 公式定界（全稿）

- display 块 128；inline 块 585；游离 $ 1；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 35903；标题 67 个（分级 {"1": 10, "2": 31, "3": 26}）；表格行 0；**加粗** 处 35

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_232607.md", "added": "107", "removed": "0", "unchanged": "0"}]；知识单元增量=28；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
