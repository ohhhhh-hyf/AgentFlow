# OCR 入库基线记录

- 时间：2026-09-04T23:36:38
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 81.0s；OCR 阶段 4.6s；整理+审校阶段 79.1s；LLM 调用合计 215.8s；入库 1.8s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 208.8 | 13.0 | 19.5 | 31963 | 17911 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 7.0 | 1.2 | 2.3 | 1670 | 520 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 1.8 | 78.8 | 0.0 | rec=1 rev=0 | 81条/0.9836/0.9877 | 109条/0.9471 | 0.617 | 0 |
| 2 | 8 | 1.5 | 67.8 | 0.0 | rec=1 rev=0 | 68条/0.9826/0.9706 | 134条/0.9351 | 0.531 | 0 |
| 3 | 5 | 1.3 | 62.1 | 0.0 | rec=1 rev=0 | 49条/0.9698/0.9796 | 86条/0.9559 | 0.371 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 21；补回字符 1411


## 全稿保真（对最终合并稿）

- 正文 198 行：avg_char_ratio=0.9905，kept80=0.9949，contiguous=0.5303
- 公式 329 行：avg_char_ratio=0.9601，kept80=0.9696
- 6gram recall：正文 0.5421472937000887，全量 0.39113107287449395

## 公式定界（全稿）

- display 块 98；inline 块 574；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 45117；标题 60 个（分级 {"1": 11, "2": 25, "3": 21, "4": 3}）；表格行 2；**加粗** 处 46

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_233513.md", "added": "122", "removed": "0", "unchanged": "0"}]；知识单元增量=24；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
