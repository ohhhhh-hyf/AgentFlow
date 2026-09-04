# OCR 入库基线记录

- 时间：2026-09-05T00:20:06
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 81.8s；OCR 阶段 12.0s；整理+审校阶段 79.7s；LLM 调用合计 208.4s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 16 | 16 | 0 | 198.9 | 12.4 | 18.4 | 28918 | 17110 |
| ocr/reconstruct/fix | 6 | 6 | 0 | 9.6 | 1.6 | 3.4 | 1968 | 808 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.1 | 44.6 | 0.0 | rec=1 rev=0 | 67条/0.9905/1.0 | 146条/0.9811 | 0.536 | 0 |
| 2 | 8 | 8.6 | 88.7 | 0.0 | rec=1 rev=0 | 74条/0.9777/0.973 | 111条/0.9203 | 0.663 | 0 |
| 3 | 5 | 1.3 | 65.6 | 0.0 | rec=1 rev=0 | 55条/0.9585/0.9273 | 72条/0.8477 | 0.492 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 6 次；兜底行 24；补回字符 1910


## 全稿保真（对最终合并稿）

- 正文 196 行：avg_char_ratio=0.9884，kept80=0.9898，contiguous=0.5561
- 公式 329 行：avg_char_ratio=0.9614，kept80=0.9726
- 6gram recall：正文 0.5738095238095238，全量 0.40824729207575855

## 公式定界（全稿）

- display 块 72；inline 块 577；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 43424；标题 54 个（分级 {"1": 9, "2": 23, "3": 19, "4": 3}）；表格行 2；**加粗** 处 49

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260905_001839.md", "added": "118", "removed": "0", "unchanged": "0"}]；知识单元增量=19；items 示例数=19

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
