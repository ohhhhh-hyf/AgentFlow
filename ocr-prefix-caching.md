# OCR 流水线前缀缓存（Prefix Caching）开启指导

> 状态：**待执行**——服务端形态已确认（自部署 vLLM，records `config.llm_provider=vllm`）。
> 现代 vLLM（V1 引擎）的 Automatic Prefix Caching（APC）**默认开启**，大概率不需要服务端改启动参数；
> 本仓库侧只有一个真实缺口（§2.1 命中字段读取）加一个验证流程。零质量风险（缓存不改变生成），
> 收益在 prompt/prefill 侧：省 prefill 时间，官方缓存计费时省钱。
> 这份文档是之后"开 prefix caching"的指导：服务端同事按 §1、仓库侧按 §2、验证按 §3、验收按 §4。

---

## 0. 收益量级：先看命中机会在哪（决定做什么、不做什么）

以一次 21 图页级运行实测为例（s4srvOn，仅供数量级示意，不预设目标）：

| 数据 | 值 |
| --- | --- |
| `ocr/reconstruct` | 16 次调用，prompt 27.9k token（每页约 1.7k），completion 17.5k |
| `ocr/reconstruct/fix` | 6 次调用，prompt 2.6k token |
| `cache_hit_tokens` | 0（观测缺口，见 §2.1，不表示缓存未生效） |

由此分出三层命中机会：

- **L1 同一次运行内、页与页之间**：共享前缀 = 系统提示（压缩后 571 字符，约几百 token）×15 页 ≈
  每 run 几千 token。稳定但小。
- **L2 同输入复跑 / 重复入库**（A/B、回归、同一用户重复上传同一笔记）：整条 prompt 逐 token 一致
  （payload 序列化是确定性的，见 §2.2）→ **整段命中，prompt prefill 几乎归零**。这是收益最大、
  最确定的场景：一次 21 图 run 约 30k prompt token 的 prefill 在第二次复跑时不再重复计算。
- **L3 跨 label**：reconstruct / review / fix 各自 system 不同，互相没有前缀可共享。

**结论**：不要把时间花在"微调 prompt 布局去凑页间前缀"上（增量只有固定引导那几十~百 token × 页数，
且改动会让 L2 的历史对比失效，见 §2.3）。收益顺序是：**L2 复跑/重传场景 > L1 页间 system 共享**；
做事的顺序是：确认服务端状态 → 补上命中观测 → 连跑两次验证 → 按需核算。

## 1. 服务端（vLLM 部署方）怎么做

### 1.1 确认状态（预计无需改动）

1. 记录版本：`vllm --version`；
2. 查启动命令行：确认没有 `--no-enable-prefix-caching`；现代版本（V1 引擎）APC 默认开，
   显式加 `--enable-prefix-caching` 只对老版本（0.4.x）或 CPU backend（默认关）有必要；
3. 若部署在容器/编排平台，检查环境变量或 helm values 里是否显式关了缓存。

### 1.2 可选：让 usage 回传命中字段

vLLM 默认不在 OpenAI usage 里回传缓存命中数（本仓库观测为 0 的主因）。
若想让 run.json 直接可见命中，服务端加启动参数（版本间命名可能有差异，以
`vllm serve --help | grep -i prompt-tokens` 为准）：

```
--enable-prompt-tokens-details
```

之后每次响应的 `usage.prompt_tokens_details.cached_tokens` 即本次命中的前缀 token 数
（新版本还拆 `local_cached_tokens` / `external_cached_tokens`，cached = 两者之和）。

### 1.3 验证证据（三选一，不依赖 usage 字段）

- **服务端指标**：请求前后各取一次 `/metrics`，看 `vllm:prefix_cache_hits`（累计命中 token 数，
  Prometheus counter 常带 `_total` 后缀）与 `vllm:prefix_cache_queries` 增量；命中率 =
  hits / queries。`vllm:prompt_tokens_recomputed` 大增说明缓存被频繁淘汰（thrashing）。
- **同 prompt 两次请求**：对同一段长 prompt 连续 curl 两次，第二次 TTFT（首 token 延迟）
  应显著下降（同输入 warm 请求可降 60–90%+）。
- **usage 字段**：按 1.2 开启后，任一客户端响应里的 `prompt_tokens_details.cached_tokens > 0`。

### 1.4 若后端形态变化（官方 API / 网关）

DeepSeek 官方 API 与多数网关：自动上下文缓存，无需配置；usage 顶层返回
`prompt_cache_hit_tokens`（客户端已读取），命中部分按缓存价计费。届时只跑 §3 验证即可。

