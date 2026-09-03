# OCR 入库基线记录

- 时间：2026-09-03T19:55:52
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 236.5s；OCR 阶段 34.8s；整理+审校阶段 201.7s；LLM 调用合计 201.0s；入库 1.5s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 165.3 | 55.1 | 57.7 | 24496 | 14893 |
| ocr/review | 3 | 3 | 0 | 35.7 | 11.9 | 18.6 | 8375 | 3048 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 13.2 | 57.7 | 1.5 | rec=1 rev=1 | 58条/0.9393/0.931 | 100条/0.8859 | 0.48 | 0 |
| 2 | 8 | 12.0 | 53.6 | 15.6 | rec=1 rev=1 | 46条/0.9165/0.8696 | 122条/0.8185 | 0.308 | 0 |
| 3 | 5 | 9.7 | 54.0 | 18.6 | rec=1 rev=1 | 15条/0.9236/0.8667 | 80条/0.8616 | 0.348 | 0 |

## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9585，kept80=0.9496，contiguous=0.2605
- 公式 302 行：avg_char_ratio=0.8888，kept80=0.8642
- 6gram recall：正文 0.4008170676350431，全量 0.1329488541508575

## 公式定界（全稿）

- display 块 133；inline 块 484；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 32483；标题 60 个（分级 {"1": 11, "2": 31, "3": 18}）；表格行 0；**加粗** 处 34

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_195138.md", "added": "90", "removed": "0", "unchanged": "0"}]；知识单元增量=24；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
