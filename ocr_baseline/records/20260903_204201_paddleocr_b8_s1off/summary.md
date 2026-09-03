# OCR 入库基线记录

- 时间：2026-09-03T20:46:35
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 256.4s；OCR 阶段 35.4s；整理+审校阶段 221.0s；LLM 调用合计 220.1s；入库 1.6s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 3 | 3 | 0 | 200.9 | 67.0 | 95.3 | 24496 | 18309 |
| ocr/review | 3 | 3 | 0 | 19.2 | 6.4 | 17.5 | 8273 | 1582 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 12.7 | 61.4 | 1.5 | rec=1 rev=1 | 58条/0.9384/0.9138 | 100条/0.889 | 0.488 | 0 |
| 2 | 8 | 11.9 | 95.3 | 17.5 | rec=1 rev=1 | 46条/0.9538/0.9565 | 122条/0.8737 | 0.387 | 0 |
| 3 | 5 | 10.8 | 44.2 | 0.3 | rec=1 rev=1 | 15条/0.9267/0.8667 | 80条/0.8587 | 0.317 | 0 |

## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9621，kept80=0.9496，contiguous=0.2605
- 公式 302 行：avg_char_ratio=0.8918，kept80=0.8642
- 6gram recall：正文 0.4339536995006809，全量 0.1469874032478373

## 公式定界（全稿）

- display 块 159；inline 块 603；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 39985；标题 63 个（分级 {"1": 11, "2": 32, "3": 20}）；表格行 0；**加粗** 处 47

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260903_204201.md", "added": "112", "removed": "0", "unchanged": "0"}]；知识单元增量=24；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
