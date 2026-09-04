# OCR 入库基线记录

- 时间：2026-09-04T22:54:59
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 101.1s；OCR 阶段 34.7s；整理+审校阶段 88.3s；LLM 调用合计 221.8s；入库 1.6s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 19 | 19 | 0 | 198.3 | 10.4 | 16.4 | 25291 | 16966 |
| ocr/review | 3 | 3 | 0 | 23.2 | 7.7 | 15.3 | 15557 | 1726 |
| ocr/reconstruct/fix | 1 | 1 | 0 | 0.3 | 0.3 | 0.3 | 352 | 11 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 12.8 | 54.0 | 0.5 | rec=1 rev=1 | 22条/0.9604/0.9545 | 42条/0.9341 | 0.525 | 0 |
| 2 | 8 | 11.5 | 86.7 | 7.4 | rec=1 rev=1 | 11条/0.9752/1.0 | 56条/0.9183 | 0.462 | 0 |
| 3 | 5 | 10.4 | 57.6 | 15.3 | rec=1 rev=1 | 7条/0.9072/0.8571 | 51条/0.8516 | 0.26 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 1；补写调用 1 次；兜底行 0；补回字符 18


## 全稿保真（对最终合并稿）

- 正文 40 行：avg_char_ratio=0.9801，kept80=0.975，contiguous=0.25
- 公式 149 行：avg_char_ratio=0.9258，kept80=0.9262
- 6gram recall：正文 0.4703448275862069，全量 0.26513886780998636

## 公式定界（全稿）

- display 块 140；inline 块 474；游离 $ 0；$$$ 2；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 37283；标题 57 个（分级 {"1": 5, "2": 24, "3": 28}）；表格行 5；**加粗** 处 44

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_225302.md", "added": "102", "removed": "0", "unchanged": "0"}]；知识单元增量=25；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
