# OCR→Markdown 还原优化路线 · ServerOCR（2026-09-04 修订版）

> 修订说明：共享层机制（完整性闭环、页级并行、组间流水线重叠、页界去重、审校
> 留痕、基线记账）已在 paddleocr 上落地并实测；这些机制**对 serverocr 自动生效**
> （引擎差异被 adapter 层隔离）。本文档因此重排为两部分：①「共享机制已生效清单
> （server 自动受益，待 server 实测确认）」；②「server 特有专项」（核心缺口：
> **OCR 服务不返回 confidence**，其次行碎）。不再把已完成的事重复列为待办。

---

## 0. 基线快照（历史记录，用于对照）

serverocr 历史实测（同一语料、批 8、OCR 并发 4，vLLM deepseek-v4-flash）：

| 运行 | 墙钟 | 总 token（快照口径） | kept80 / avg | 说明 |
| --- | --- | --- | --- | --- |
| r2（初版基线） | 179.0s | 46.2k | 0.899 / 0.922 | 3/3 批被上限截断；无 review（无 conf） |
| p0（显式缺失闭环） | 249.8s | ~65k | 0.985 / 0.986 | 截断修复；稿尾曾被噪声兜底污染（已由噪声纪律修正） |

**serverocr 两个引擎级事实（与语料无关）**：
1. **OCR 服务不返回 confidence**（21/21 页 avg_conf=None；`server_ocr._optional_conf` 已支持
   confidence/conf/score/prob/probability，但服务端响应未带出）→ 连锁影响：
   review 门控永不触发、低置信行谨慎纠错空转、页级确定性路径几乎不可达；
2. **行碎**：识别行多而短（参考行数明显多于 paddle 同批），行合并依赖整理 LLM。

---

## ① 共享机制已生效清单（serverocr 自动受益）

以下全部在共享管线（tools/ocr/levels/light.py + tools/ocr/reconstruct.py），
paddle 已实测；**serverocr 尚未用新代码跑过**，第一优先动作是补一次全量运行验证
（见 §验证命令），而不是再开发。

| 机制 | 位置/开关 | server 受益点 | 状态 |
| --- | --- | --- | --- |
| 输出上限护栏 | `_estimate_reconstruct_tokens`：`clamp(输入字符×2, 9000, 50000)` | 不再被 max_tokens 掐断批尾（r2 曾 3/3 批截断） | ✅ 已落地（paddle 实测） |
| 完整性闭环（显式缺失） | `ensure_markdown_complete`；`OCR_COMPLETENESS_FIX` | **无 review 兜底时这是唯一第二道保障**，收益应最大 | ✅ 已落地 |
| 噪声纪律 | `_recoverable_row` / `_keep_for_append` / 片段复检 | 页码/乱码/页脚不被恢复机制塞回稿子 | ✅ 已落地（p0 污染形态的修正） |
| 页级整理 | `OCR_PAGE_RECONSTRUCT`（默认 1）、`OCR_RECONSTRUCT_WORKERS`（默认 4） | 墙钟大降；server 的 OCR 快（~5s），整理是绝对大头 | ✅ 已落地（paddle：整批 258.9s→113.1s） |
| 组间流水线重叠 | `OCR_PIPELINE_OVERLAP`（默认 1） | 下一组 OCR 与当前组整理并行；server OCR 段短，藏得干净 | ✅ 已落地（paddle：111.5s→93.6s） |
| 页界整段重复去重 | `_dedupe_page_boundary_blocks`（合并前，零 token） | 消除页级续写的跨界重复段 | ✅ 已落地 |
| 审校旁路+留痕 | `OCR_REVIEW`（默认 1）；`batches[].review` / `review_stats` | 无 conf 时 review 门控不触发——留痕会如实显示 disabled，便于跨语料判定 | ✅ 已落地 |
| 记账口径 | llm token 取快照、`chunk_stats` 真实墙钟、`--set-env`、`pipeline_overlap` 标志 | 对比可信 | ✅ 已落地 |

---

## ② server 特有专项（按价值排序）

### Step S1｜补一次 server 全量运行，确认共享机制在该引擎的表现

**为什么**：共享机制全部按 paddle 形态验证过；serverocr 的输入形态不同
（无 conf、行碎、公式行带 formula 字段），需要一次实测确认：页级门控的
触发分布、确定性页是否出现、完整性闭环触发率、墙钟与 token 的实际收益。

**动作**：见 §验证命令（三组对照），拉回 run.json 后按性质验收：
- `config.pipeline_overlap` / `env_overrides` 记录正确；
- `wall.total_seconds` 显著低于 r2（179s）——具体幅度不作预设，机制收益来自
  页级+重叠，与语料无关；
