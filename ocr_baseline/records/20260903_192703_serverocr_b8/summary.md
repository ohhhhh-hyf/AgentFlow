# OCR 入库基线记录

- 时间：2026-09-03T19:30:20
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 192.9s；OCR 阶段 13.9s；整理+审校阶段 179.0s；LLM 调用合计 0.0s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 0.0 | 0.0 | 0.0 | 0 | 0 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 6.2 | 0.0 | 0.0 | rec=1 rev=0 | 81条/0.9069/0.8519 | 109条/0.8818 | 0.463 | 0 |
| 2 | 8 | 6.5 | 0.0 | 0.0 | rec=1 rev=0 | 68条/0.8398/0.7206 | 134条/0.8072 | 0.252 | 0 |
| 3 | 5 | 1.3 | 0.0 | 0.0 | rec=1 rev=0 | 49条/0.8451/0.7347 | 86条/0.8429 | 0.223 | 0 |

## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9296，kept80=0.904，contiguous=0.2071
- 公式 329 行：avg_char_ratio=0.8872，kept80=0.8237
- 6gram recall：正文 0.34102336586808635，全量 0.1404352226720648

## 公式定界（全稿）

- display 块 125；inline 块 511；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 36358；标题 55 个（分级 {"1": 11, "2": 26, "3": 17, "4": 1}）；表格行 0；**加粗** 处 48

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_192703.md", "added": "101", "removed": "0", "unchanged": "0"}]；知识单元增量=21；items 示例数=21

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
