# OCR→Markdown 还原优化路线 · ServerOCR

> 依据：2026-09-03 r2 基线（`ocr_baseline/records/20260903_194740_serverocr_b8_r2`，21 张物理笔记照片，批 8，OCR 并发 4，LLM=vLLM deepseek-v4-flash-0731）。本路线只讲 serverocr（远程 OCR 服务）侧该怎么做，三步按"最值得做"排序，每步给出改点、量化预期与验收口径，改完用 ocr_baseline 同一套工具 A/B。

---

## 0. 基线快照（当前起点，所有收益都对照它）

| 指标 | 数值 | 备注 |
| --- | --- | --- |
| 墙钟 | 179.0s | OCR 5.4 + LLM 172.8（reconstruct 165.3 + review 0）+ 入库 1.7 |
| LLM token | reconstruct 30,135入/16,104出；合计 46.2k | 无 review（见下）；生成吞吐 ~93 tok/s/单路 |
| 截断 | **3/3 批全部顶满 max_tokens（5149/5955/5000）被截断** | 批1 尾部丢 1591 字符原文；批2/批3 断在半条 LaTeX 公式里 |
| 正文保真 | 198 行 avg_char 0.9222 / kept80 0.8990 / contiguous 0.197 | 行碎（198 vs paddle 119） |
| 公式保真 | 329 行 avg_char 0.8890 | 服务返回公式行较多 |
| 检出量 | raw 32.4KB / 参考行 550（paddle 同批 25.5KB/430，**多 28%**） | 内容是 serverocr 的强项 |
| 门控 | 3 批全部 rec=1；**review=0×3（永不触发）** | 无 conf 连锁反应 |
| conf | **21/21 页 avg_conf=None** | server_ocr.py 支持 confidence/score/prob 字段，服务端响应未返回 |
| OCR 速度 | 单张 avg 1.7s（远程服务） | 快，非瓶颈 |
| 入库 | 97 块 / 知识单元增量 20 | 结构干净：0 重复标题、定界错 0 |

**时间=单路 LLM 生成（172.8s，占墙钟 96%）**；**质量两大问题：① 3/3 批被上限截断、末页尾部丢内容且无 review 兜底；② 引擎不带 conf → 整条"质量信号"链（低置信谨慎纠错、review 门控、确定性快路径、页眉剔除）全部空转，且行碎让每行保真统计吃亏**。serverocr 的优势是内容全 + OCR 快。

---

## Step 1｜完整性止血：重估输出上限 + 截断/漏行闭环补写

**要解决的问题**：与 paddle 同源，但 serverocr 更严重——3/3 批截断（prompt 行多 → 需要的输出更多，5~6k 上限更不够用；实测 md 输出字符 ≈ 输入的 1.9~3.3 倍、约 2.0~2.4 字符/token）。截断证据：批1 md 断句"用矩阵理解是转置后取共"，raw 里还有 1591 字符；批2 断在 `$$N_{lm} =`、批3 断在 `\left[-\frac{\hbar^2}{2m}\frac{`。**且 serverocr 无 review 轮，截断内容没有任何第二道机制能救回。**

**改法（与 paddle Step 1 同构，3 小步）**：

1. **上限重估**：`_estimate_reconstruct_tokens`（tools/ocr/levels/light.py:414-425）改为
   `est = clamp(round(total_chars * 1.15), 9000, 50000)`。max_tokens 只是保护性上限，放大不会让短输出变贵。
2. **完整性自检（零 LLM）**：整理稿返回后逐行比对 OCR 行 vs md（字符出现率 <0.8 即缺失/受损），按"缺失集中在稿尾=截断型 / 散布全文=漏写型"分类。
3. **闭环补写**：缺失字符占比 >1.5% 或缺失行 ≥3 时发一次小续写（输入 = 本批 lines + 稿尾 200 字符 + 缺失行清单，输出上限 2k）；截断型提示"从断点继续"，漏写型提示"按原文补回、禁止臆造"。兜底：无 LLM 时缺失行原样 append。

**为什么省/值**：质量收益最大（3 个批尾各 1.5KB+ 内容回到库里）；成本 = 补回内容的 completion（+10~15%，约 +2k）+ 触发时的一次小续写；时间 +15~20s。