- `batches[].completeness` 触发率与 fallback 行数正常（噪声纪律生效、稿尾无噪声块）；
- kept80/avg 与 p0 同档或更好，截断类缺陷=0。

### Step S2｜恢复质量信号：向 OCR 服务方确认/取回 confidence（server 最大质量杠杆）

**为什么**：serverocr 与 paddle 同 LLM、同语料时质量差异的主要来源之一是无 conf：
- `_needs_review` 依赖 conf → 无 conf 则审校永不执行（r2 起 rev=0×N）；
- reconstruct prompt 的"低置信行谨慎纠错"依赖 conf 标记 → 空转；
- 页级确定性门控的"高置信页"分支依赖 conf → 几乎不可达。

**动作**：
1. **取证**：抓 1~2 页 OCR 服务原始响应落盘，确认是否存在 per-line 置信/
   得分字段、字段名是什么（`server_ocr._optional_conf` 的 `_first_present` 清单
   按实际字段扩展即可，改动一行级）；
2. 与服务方确认：能否在响应中带出该字段（这属于服务配置/协议问题，非本仓库能改）；
3. 确认返回后重跑基线：`per_image[].avg_conf` 应非 None；`batches[].needs_review_llm`
   可能出现 true；事件里低置信行开始生效。

**拿不到 conf 的兜底（可选，不做预设）**：为无 conf 形态启用启发式审校触发
（公式行 + 短行乱码窗），用现有 `OCR_REVIEW` 开关做 A/B；判定只做性质检查
（applied_patches 是否长期≈0），不预设数值。

### Step S3｜行碎处理（可选评估项，不预设必做）

**问题**：server 行碎使参考行数明显多于 paddle，每页 prompt 与行统计开销更大；
行碎本身也降低"行级保真"度量的可读性。

**候选动作（机制性，需先评估再决定）**：整理前做**确定性行合并预规整**——
同页相邻行 bbox 邻接、字高相近、行尾无标点且下行首非编号 → 合并为一段；
只做高置信拼接，不做语义判断，误并风险交给整理/审校兜底。
**决策依据**：等 S1 的 server 页级运行数据出来后，看每页参考行数与 prompt token
的占比再决定是否值得做（跨语料，不预设阈值）。

---

## 验证命令（server 全量对照，约 3×4 分钟）

```bash
# ① 现状默认：页级 + 组间重叠（共享机制全开）
python ocr_baseline/run_baseline.py --engine serverocr --label srvOn

# ② 页级关（整批一次长文重写），隔离页级收益
python ocr_baseline/run_baseline.py --engine serverocr --label srvBatch --set-env OCR_PAGE_RECONSTRUCT=0

# ③ 重叠关（页级保留），隔离组间重叠收益
python ocr_baseline/run_baseline.py --engine serverocr --label srvNoOv --set-env OCR_PIPELINE_OVERLAP=0
```

前置：服务器 `.env` 的 `SERVER_OCR_*` 按生产配置就位（服务可达）；
对比字段固定取 run.json：`wall.total_seconds`、`config.*`（含 pipeline_overlap/
env_overrides）、`llm_by_label`（快照口径）、`whole.fidelity.*`、`completeness`、
`review_stats`、`per_image[].avg_conf`。

## 环境开关总表（共享层，两引擎通用）

| 开关 | 默认 | 作用 |
| --- | --- | --- |
| `OCR_PAGE_RECONSTRUCT` | 1 | 页级整理；0 = 整批一次长文重写（A/B） |
| `OCR_RECONSTRUCT_WORKERS` | 4 | 页级整理并发路数 |
| `OCR_PIPELINE_OVERLAP` | 1 | 组间流水线重叠；0 = 串行（A/B） |
| `OCR_COMPLETENESS_FIX` | 1 | 完整性闭环；0 = 关闭（A/B） |
| `OCR_CONTINUE_MAX_CALLS` / `OCR_CONTINUE_MAX_TOKENS` | 2 / 3000 | 补写预算 |
| `OCR_REVIEW` | 1 | 审校轮；0 = 旁路（A/B） |
| `OCR_UPSCALE` 等 | 0 | 仅 paddleocr 生效的识别前放大（server 无关） |

## 暂不做（明确排除）

- 视觉大模型直读、换 OCR 引擎；
- 在拿不到 conf 前先做"启发式 review 触发"的数值调优（等 S1/S2 证据）；
- 行合并预规整的阈值预设（等 S1 数据）。
