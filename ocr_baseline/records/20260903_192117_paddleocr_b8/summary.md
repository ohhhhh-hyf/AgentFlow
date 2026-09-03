# OCR 入库基线记录

- 时间：2026-09-03T19:25:30
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 220.6s；OCR 阶段 36.6s；整理+审校阶段 184.0s；LLM 调用合计 0.0s；入库 3.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 0.0 | 0.0 | 0.0 | 0 | 0 |
| ocr/review | 3 | 3 | 0 | 0.0 | 0.0 | 0.0 | 0 | 0 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 15.3 | 0.0 | 0.0 | rec=1 rev=1 | 58条/0.9387/0.9138 | 100条/0.8911 | 0.482 | 0 |
| 2 | 8 | 12.0 | 0.0 | 0.0 | rec=1 rev=1 | 46条/0.9178/0.8696 | 122条/0.8115 | 0.304 | 0 |
| 3 | 5 | 9.3 | 0.0 | 0.0 | rec=1 rev=1 | 15条/0.9267/0.8667 | 80条/0.8634 | 0.342 | 0 |

## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9583，kept80=0.9496，contiguous=0.2521
- 公式 302 行：avg_char_ratio=0.8872，kept80=0.8609
- 6gram recall：正文 0.40036314117113025，全量 0.13241766580664743

## 公式定界（全稿）

- display 块 119；inline 块 519；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 31004；标题 60 个（分级 {"1": 9, "2": 26, "3": 25}）；表格行 0；**加粗** 处 30

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_192117.md", "added": "90", "removed": "0", "unchanged": "0"}]；知识单元增量=25；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
