# OCR→Markdown 还原优化路线 · PaddleOCR

> 依据：2026-09-03 r2 基线（`ocr_baseline/records/20260903_195138_paddleocr_b8_r2`，21 张物理笔记照片，批 8，OCR 并发 4，LLM=vLLM deepseek-v4-flash-0731）。本路线只讲 paddleocr 引擎侧该怎么做，三步按"最值得做"排序，每步给出改点、量化预期与验收口径，改完用 ocr_baseline 同一套工具 A/B。

---

## 0. 基线快照（当前起点，所有收益都对照它）

| 指标 | 数值 | 备注 |
| --- | --- | --- |
| 墙钟 | 236.5s | OCR 34.8 + LLM 201.0（reconstruct 165.3 + review 35.7）+ 入库 1.5 |
| LLM token | reconstruct 24,496入/14,893出；review 8,375入/3,048出；合计 50.8k | 生成吞吐 ~90 tok/s/单路 |
| 截断 | **批1、批2 输出顶满 max_tokens（5000）被截断**；批3 自然收尾 | 批2 尾部丢失约 1757 字符原文 |
| 正文保真 | 119 行 avg_char 0.9585 / kept80 0.9496 / contiguous 0.26 | 每行平均丢 ~4% 字符 |
| 公式保真 | 302 行 avg_char 0.8888 | OCR 文本 → LaTeX，天然有损耗 |
| 检出量 | raw 25.5KB / 参考行 430（serverocr 同批为 32.4KB/550，**少 28%**） | 引擎漏检是 paddle 特有短板 |
| 门控 | 3 批全部 rec=1（LLM 整理全开），review=1×3 | 确定性 0-token 路径从未触发 |
| OCR 质量 | 单张 avg 6.4s；页均 conf 0.763；20/21 页存在 <0.7 低置信行 | conf 可用是 paddle 的优势 |
| 入库 | 90 块 / 知识单元增量 24 | 结构干净：0 重复标题、定界错 0 |

**时间=单路 LLM 生成（~90 tok/s × 3 次 55~63s 串行）**；**质量第一大问题=输出被上限截断、每批最后一页尾部丢内容**；paddle 相对 serverocr 的优势=带 conf、行保真高；劣势=检出内容少。

---

## Step 1｜完整性止血：重估输出上限 + 截断/漏行闭环补写