> **实现状态（2026-09-03 两轮已落地，与 paddle 共用同一段管线代码，serverocr 自动生效）**：
> - 上限重估 + `ensure_markdown_complete` 闭环已接入 `reconstruct_and_review_pages`；
> - 第二轮收敛为显式缺失语义（P0~P4）：行"存在"判定 = 与 md 共享任一 8 连字符；
>   公式行/编号标题行不参与缺失判定；触发只认近整行丢失与稿尾截断（含结构残片信号）；
>   补写独立 label `ocr/reconstruct/fix`，定界不平衡/超预算一律原文兜底；
> - 自检事件进 run.json 的 `completeness`（按批归并），跨语料观察触发率；
> - A/B 开关：`OCR_COMPLETENESS_FIX=0` 关闭；`OCR_CONTINUE_MAX_CALLS` / `OCR_CONTINUE_MAX_TOKENS` 可调。

**预期**：截断=0；kept80 ≥0.92（现 0.899）；入库增量 ≥22（现 20）。

**风险与回退**：续写重复 → 续写后跑 `normalize_heading_numbering` + 相邻重复标题清理；续写失败保持原稿。

**验收**：`python ocr_baseline/run_baseline.py --engine serverocr --label s1`，对比 run.json：completion_tokens（应 >17.5k）、`whole.fidelity.text.kept80_ratio`、`ingest.increment`；抽看 batch_01/02/03_reviewed.md 末尾完整成句成公式。建议 run.json 增加"截断/续写事件"计数。

---

## Step 2｜恢复质量信号：确认/补齐 confidence + 版面特征入批（serverocr 特有，质量杠杆最大）

**要解决的问题（serverocr 与 paddle 的核心差异）**：
- **服务不返回 confidence**：`server_ocr.py` 的 `_optional_conf`（tools/ocr/server_ocr.py:403）已支持 confidence/conf/score/prob/probability 字段映射，但 21/21 页全 None → 服务端响应没带（或字段名不在清单里）。连锁后果：a) `_needs_review` 永不触发，OCR 错字无第二道修补（这是 serverocr kept80 0.899 < paddle 0.950 的重要成因——LLM 不知道哪些行不可信，纠错全靠猜）；b) reconstruct prompt 里"低置信行谨慎纠错"规则空转；c) 确定性快路径（依赖 conf 门控）不可能触发。
- **批路径没接 layout.py 版面推断**：与 paddle 相同，全部行 ambiguous → 标题双轨规则空转、boilerplate（"华中科技大学附属印刷厂/1701572/页"这类服务返回的页脚噪声）混进 LLM 输入。

**改法（3 小步，按依赖顺序）**：

1. **拿 conf（首选找服务方，次选本地取证）**：
   - 与服务方确认：响应里是否有 per-line 置信/得分字段，字段名是什么；`_optional_conf` 的 `_first_present` 清单按实际字段扩展即可（改动一行）。
   - 取证脚本：抓 1 页的原始响应 JSON 落盘（在 server_ocr 的解析处临时 dump 一条），确认字段形态后再定映射；**不要本地编造 conf**（伪 conf 会误导门控与纠错）。
   - 若服务端确认无法提供：跳过 conf 依赖，改用第 3 步的启发式 review 触发。
2. **版面特征入批**：OCR 后逐页跑 `layout._infer_layout_hints`（tools/ocr/layout.py:113，已实现）→ 行带 role_hint/title_decision/heading_score；boilerplate 页脚行在进 LLM 前剔除（serverocr 的页脚噪声比 paddle 多，收益更明显）；LLM 拿到 locked/ambiguous 标题双轨，标题层级贴原图。
3. **门控与 review 激活**：
   - 拿到 conf 后：低置信行进 prompt 标记（谨慎纠错规则生效）、`_needs_review` 恢复（低置信行存在即触发）、高置信页可走确定性路径（0 token）。
   - 拿不到 conf 的兜底：改 `_needs_review` 增加"无 conf 启发式"分支——按"疑似公式行 + 短行含乱码/孤符号 + 数字字母混排"选窗（窗口机制已现成，只换选窗标准），让 serverocr 也有审校轮。

