## 进度总览（2026-09-04）

| 项 | 状态 |
| --- | --- |
| 共享机制（完整性闭环/页级/重叠/去重/审校留痕/记账） | ✅ 实现并双引擎实测（paddle 干净 A/B + server S1 三组对照） |
| S1 server 全量验证 | ✅ 完成（页级保留、账目正确、无 conf 影响确认） |
| S2 conf 信号 | ✅ 取证完成：`probability` 三级存在但恒 0，代码零改动待服务方答复；⏳ 外部依赖 |
| S3 行碎合并 | ✅ 评估完成 → **不默认开启**（结构扰动证据；实验开关保留） |
| 仓库内待办 | 无（剩余均为外部依赖或可选实验） |

---

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
**paddle 与 server 均已实测**（server 见 srvOn/srvBatch/srvNoOv 三组对照与
s3 系列运行），列表为最终状态，不再有待办。

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

### Step S1｜server 全量运行，确认共享机制在该引擎的表现（已完成 2026-09-04）

**结果摘要**（srvOn 页级+重叠 / srvBatch 整批 / srvNoOv 页级串行 三组对照）：
- 页级对 server 收益成立且质量更优（kept80 0.9899、公式 avg 0.959 档，
  显著高于整批 0.929 档）→ **页级默认保留**；
- 记账与开关全部正确（chunk_stats、pipeline_overlap、env_overrides 记录无误）；
- 无 conf 时 review 恒不触发（ran=0/3）——S2 专项的必要性再次实锤；
- 意外正向：即使无 conf，仍有部分干净页经版面 ambiguous 分支走确定性路径（零 LLM）；
- 组间重叠机制由离线确定性测试保证（test_step4）；现场单次对照被 LLM 输出长度
  方差污染，不以此做结论（墙钟分析以 completion token 归一化看待）。

### Step S2｜恢复质量信号：向 OCR 服务方确认/取回 confidence（server 最大质量杠杆）

**为什么**：serverocr 与 paddle 同 LLM、同语料时质量差异的主要来源之一是无 conf：
- `_needs_review` 依赖 conf → 无 conf 则审校永不执行（r2 起 rev=0×N）；
- reconstruct prompt 的"低置信行谨慎纠错"依赖 conf 标记 → 空转；
- 页级确定性门控的"高置信页"分支依赖 conf → 几乎不可达
  （注：无 conf 时仍有部分干净页经 ambiguous 分支走确定性，S1 已观测到）。

**状态（2026-09-04 取证完成）**：
- ✅ 取证结论：服务端响应在 **block / textLine / element 三级都有 `probability` 字段**，
  且生产行节点已携带 line 级 `probability`（`_optional_conf` 候选清单也已含该键，
  代码侧接线无缺口）；**但三级数值全部为 0**（行 0/29、元素 0/756、块 0/1）——
  根因是"服务端未返回有效置信（占位 0）"，不是字段缺失、也不是解析遗漏；
- ⏳ 待服务方答复：为什么 `probability` 恒为 0（模型未启用置信输出？接口版本占位？
  需要参数/模型类型开关？），能否返回 0~1 或 0~100 的真值
  （数值尺度兼容已就绪：`_optional_conf` 对 >1 自动按 /100 处理）；
- 拿到非 0 真值样本后仓库侧无需逻辑改动，重跑基线验证即可
  （预期：`per_image[].avg_conf` 非 None、review 门控/确定性高置信分支复活）；
- 若服务方确认无法提供：再启用"无 conf 启发式审校触发"兜底（A/B 性质判定）。

```bash
# 取证（已执行；原始响应在 ocr_baseline/records/*_raw_response.json）
python ocr_baseline/server_ocr_probe.py --images /path/to/任意两张笔记图片
```

**拿不到 conf 的兜底（可选，不做预设）**：为无 conf 形态启用启发式审校触发
（公式行 + 短行乱码窗），用现有 `OCR_REVIEW` 开关做 A/B；判定只做性质检查
（applied_patches 是否长期≈0），不预设数值。是否启用等取证结论出来再定。

### Step S3｜行碎处理（已评估 → **不默认开启**，代码保留为实验开关）

**为什么评估结论是"不默认开启"（机制性依据，非语料结论）**：
- 确定性行合并的收益（行数减半、prompt −18%）以**结构扰动为代价**：两轮实现
  （版面推断前合并；修复后的"推断后 + 同角色约束"）都在实测中出现标题被并进
  正文/条目消失——碎片行太短使版面角色本身不可靠，任何基于碎片角色的防线
  都不稳，合并链一旦开始就可能跨过真实行边界；
- 该能力管线里已有安全实现：整理 LLM 的规则就是"合并被断行的完整句子"，
  server 合并关的高质量正是在 LLM 语义合并下取得的——确定性合并是用更弱的
  信息做同一件事；
- 若将来仍想降行数/prompt，正路是引擎侧输出参数（服务端按行合并配置）或
  整理 prompt 的显式断行合并指令，不在行边界上做确定性赌博。

**保留内容**：`layout.merge_fragment_lines`（含同角色约束与标题保护）与
`OCR_MERGE_FRAGMENTS` 开关保留为实验项（默认 0）；`ocr_baseline/test_step5.py`
8 组用例覆盖其行为，供将来有更强行边界证据（如引擎返回行内词级坐标）时复用。
**约束**：默认必须为 0；任何重新评估需先给出"能区分碎片与真实行边界"的新证据，
不允许仅凭行数/token 收益开启。

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
