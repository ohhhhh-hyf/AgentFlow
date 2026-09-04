# OCR 入库基线记录

- 时间：2026-09-04T18:03:57
- 引擎：serverocr（env 原值 serverocr）
- 图片：21 张（批 8，共 3 批，OCR 并发 4）
- LLM：vllm / deepseek-v4-flash-0731（可用 True）
- 入库计数库：fake（user ocr_baseline，subject base_serverocr）

## 墙钟

- 总计 76.4s；OCR 阶段 4.9s；整理+审校阶段 74.4s；LLM 调用合计 183.3s；入库 1.7s

## LLM（label 分账）

| label | 次数 | 成功 | 失败 | 总耗时(s) | 平均(s) | 最长(s) | 输入tok | 输出tok |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ocr/reconstruct | 14 | 14 | 0 | 172.5 | 12.3 | 18.4 | 24913 | 15687 |
| ocr/reconstruct/fix | 5 | 5 | 0 | 10.7 | 2.1 | 5.5 | 2643 | 884 |

## 逐批

| 批 | 页 | OCR(s) | LLM整理(s) | LLM审校(s) | 门控 | 正文行avg_char/kept80 | 公式行avg_char | 6gram(text) | 游离$ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 2.0 | 44.8 | 0.0 | rec=1 rev=0 | 32条/0.9807/0.9688 | 37条/0.9584 | 0.553 | 0 |
| 2 | 8 | 1.7 | 77.8 | 0.0 | rec=1 rev=0 | 28条/0.9739/0.9286 | 48条/0.9236 | 0.562 | 0 |
| 3 | 5 | 1.3 | 50.0 | 0.0 | rec=1 rev=0 | 35条/0.9816/0.9714 | 40条/0.9607 | 0.499 | 0 |

## 完整性闭环（Step1 自检事件）

- 批次数 3（gate_off 0）；触发批 3；补写调用 5 次；兜底行 20；补回字符 2203


## 全稿保真（对最终合并稿）

- 正文 95 行：avg_char_ratio=0.9908，kept80=1.0，contiguous=0.6105
- 公式 125 行：avg_char_ratio=0.9571，kept80=0.96
- 6gram recall：正文 0.546907574704656，全量 0.4418225178862809

## 公式定界（全稿）

- display 块 130；inline 块 502；游离 $ 0；$$$ 0；\left/\right 失配 0 处

## 结构（全稿）

- md 字符 41907；标题 51 个（分级 {"1": 9, "2": 20, "3": 22}）；表格行 2；**加粗** 处 45

## 入库（生产同款计数）

- 模式：fake；ok=True
- doc_count=1；新增块=[{"name": "ocr_20260904_180237.md", "added": "110", "removed": "0", "unchanged": "0"}]；知识单元增量=22；items 示例数=22

规范数据见 run.json（per_image / batches / batch_stage / llm_calls / whole / ingest）。