**为什么省/值**：质量杠杆最大——paddle 与 serverocr 同 LLM、同语料，差异只在 OCR 输出形态（paddle 带 conf、行整；server 无 conf、行碎）。恢复信号链后 serverocr 的 kept80 理论上能追到 paddle 的 ~0.95 水平，同时保住它多 28% 的检出量优势（内容全 + 保真高 = 还原度反超 paddle）。token 侧：确定性路径命中打印清晰的页时省整次 LLM；review 启用增加 ~8~11k token 是买质量的（可与 paddle 的 review A/B 结论互相印证）。

**风险与回退**：conf 拿不到 → 兜底启发式先上线；服务方字段映射错 → 取证落盘先看真值再定。

**验收**：同 Step 1 跑法，重点看 run.json 新出现的 `per_image[].avg_conf`（非 None）、`batches[].needs_review_llm`（出现 1）、`whole.fidelity.text.kept80_ratio`（目标 ≥0.93）。

---

## Step 3｜页级并行整理 + 行合并预规整 + 保真闸门留痕（时间 ↓3~4 倍 + 收尾质量）

**要解决的问题**：LLM 172.8s 占墙钟 96%（3 次整批串行重写，单路 ~93 tok/s）；行碎（550 参考行 vs paddle 430）让每页的 prompt/输出都比 paddle 大（30.1k vs 24.5k prompt）；截断虽被 Step 1 补上，但长上下文页尾质量仍弱于页级整理。

**改法（3 小步）**：

1. **页级（1~2 页/批）并行整理**：与 paddle Step 2 相同架构——页级分派短整理调用、4~6 路并发、每页附上一页末标题防跨页漂移、按序拼接 + 全局同族标题归并。serverocr 特有的加分项：
   - **整理前先做确定性行合并**：serverocr 行碎（同页相邻行 bbox 邻接、字高相近、行尾无标点 + 下行首非大写/非编号 → 合并），把 550 行先规整到 ~450 行量级，prompt/输出都变小（省 token 且行保真统计口径与 paddle 对齐）。
   - vLLM 确认开 `--enable-prefix-caching`（r2 cache_hit_tokens=0），否则页级化会让系统 prompt 重复 21 次推高 prompt token。
2. **保真闸门留痕**：Step 1 的自检结果（每批缺失行数/字数/位置 首·中·尾）写进 run.json 与日志——serverocr 无 review 兜底，这份"漏检地图"是它质量回归的主要依据。
3. **review 精修（承接 Step 2）**：拿到 conf 后按 paddle 同款 A/B 收紧触发条件；无 conf 启发式路径先跑一轮对照，验证"有 review vs 无 review"的 kept80 差，决定是否常开。

**为什么省/值**：时间 172.8s → 35~60s（并发 4~6，vLLM 连续批处理）；内容全的优势在页级短上下文下保真进一步上升（目标 kept80 ≥0.95）；token 总量在 prefix cache 开启后持平或略降（行合并 + 无截断重复生成）。

**风险与回退**：并发退化（vLLM 排队）→ 并发数做成环境变量开关先 2 路实测；行合并误并（把两行不同内容并成一句）→ 合并只做"高置信拼接"，不做语义判断，误并风险交给 review/LLM 兜底。

**验收**：`--label s3` 跑一轮，对照 `20260903_194740_serverocr_b8_r2`：`wall.review_seconds` <90s、`llm_by_label` 的 calls 数变为页批数、`whole.fidelity.text.kept80_ratio` ≥0.95、`ingest.increment` ≥24（追平 paddle 水平）、截断 0。

---

## 通用建议（serverocr 注意点）

- 服务端 OCR 的原始响应先落盘取证一次（conf 字段、公式字段形态、页脚噪声规律），再动映射代码——serverocr 的多数优化都依赖这份"响应真值"。
- 固定 A/B 口径：同语料 21 张、`--engine serverocr --batch-size 8`、加 `--label`；对比字段固定取 run.json 的 `wall.*`、`llm_by_label.*`、`whole.fidelity.*`、`ingest.increment`、`batches[].fidelity`、`per_image[].avg_conf`。
- 暂不做：视觉大模型直读、本地 rapidocr 兜底改造、调 OCR 并发（占时仅 3%）。
