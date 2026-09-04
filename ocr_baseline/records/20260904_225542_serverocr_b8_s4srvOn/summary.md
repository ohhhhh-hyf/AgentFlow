# OCR 入库基线记录

- 时间：2026-09-04T22:57:05
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 80.2s；OCR 阶段 4.7s；整理+审校阶段 78.4s；LLM 调用合计 206.6s；入库 1.8s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 199.8 | 12.5 | 19.3 | 27882 | 17467 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 6.8 | 1.1 | 4.6 | 2604 | 581 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.8 | 59.2 | 0.0 | rec=1 rev=0 | 38条/0.9742/0.9737 | 35条/0.9515 | 0.631 | 0 |
| 2 | 8 | 1.6 | 91.4 | 0.0 | rec=1 rev=0 | 31条/0.9714/0.9355 | 50条/0.913 | 0.559 | 0 |
| 3 | 5 | 1.3 | 49.3 | 0.0 | rec=1 rev=0 | 32条/0.9672/0.9375 | 44条/0.9612 | 0.456 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 16；补回字符 1696


## 全稿保真（对最终合并稿）

- 正文 101 行：avg_char_ratio=0.9903，kept80=1.0，contiguous=0.5149
- 公式 129 行：avg_char_ratio=0.9551，kept80=0.9535
- 6gram recall：正文 0.5653021442495126，全量 0.36983977379830346

## 公式定界（全稿）

- display 块 136；inline 块 588；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 42843；标题 66 个（分级 {"1": 9, "2": 23, "3": 34}）；表格行 1；**加粗** 处 51

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_225542.md", "added": "121", "removed": "0", "unchanged": "0"}]；知识单元增量=28；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