**要解决的问题**：`_estimate_reconstruct_tokens`（tools/ocr/levels/light.py:414-425）按"输入字符/1.2"估输出上限，但实测这批笔记 **md 输出字符 ≈ 输入的 1.9~3.3 倍、约 2.0~2.4 字符/token**（LaTeX 化 + 定界符膨胀），上限被系统性低估 → 5 批里 2 批（批1、批2）顶到 5000 截断，尾部断句/断公式（`md 末尾 "$$\hat{l}_\alpha,\hat{l}_\` 这类残片），批2 丢 1757 字符。截断损失恰好落在每批最后一页——**入库 chunk 尾部内容永久缺失，且 review 补不回来（它只能改稿内已有行）**。

**改法（3 小步，集中在整理层，不碰入库）**：

1. **上限重估**：`max_tokens` 只是保护性上限，放大不会让短输出变贵（模型自然 EOS 就停）。改为
   `est = clamp(round(total_chars * 1.15), 9000, 50000)`（按实测需要的 ≈ 输入×0.9~1.1 再加 15% 安全边际；下限 5000 → 9000，覆盖 5~8 页批的 6~8k 真实需求）。
2. **完整性自检（零 LLM）**：整理稿返回后，程序用行级字符比对（复用 ocr_baseline 的 `line_fidelity` 思路：每行 compact 字符在 md 中出现率 <0.8 即"缺失/受损"）统计缺失行与其原文，**区分两类**：
   - 缺失集中在稿尾 → 截断型；
   - 缺失散布全文 → 漏写型。
3. **闭环补写**：仅当缺失字符占比 >1.5% 或缺失行 ≥3 时，发一次小续写调用（输入 = 本批 lines + 当前稿尾部 200 字符 + 缺失行清单，指令"把缺失内容补在合适位置，不要重复已有内容"，输出上限 2k）。截断型缺失的续写提示要"从断点继续"，漏写型要"按原文补回，禁止臆造"。可选兜底：不调 LLM 时把缺失行原样 append 到稿尾（保内容不丢，格式略糙）。

**为什么省/值**：质量收益最大（每批末页尾部 1.5~1.8KB 内容回到库里）；成本 = 补回内容的 token（completion +8~15%，约 +1.5k×2 批）+ 触发时的一次小续写；时间 +15~20s。它不省时间，是把之前省错的上限花对。

> **实现状态（2026-09-03 两轮已落地，shared 管线双引擎生效）**：
> - `light._estimate_reconstruct_tokens` → `max(9000, min(50000, 输入字符×1.15))`；
> - `reconstruct.ensure_markdown_complete`（接入 `reconstruct_and_review_pages`，review 之前执行）。第一轮（A/B s1）确认闭环有效但触发过频（6/6 批全触发），第二轮收敛为**显式缺失语义**（P0~P4）：
>   - 行"存在"判定 = 与 md 共享任一 8 连字符（对改写/合并/常用字重叠稳健，无语料调参）；公式行、编号短标题行永不参与缺失判定；
>   - 触发只认两类：正文近整行丢失、稿尾截断（缺失延伸到最后一行，或稿尾结构残片信号）；
>   - 补写独立 label `ocr/reconstruct/fix`；片段 $ 定界不平衡自动回退原文兜底；超预算余段一律原文兜底；
>   - 每次自检产出一条事件：run.json 的 `completeness`（按批归并进 `batches[].completeness`），跨语料观察触发率与开销，不做单语料调参；
>   - 第三轮修正（噪声纪律）：恢复前先过"可恢复资格"过滤（页码/机构信息/纯数字符号残渣/乱码指纹，与管线噪声口径一致），补写片段与原文兜底同用；缺失段按 ≤2 行间隔合并；片段合入后复检未覆盖行转入兜底——LLM 主动删除的 OCR 噪声不再被塞回稿子；
> - A/B 开关：`OCR_COMPLETENESS_FIX=0` 关闭闭环；`OCR_CONTINUE_MAX_CALLS`（默认 2）、`OCR_CONTINUE_MAX_TOKENS`（默认 3000）可调。

**预期**：截断=0；kept80 ≥0.965（现 0.9496）；入库增量 ≥26（现 24）；批尾锚点内容残留检测=0。

**风险与回退**：续写可能重复内容 → 续写后跑一遍已有的 `normalize_heading_numbering` + 相邻重复标题清理（document_processor._clean_ocr_markdown 同款规则）；续写失败保持原稿，不算错。

**验收**：跑 `python ocr_baseline/run_baseline.py --engine paddleocr --label s1`，对比 run.json：`llm_by_label` 的 completion_tokens（应 >16.5k）、`whole.fidelity.text.kept80_ratio`、`ingest.increment`；另抽看 batch_01/02_reviewed.md 末尾是否完整成句成公式。建议 run.json 新增"截断/续写事件"计数字段便于回归。

---

## Step 2｜页级并行整理 + 版面特征入批（时间 ↓3~4 倍，顺带根治截断，结构更贴原图）

**要解决的问题**：
- 时间：LLM 201s 占墙钟 85%，是 3 次"8 页一锅 55~63s"的**串行长文重写**；单路 ~90 tok/s 是硬约束，唯一的墙钟杠杆是并发。
- 质量：8 页超长上下文，页尾注意力衰减 + 上限截断双亏（Step 1 只是止血）；整理单位过大使页级门控与确定性路径（干净页零 token）无从生效——标题双轨（locked/ambiguous）虽有版面推断支撑（经 adapter→layout 已生效，早期"批路径未接版面"的判断有误），但门控与门控阈值作用在整批混合行上，单页质量无法单独判断。

**改法（3 小步）**：

1. **处理单元从"8 页一批"改成"1~2 页一批"**：`iter_ocr_review_pipeline` 的批内 review 改为页级分派，每页一个短整理调用（prompt ~1.2~1.5k、输出 ~1k，远离上限 → 截断消失），4~6 路并发（复用现有线程池模型；paddle 引擎实例池与整理并发互不冲突——OCR 线程与 LLM 线程分开）。跨页连续性：每页 prompt 附上一页最后一个标题行（防新页首标题层级漂移），页输出按序拼接，最后跑全局 `normalize_heading_numbering` 归并同族标题。
2. **OCR 后、整理前逐页补版面推断**：把 `layout._infer_layout_hints`（tools/ocr/layout.py:113，已实现、零成本）挂到页行上 → LLM 输入里带 locked_heading/locked_body/ambiguous + heading_score，标题层级按版面而非纯文本猜；boilerplate（页眉页脚/印刷厂行）在进 LLM 前剔除，少喂噪声。
3. **页级门控复活确定性路径**：版面推断 + paddle 已有 conf 后，`_needs_reconstruct_llm` 对"平均 conf≥0.9 且无低置信行且标题已锁定"的页返回 False → 走 `deterministic_reconstruct_markdown`（0 token）。打印清晰的页能省整次 LLM；以数据为准，不达标不强求。

> **实现状态（2026-09-03 已落地，shared 管线双引擎自动生效；paddle 先验收）**：
> - `reconstruct_and_review_pages` 默认走页级整理（`OCR_PAGE_RECONSTRUCT=0` 回退整批一次长文重写做 A/B）：每页独立门控，需 LLM 的页并发短整理（`OCR_RECONSTRUCT_WORKERS`，默认 4），干净页确定性零 token；跨页只传上一页末尾 locked 标题（`reconstruct_markdown(context=…)`）防层级漂移；按页序合并后仍按批做完整性闭环与审校（事件 1:1 不破坏基线观测）；
> - 版面推断确认已通过 adapter→layout 在批路径生效（早期文档判断有误，已更正），页级化后按页自然参与门控；
> - 已知观测口径（已修）：页级并发下逐调用 token 差分会交叠失真——基线已改为 token 一律取客户端快照 `usage_by_label`（锁内累计，并发安全），`llm_calls` 只记耗时；`llm_by_label.seconds` 是各调用耗时之和（并发下可大于墙钟，墙钟以 `wall.review_seconds` 为准）；A/B 环境开关用 `--set-env OCR_PAGE_RECONSTRUCT=0`（shell 无关，且记入 run.json config.env_overrides）。

**为什么省/值**：
- 时间：LLM 201s → 每页生成 3~6s×并发 4~6 路 ≈ 35~60s（vLLM 连续批处理下并发吞吐通常显著高于单路 90 tok/s；若服务端排队导致退化，保守也 ≤90s）。OCR 34.8s 不变。
- token：completion 补全截断后 ≈ 17~19k（持平略升，内容完整了）；prompt 因系统头按页重复会上涨（21×~1k vs 3×~9k，约 +15k）——**先查 vLLM 是否开 prefix caching**（r2 里 cache_hit_tokens=0，疑似没开）；没开就压缩 RECONSTRUCT_SYSTEM_PROMPT（11 条规则压成 ~5 条要点）或折中 2 页/批。
- 质量：页尾注意力不衰减 → 目标 kept80 ≥0.97、contiguous 上升；标题层级更贴原图 → 入库 heading_kind/chapter/topic 更准。

**风险与回退**：并发打满 vLLM 时单请求变慢 → 用 `OCR_PARALLEL` 风格环境变量做并发数开关，先 2 路实测吞吐再调；跨页重复标题 → 已有归并函数兜底。

**验收**：同 Step 1 跑法，对比 `wall.review_seconds`（目标 <90s）、`llm_by_label.ocr/reconstruct` 的 calls（应 >3，批数=页批数）、`whole.fidelity`、标题数/层级分布稳定性（与现 60 标题量级一致即可，不追求相等）。

---

## Step 3｜保真闸门 + review 精修 + paddle 检出量补强（质量天花板）

**要解决的问题**：现状每行平均丢 4% 字符（kept80 0.95），少量整行丢失混在其中（review 补不了）；review 轮 35.7s/11.4k token 是否值回票价没验证过；paddle 检出内容比 serverocr 少 28%（参考行 430 vs 550）是最伤"贴近图片笔记"的引擎级短板。

**改法（3 小步）**：

1. **保真闸门升级为留痕机制**：Step 1 的自检结果（每批缺失行数/字数/位置 首·中·尾）写进 run.json 与日志，让"漏了什么"可见可回归；闸门只补 Step 1 兜不住的漏写型缺失。
2. **review A/B 实验**：关掉 review（`_needs_review` 恒 False）跑一轮对照，对比 kept80/公式 avg/入库增量。若差异 <0.005 则把 review 触发条件收紧为"公式行 >20 或低置信行 >5 且 evidence 窗口能定位"，预期省 ~10k prompt token + ~30s；若差异明显则保留现窗口机制，只做 Step 1 的"先补全再审校"顺序修正。
3. **检出量补强（paddle 特有）**：先用 r2 的 `per_image` 定位低行数页，与 serverocr 同页差集分析漏检形态（整段漏 vs 边缘漏）；按结论二选一或组合：
   - OCR 输入预处理：拍照图先放大到长边 ≥2000px / 轻度锐化再送 paddle（PP-OCRv5 对低分辨率小字漏检明显）；
   - 仲裁式补检：对 paddle 行数异常低的页，用 serverocr 补识别一次并 diff 合并（paddle 行保真高当主源，serverocr 当补源）——成本只在少数页发生。

**为什么省/值**：前两小步是 token/时间精修（净省 8~11k token）；检出量补强直接提升"还原度"与入库单元数，是 paddle 追平 serverocr 内容完整性的唯一路径。

**预期（三步合起来的总目标）**：墙钟 236.5s → 70~100s；LLM token 50.8k → 40~48k（内容更完整前提下）；kept80 ≥0.97、截断 0；raw 检出量 +20%+；入库增量 ≥28。

**验收**：最终以 `--label s3` 跑一轮，与 `20260903_195138_paddleocr_b8_r2` 逐字段对比 run.json（wall / llm_by_label / whole.fidelity / ingest.increment / batches[].fidelity），并把两份 merged md 抽 3 处同一页内容人工核对"更贴近原图"。

---

## 通用建议（对 paddle 同样适用）

- 服务器 vLLM 确认是否开 `--enable-prefix-caching`（r2 cache_hit_tokens=0）；开启后系统 prompt 重复成本大幅下降，是 Step 2 页级化的前提之一。
- 固定 A/B 口径：同一语料 21 张、`--engine paddleocr --batch-size 8`、加 `--label`；对比字段固定取 run.json 的 `wall.*`、`llm_by_label.*`、`whole.fidelity.*`、`ingest.increment`、`batches[].fidelity`。
- 暂不做：视觉大模型直读（成本/部署另议）、换 OCR 引擎、优化 OCR 并发（占时仅 15%）。
