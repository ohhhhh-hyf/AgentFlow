# OCR 入库基线记录

- 时间：2026-09-04T07:08:14
- 引擎：paddleocr（env 原值 paddleocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_paddleocr）

## 墙钟

- 总计 110.0s；OCR 阶段 34.5s；整理+审校阶段 75.5s；LLM 调用合计 219.6s；入库 1.6s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 21 | 21 | 0 | 215.6 | 10.3 | 16.2 | 34913 | 18465 |
| ocr/reconstruct/fix | 5 | 5 | 0 | 4.0 | 0.8 | 1.5 | 1413 | 332 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 12.6 | 67.2 | 0.0 | rec=1 rev=1 | 58条/0.9795/0.9828 | 100条/0.9104 | 0.578 | 0 |
| 2 | 8 | 12.0 | 88.4 | 0.0 | rec=1 rev=1 | 46条/0.9785/1.0 | 122条/0.8932 | 0.457 | 0 |
| 3 | 5 | 9.8 | 60.0 | 0.0 | rec=1 rev=1 | 15条/0.9278/0.8667 | 80条/0.8703 | 0.342 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 5 次；兜底行 13；补回字符 866


## 全稿保真（对最终合并稿）

- 正文 119 行：avg_char_ratio=0.9827，kept80=0.9832，contiguous=0.3866
- 公式 302 行：avg_char_ratio=0.9129，kept80=0.9073
- 6gram recall：正文 0.5111211983658648，全量 0.16823493701623918

## 公式定界（全稿）

- display 块 169；inline 块 613；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 40744；标题 76 个（分级 {"1": 2, "2": 25, "3": 35, "4": 14}）；表格行 0；**加粗** 处 52

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_070607.md", "added": "120", "removed": "0", "unchanged": "0"}]；知识单元增量=33；items 示例数=24

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