## 2. 仓库侧怎么做

### 2.1 补齐命中观测（唯一代码缺口，小改动）

`client/llmclient.py::_record_usage` 目前只读 usage **顶层**的
`prompt_cache_hit_tokens` / `cached_tokens`（DeepSeek 官方/网关形态）。vLLM 把命中放在
**嵌套**的 `usage.prompt_tokens_details.cached_tokens`，因此即使服务端缓存生效，run.json
的 `cache_hit_tokens` 也是 0。补读嵌套字段即可：

```python
# _record_usage 内，现有顶层读取之前补一段兼容读取：
details = usage.get("prompt_tokens_details") or {}
cache_hit = int(
    usage.get("prompt_cache_hit_tokens")          # DeepSeek 官方/网关：顶层
    or usage.get("cached_tokens")                 # 部分网关/代理：顶层
    or details.get("cached_tokens")               # vLLM(--enable-prompt-tokens-details)
    or details.get("local_cached_tokens", 0) + details.get("external_cached_tokens", 0)
    or 0
)
```

改完打上 §2.1 补丁后，开缓存状态直接进 run.json `llm_by_label[*].cache_hit_tokens` 与
`llm_client_snapshot`，无需再对服务端 metrics。此补丁零行为风险（字段缺失时回退 0）。

### 2.2 "逐 token 一致"纪律（缓存命中的前提，已审计现状 + 未来红线）

- **系统提示必须是常量**：三个 label 的 system 都是模块级常量 ✓
  （`RECONSTRUCT_SYSTEM_PROMPT` / `REVIEW_SYSTEM_PROMPT` / `_CONTINUE_TAIL_INSTRUCT` /
  `_CONTINUE_MID_INSTRUCT`，见 §6）。
- **user payload 序列化确定性 ✓**：`_lines_to_structured_payload` 固定
  `ensure_ascii=False + separators=(",", ":")` + 固定键序 → 同输入跨进程/跨次运行逐字节一致。
- **红线（未来不要踩）**：任何动态内容（时间戳、request_id、随机措辞、把变量拼进 system）
  都会从插入点切断缓存；改提示词文本会让"改前 vs 改后"的缓存对比整体失效（不同前缀，
  不是坏，是没法比）——每次提示词变更后重新做一次 L2 基线即可。

### 2.3 prompt 布局微调——评估为不推荐

旧方案"把跨页上下文段移到 payload 之后以延长页间前缀"经审计不划算：
页间唯一共享前缀是 system prompt；把 context 后置只多共享"固定引导 + JSON 开头"的几十
~百 token × 页数（约 1k~2k token/run），却会让所有历史 run 的前缀失效、对比口径作废。
**除非未来引入大的公共模板前缀**（例如整批共享的长上下文注入、KB 侧长 system），否则不做。
若做，原则不变：静态在前、可变在后、内容不增删。

### 2.4 其它

- 观测节奏：评估缓存期间不要同时动提示词/开关/并发路数，保证对照干净；
- 缓存键与采样参数无关（temperature/max_tokens 不进前缀），同前缀的并发请求可同时命中。

## 3. 开启与验证协议（服务端确认后照做）

1. 服务端按 §1.1 确认状态、记录版本与启动参数；按需加 §1.2 参数；
2. 仓库侧打上 §2.1 补丁（若服务端没开 usage 字段，用 `/metrics` + 时间证据替代）；
3. 页级基线连跑两次（同引擎、同语料、同代码、同参数，LLM 服务保持常驻）：

```bash
python ocr_baseline/run_baseline.py --engine paddleocr --label cacheOn
python ocr_baseline/run_baseline.py --engine paddleocr --label cacheOn2   # 原样复跑
python ocr_baseline/run_baseline.py --engine serverocr --label cacheSrvOn
python ocr_baseline/run_baseline.py --engine serverocr --label cacheSrvOn2  # 原样复跑
```

4. 判定缓存生效（任一即可）：
   - run.json `llm_by_label[*].cache_hit_tokens > 0`（§1.2 已开时）；
   - `cacheOn2` 相对 `cacheOn`：reconstruct 的 `avg_seconds` / prompt 处理明显下降、
     `wall.total_seconds` 下降（首跑已把整条 prompt 写入缓存，次跑整段命中）；
   - 服务端 `/metrics` 出现 prefix cache hits 增量、recompute 接近 0。
