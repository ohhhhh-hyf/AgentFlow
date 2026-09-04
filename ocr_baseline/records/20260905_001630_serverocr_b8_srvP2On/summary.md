# OCR 入库基线记录

- 时间：2026-09-05T00:17:59
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 84.8s；OCR 阶段 5.1s；整理+审校阶段 82.6s；LLM 调用合计 206.3s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 197.5 | 12.3 | 19.1 | 27072 | 17053 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 8.8 | 1.5 | 2.6 | 1937 | 839 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.2 | 43.6 | 0.0 | rec=1 rev=0 | 67条/0.9901/1.0 | 146条/0.9812 | 0.549 | 0 |
| 2 | 8 | 1.6 | 91.2 | 0.0 | rec=1 rev=0 | 74条/0.9823/0.9865 | 111条/0.932 | 0.66 | 0 |
| 3 | 5 | 1.3 | 62.6 | 0.0 | rec=1 rev=0 | 55条/0.972/0.9455 | 72条/0.8459 | 0.509 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 37；补回字符 2184


## 全稿保真（对最终合并稿）

- 正文 196 行：avg_char_ratio=0.9904，kept80=0.9949，contiguous=0.5663
- 公式 329 行：avg_char_ratio=0.9599，kept80=0.9696
- 6gram recall：正文 0.5824404761904762，全量 0.4197757648698296

## 公式定界（全稿）

- display 块 61；inline 块 579；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 43659；标题 57 个（分级 {"1": 8, "2": 25, "3": 21, "4": 3}）；表格行 2；**加粗** 处 44

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260905_001630.md", "added": "124", "removed": "0", "unchanged": "0"}]；知识单元增量=22；items 示例数=22

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
