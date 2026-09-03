# 页级 OCR 整理的前缀缓存（Prefix Caching）成本回收

> 状态：**待执行**——需要服务端（vLLM 部署方）配合确认/开启，本仓库侧代码已具备观测字段，可能有一处可选的小调整（见 §5.4）。
> 动机：页级整理（Step 2）把整批一次长文重写拆成每页一次短整理，墙钟约减半，代价是 prompt 总量上升（同一任务的 N 个页请求重复携带相同的系统提示与固定引导）。若服务端支持前缀缓存，这部分重复 prefill 的 KV 可复用，命中 token 不计入（或按低价计）实际成本，且降低每请求首字延迟。当前基线 `cache_hit_tokens` 观测为 0，疑似 vLLM 未开 `--enable-prefix-caching`，需先确认。

---

## 1. 收益面（为什么值得做）

前缀缓存对以下场景都有效，页级整理只是最直接的一个：

| 场景 | 可复用的公共前缀 |
| --- | --- |
| 页级整理：同一批 N 页 | 系统提示 + 固定引导 + JSON 结构说明（占 prompt 主要部分） |
| 同语料多轮运行（A/B、回归、重复入库） | 上述全部 + 相同页行内容 |
| 完整性补写 / 审校轮 | 与主整理共用同一份 `RECONSTRUCT_SYSTEM_PROMPT` / `REVIEW_SYSTEM_PROMPT` |
| 同一用户重复上传相同笔记 | 整段前缀完全一致 |

也就是说：**即使不开页级模式，只要重复跑同一批语料，前缀缓存也能回收成本**；页级模式把"重复"从"跨次运行"变成了"同一次运行内"，命中机会更多、收益更即时。

## 2. 原理简述（给服务端同事的背景）

- 服务端对请求的 **token 序列前缀**做 KV cache 复用（vLLM 的 RadixAttention / DeepSeek 网关的自动上下文缓存）。
- 命中判定要求**前缀逐 token 完全一致**——与采样参数（temperature/top_p）无关，但与消息文本、角色结构、请求顺序有关。
- 计费/计价两模式：
  - **DeepSeek 官方 API / 网关**：自动启用，命中部分按缓存价计费，usage 返回 `prompt_cache_hit_tokens`；
  - **vLLM 自部署**：需要启动参数 `--enable-prefix-caching`；是否在 usage 里回传命中字段取决于版本（vLLM 主要把命中统计暴露在 `/metrics`，不一定进 response usage）。
- 本仓库客户端已读取命中字段：`client/llmclient.py` 的 `_record_usage` 兼容 `prompt_cache_hit_tokens` / `cached_tokens`；基线 run.json 的 `cache_hit_tokens` 与 `llm_client_snapshot.usage_by_label[*].cache_hit_tokens` 可直接观测。

## 3. 前置确认清单（服务端，需部署/运维配合）

1. **确认当前 LLM 后端形态**：仓库 `.env` 的 `LLM_BACKEND` 是 `http`（直连 DeepSeek 官方）、`websocket`（服务器网关）还是 `vllm`（自部署 OpenAI 兼容服务）。基线 run.json 的 `config.llm_provider` 会写明。
2. **自部署 vLLM**：
   - 查启动命令是否已含 `--enable-prefix-caching`；没有则加上并重启（或改部署平台对应的 env/helm values）；
   - 记录 vLLM 版本（`vllm --version`），确认该版本支持 prefix caching（0.4.x 起）；
   - 注意显存：开启后 KV cache 占用上升，与 `gpu_memory_utilization`、并发路数需要平衡；
   - 与连续批处理/分块 prefill 默认兼容，一般无需额外参数。
3. **官方 API / 网关**：通常自动生效，无需配置；确认 usage 是否回传命中字段即可。
4. **确认方式（一条命令）**：服务端改完配置后，用本仓库基线工具跑一次页级运行，看 run.json：
   - `cache_hit_tokens > 0`（usage 回传命中字段时）；
   - 或 vLLM `/metrics` 出现 prefix cache 命中计数；
   - 或"同输入跑第二次，墙钟与每请求耗时明显下降"（无 usage 字段时的代理证据，见 §6）。

## 4. 本仓库侧现状（基本已就绪）

- 客户端 usage 字段读取：已实现（`client/llmclient.py::_record_usage`，键 `prompt_cache_hit_tokens`/`cached_tokens`）；
- 基线观测：run.json `llm_by_label[*].cache_hit_tokens` + `llm_client_snapshot.usage_totals.cache_hit_tokens`；
- 提示词结构：`RECONSTRUCT_SYSTEM_PROMPT` / `REVIEW_SYSTEM_PROMPT` 是**模块级常量**，跨调用完全一致 → 天然是公共前缀；页级每页的 `user` 消息以固定引导开头。