5. 质量回归：`fidelity`（kept80/avg/公式分项）、`formulas`、入库增量与开启前记录持平。
   缓存不改变生成，理论上只验证无回归；若某次调用恰好被淘汰重算，内容也与未开缓存一致。
6. 收益核算口径：自部署 vLLM 省的是 **prefill 时间与机器吞吐**（KV 复用同时省显存占用），
   不是 token 计费；官方 API/网关形态下命中 token 按缓存价计费，用
   `cache_hit_tokens × 价差` 折算。不要用任何单语料的绝对值当目标。

## 4. 验收（性质化，不预设数值）

- 缓存确认生效：usage 字段 > 0，或同输入二次运行耗时明显下降，或服务端 metrics 有命中；
- 命中随"同前缀请求数"增长：同语料复跑次数越多、页数越多、重复上传越多，收益越大；
- 质量无副作用：kept80 / avg_char / 公式 avg / 入库增量与开启前持平；
- 代码改动面 ≤ §2.1 一处；不做无谓的 prompt 布局改动（§2.3）。

## 5. 常见坑

- **命中粒度**：vLLM 按 16 token 的 block 对齐命中——页级 system 仅几百 token，会整 block
  命中，正常；极短前缀（<16 token）收益忽略。
- **cache_hit_tokens=0 ≠ 缓存没生效**：没开 §1.2 时 usage 里根本没有命中字段；以 metrics /
  时间证据为准，不要因为字段为 0 就判定失败（这正是本次记录里 0 的成因）。
- **LRU 淘汰**：引擎显存压力大或高并发时旧块会被淘汰，复跑间隔内保持引擎空闲即可命中；
  `prompt_tokens_recomputed` 上升 = thrashing，优先查容量/并发而不是参数。
- **逐字节一致才命中**：JSON 键序、浮点表示、换行、尾随空格都会切断缓存——不要换用
  pretty-print / sort_keys 变体，不要在提示词里加任何动态内容。
- **改提示词后旧记录不可比**：前缀变了，与历史 run 的缓存对比无意义，需重跑基线；
  模型权重版本更新同理会清空缓存。
- **后端不同、口径不同**：vLLM 与官方 API 的字段位置/计费不同（§1.2 / §1.4），
  别把一套字段套到另一套后端上。
- 缓存只作用于 **prompt/prefill 侧**；completion（生成）时间与 token 不受影响。

## 6. 代码 / 字段 / 命令索引

| 位置 | 说明 |
| --- | --- |
| `client/llmclient.py::_record_usage`（约 146–185 行） | 命中字段读取处（§2.1 补丁点）：现读顶层 `prompt_cache_hit_tokens`/`cached_tokens`，需补 `prompt_tokens_details.cached_tokens` |
| `tools/ocr/reconstruct.py`（`RECONSTRUCT_SYSTEM_PROMPT` / `REVIEW_SYSTEM_PROMPT` / `_CONTINUE_*_INSTRUCT`） | 恒定 system，各 label 页间共享前缀主体 |
| `tools/ocr/reconstruct.py::_lines_to_structured_payload` | user payload 确定性序列化（键序/分隔符固定） |
| `tools/ocr/reconstruct.py::reconstruct_markdown` | 页级 user prompt 拼接（context 前置段，§2.3 判定不推荐挪动） |
| `ocr_baseline/run_baseline.py` | `cache_hit_tokens` 打印、`llm_client_snapshot`、`llm_by_label` 聚合 |
| 服务端 | vLLM：`/metrics` 的 `prefix_cache_hits` / `prefix_cache_queries` / `prompt_tokens_recomputed`；启动参数 `--enable-prompt-tokens-details`（可选）、`--no-enable-prefix-caching`（确认未出现） |

---

## 待办清单（状态勾选）

- [x] 确认 LLM 后端形态（records `config.llm_provider = vllm`，自部署）
- [ ] 服务端：记录 vLLM 版本与启动参数；确认无 `--no-enable-prefix-caching`；按需加 `--enable-prompt-tokens-details`
- [ ] 服务端：`/metrics` 或同 prompt 两次请求取一次命中证据（§1.3）
- [ ] 仓库侧：打上 §2.1 命中字段补丁（唯一代码改动，零行为风险）
- [ ] 跑 `cacheOn` / `cacheOn2`（paddleocr）与 `cacheSrvOn` / `cacheSrvOn2`（serverocr），判定命中
- [ ] 质量回归：fidelity / formulas / 入库增量与开启前持平
- [ ] 若将来后端换成官方 API / 网关：直接按 §3 复验（客户端顶层字段已就绪，无需再改代码）
