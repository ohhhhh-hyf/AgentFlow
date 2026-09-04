# OCR 入库基线记录

- 时间：2026-09-04T07:51:58
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 144.8s；OCR 阶段 8.5s；整理+审校阶段 142.9s；LLM 调用合计 286.3s；入库 1.8s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 280.5 | 17.5 | 82.3 | 31963 | 26140 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 5.8 | 1.0 | 1.5 | 1816 | 490 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.9 | 148.6 | 0.0 | rec=1 rev=0 | 81条/0.9757/0.9753 | 109条/0.9483 | 0.64 | 0 |
| 2 | 8 | 5.4 | 67.7 | 0.0 | rec=1 rev=0 | 68条/0.981/0.9706 | 134条/0.9342 | 0.559 | 0 |
| 3 | 5 | 1.3 | 64.3 | 0.0 | rec=1 rev=0 | 49条/0.9698/0.9796 | 86条/0.9538 | 0.375 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 31；补回字符 1507


## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9874，kept80=0.9899，contiguous=0.5505
- 公式 329 行：avg_char_ratio=0.9593，kept80=0.9696
- 6gram recall：正文 0.5625554569653949，全量 0.39878542510121456

## 公式定界（全稿）

- display 块 94；inline 块 550；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 60622；标题 57 个（分级 {"1": 13, "2": 24, "3": 17, "4": 3}）；表格行 2；**加粗** 处 41

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_074927.md", "added": "152", "removed": "0", "unchanged": "0"}]；知识单元增量=18；items 示例数=18

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