## 5. 可选的提示词结构调整（最大化命中，改动小）

当前页级 user prompt 顺序（`tools/ocr/levels/light.py::_draft_pagewise` → `tools/ocr/reconstruct.py::reconstruct_markdown`）：

```
固定引导（"OCR 行列表 JSON（按阅读顺序排列…）"）
【跨页上下文】…（每页可变）
页行 JSON payload（每页可变）
```

固定前缀只覆盖到"固定引导"为止。把**每页可变的跨页上下文段移到 payload 之后**，公共前缀会延伸到 payload 之前的所有内容，命中长度最大化。收益大小取决于固定部分与 payload 的长度比，是否值得动取决于服务端确认缓存生效后的实测。

> 调整原则：不改系统提示语义、不改变给模型的内容；只移动可变段位置。改后需重跑一次页级基线确认质量指标（kept80/avg/入库增量）与调整前持平。

## 6. 验证步骤（拿到服务端确认后照做）

1. 服务端开启/确认缓存，记录 vLLM 版本与启动参数（或网关说明）；
2. 本仓库**零代码改动**跑页级基线：`python ocr_baseline/run_baseline.py --engine paddleocr --label cacheOn`；
3. **原样复跑第二次**（同引擎、同语料、同参数，`--label cacheOn2`）——若服务端有缓存，第二次的 prompt 处理与整体墙钟应低于第一次（同输入连续命中）；
4. 看 run.json：`cache_hit_tokens`、`wall.total_seconds`、`llm_by_label[*].avg_seconds`；
5. 若 usage 不回传命中字段但时间有下降：以"二次运行墙钟差 + vLLM /metrics"为证据，确认缓存生效；
6. 确认生效后，按需做 §5 的提示词结构调整并复跑对比；
7. 成本核算口径：命中 token 按服务端计费规则折算（官方 API 有缓存价；自部署省的是 prefill 时间与带宽，直接体现在墙钟）。

## 7. 验收（性质化，不预设数值）

- 缓存确实生效：`cache_hit_tokens > 0`，或同输入二次运行的墙钟/每请求耗时明显下降；
- **质量无副作用**：kept80 / avg_char / 公式 avg / 入库增量与开启前持平（缓存不改变生成内容，只需确认无回归）；
- 命中比例随"同前缀请求数"增长（页数越多、同语料复跑越多，收益越大）；
- 不把任何单语料的绝对值当目标——只验证"缓存是否生效 + 是否无副作用"。

## 8. 注意事项 / 常见坑

- **前缀一致性**：system 或固定引导里任何动态内容（时间戳、随机数、每请求变化的措辞）都会切断缓存；保持常量；
- **不要与其它变量同时改**：观察期间固定并发路数、语料、开关，保证对照干净；
- **显存与并发**：开缓存后注意 `gpu_memory_utilization` 与并发路数的平衡，避免 OOM 或吞吐回退；
- **usage 字段缺失≠没生效**：vLLM 命中统计主要在 `/metrics`，response usage 可能不含命中字段；以时间证据为准，不要因为字段为 0 就判定失败；
- 页级模式单页输出短，缓存收益主要体现在 **prompt/prefill 侧**；completion（生成）侧不受影响。

## 9. 相关代码/字段索引

| 位置 | 说明 |
| --- | --- |
| `client/llmclient.py`（`_record_usage`） | 读取 `prompt_cache_hit_tokens` / `cached_tokens`，累计进 `cache_hit_tokens` |
| `tools/ocr/reconstruct.py`（`RECONSTRUCT_SYSTEM_PROMPT` 等常量） | 恒定 system，公共前缀主体 |
| `tools/ocr/levels/light.py`（`_draft_pagewise`） | 页级并行的每页 prompt 组装（跨页上下文位置，§5 的可调点） |
| `tools/ocr/reconstruct.py`（`reconstruct_markdown`） | user prompt 固定引导 + context 段 + payload 的拼接处 |
| `ocr_baseline/run_baseline.py` | `cache_hit_tokens` 打印、`llm_client_snapshot`、`llm_by_label` |

---

## 待办清单（状态勾选）

- [ ] 服务端确认 LLM 后端形态（http / websocket / vllm）
- [ ] vLLM：确认/添加 `--enable-prefix-caching` 并重启；记录版本
- [ ] 跑 `--label cacheOn` 页级基线（零代码改动）
- [ ] 原样复跑 `--label cacheOn2`，对比墙钟/耗时/cache 字段
- [ ] 确认生效后评估 §5 提示词结构调整（可变段后置）并复跑
- [ ] 质量回归确认（kept80/avg/入库增量与开启前持平）
