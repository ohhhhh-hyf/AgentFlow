# OCR 入库基线记录工具

对知识库「图片 → OCR → LLM 整理审校 → Markdown → 入库」流水线做**可复现基线测量**，
不改动任何生产代码（`tools/ocr/*`、`domain/*` 均只被脚本复用）。

在服务器上用 `paddleocr` 与 `serverocr` 各跑一次，拿到 run.json / summary.md，
之后拿回本地由 ZCode 对比分析（时间、两轮 LLM 开销、md 保真度、公式定界、入库增量）。

## 运行

```bash
# 在服务器仓库根目录执行（python 3.9+，需已装生产依赖）
python ocr_baseline/run_baseline.py --engine paddleocr
python ocr_baseline/run_baseline.py --engine serverocr

# 可选参数
python ocr_baseline/run_baseline.py --engine paddleocr --batch-size 8 --workers 4 \
    --kb-mode fake --label 第一次
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--engine` | .env 的 OCR_ENGINE | paddleocr / serverocr / rapidocr（自动设置环境变量，不用改 .env） |
| `--images` | data/1/docs 下全部 jpg/jpeg/png（自然序） | 显式图片路径列表 |
| `--batch-size` | 8 | 整理批大小（生产默认 8，与 LIGHT_OCR_BATCH 一致） |
| `--workers` | 引擎默认（通常 4） | OCR 并发路数 |
| `--kb-mode` | fake | fake=离线伪向量计数（可复现、不调硅基流动）；real=真实 embedding |
| `--label` | 空 | 备注，追加进输出目录名 |

前置条件：
- LLM：服务器 `.env` 已配置（`LLM_BACKEND` + key），整理/审校与生产完全同源。
- OCR 引擎：`paddleocr` 需模型已下载；`serverocr` 需 `.env` 里 SERVER_OCR_URL 等按生产方式配置。
- KB 计数默认 fake 模式，不需要外网 embedding key；`--kb-mode real` 才需要硅基流动 key。

## 产物

每次运行生成独立目录：

```
ocr_baseline/records/<时间戳>_<引擎>_b<批大小>[_<label>]/
├── run.json              # 规范数据（分析用，字段见下）
├── summary.md            # 人读摘要
├── merged_md 产物         # ocr_<时间戳>.md：最终合并稿（即入库那份）
├── raw_merged.txt         # 全量 OCR 原文合并稿
├── batch_NN_reviewed.md   # 第 N 组整理稿
├── batch_NN_raw.txt       # 第 N 组 OCR 原文
└── kb_chroma/             # isolated 知识库（入库计数用，不影响真实库）
```

## run.json 主要字段

| 字段 | 内容 |
| --- | --- |
| `config` | 引擎 / 图片数 / 批大小 / 批数 / OCR 并发 / LLM provider+model / LLM 可用性 |
| `wall` | 墙钟总时长；OCR 阶段、整理+审校阶段、LLM 调用合计、入库 |
| `events_seen` | 流水线事件计数（ocr_start/item/fail、review_start、batch_done） |
| `per_image` | 每张图：OCR 耗时、行数、平均/最低置信、公式行数、是否失败 |
| `batches[]` | 每批：页数、门控（needs_reconstruct_llm / needs_review_llm）、估算 max_tokens、整理耗时、保真、公式、结构 |
| `batch_stage` | 每批 OCR 阶段耗时 + 批内 LLM 整理/审校耗时（按 label 归因） |
| `llm_by_label` | ocr/reconstruct 与 ocr/review 各自：次数、总/平均/最长耗时、输入/输出 token、失败数 |
| `llm_calls[]` | 逐次调用明细（label / 批号 / 耗时 / token / 是否成功） |
| `whole` | 全稿保真、公式定界、md 结构统计 |
| `ingest` | 入库计数（生产 ingest_library 同款逻辑）：新增块、知识单元增量、items |

## 指标口径（解读前必读）

- **阶段计时**：OCR 阶段 = 各批 `ocr_start → review_start` 之和（含失败/等待）；
  整理+审校阶段 = 每批 `reconstruct_and_review_pages` 执行期；LLM 分账另按 label 独立计时。
- **LLM 统计**：脚本在进程内把 `tools/ocr/engines.get_llm_client` 换成**共享实例**，
  因此 `usage_by_label` / `latency_by_label` 能跨多次调用累计（生产每次新建实例、统计即失，脚本只改本进程行为）。
  失败自动降级（整理→原文、审校→原稿）与生产一致，失败次数单独记录。
- **保真率**（输出 md 相对整理前的 OCR 原文行）：
  - 参考行 = 该批 OCR 行剔除页眉页脚/机构行（boilerplate）；
  - 正文行 / 公式行分开统计；公式行按「含数学符号或引擎 formula 字段」判定；
  - `avg_char_ratio`：该行字符在 md 中出现的占比（宽松、容忍换行合并）；`kept80`：≥0.8 的行占比；`contiguous`：整行连续出现占比（标题被移到行首、行被表格化会降低，属正常整理）；
  - `recall6_text/all`：整稿字符 6-gram 召回（顺序敏感；md 侧的 `#、$、**` 等排版符已剔除，行内/展示公式的 `$` 包裹不参与比对）。
  - **解读优先级：行级指标为主，6-gram 只作参考**——LLM 整理把标题前移、断行合并是预期行为，
    会压低 6-gram 但不应压低 avg_char/kept80。公式行 avg_char 天然偏低（OCR 文本 vs LaTeX 化）。
- **公式定界**：口径与 tools/ocr/mathmd 的归一化一致（display 允许单 `$` 收尾、inline 遇空行视为未闭合）；
  统计的是归一化后仍残余的游离 `$` / `$$$` / `\left` `\right` 失配——理论目标值应接近 0。
- **入库计数**：把最终合并稿当「新入库 md 文件」，在 isolated（独立 persist 目录 + 专用
  user/subject）知识库上跑生产 `ingest_library` 同款逻辑：按标题切块 → 计算知识单元增量。
  空库起步，与生产一致；fake 模式用确定性伪向量，与真实 embedding 在增量计数上等价且可复现。
- 本语料（data/1/docs 的 21 张）为同一份固定输入，跨引擎/跨批大小直接可比。
- LLM 输出并非完全确定（整理 temperature 0.1、审校 0.0）：同配置重复跑会有小抖动，数值看量级。

## 对比方法

把 `paddleocr` 与 `serverocr` 两次运行的 `run.json`（连同 summary.md）放回
`ocr_baseline/records/` 即可；分析时重点看：墙钟与两轮 LLM 时长/token、
正文行 kept80 / avg_char、公式行 avg_char、游离 $ 数、入库知识单元增量。
