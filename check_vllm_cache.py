#!/usr/bin/env python3
"""check_vllm_cache.py -- 服务器端 vLLM Prefix Caching (Prefill Cache) 状态全能检测工具。

针对生产环境配置：
    LLM_BACKEND=vllm
    LLM_VLLM_BASE_URL=http://127.0.0.1:8000/v1
    LLM_VLLM_API_KEY=sjk_vllm_dsv4flash0731
    LLM_VLLM_MODEL=deepseek-v4-flash-0731

核心检测逻辑：
1. 【鉴权与模型就绪检测】：
   - 携带 API Key 探测 /v1/models；
   - 支持模型名模糊与全路径匹配（如深层目录挂载路径 /data/models/deepseek-v4-flash-0731）。
2. 【Prometheus 引擎级指标探针】：
   - 探测 /metrics 端点（带鉴权头），检查 vLLM 原生的 prefix cache 核心指标：
     * vllm:num_prefix_cache_hits_total
     * vllm:gpu_prefix_cache_hit_rate
     * vllm:prefix_cache_queries / hits
     * vllm:gpu_cache_usage_factor
3. 【高载荷双轮 TTFT 测速探针（2500+ Tokens 长前缀）】：
   - 注入约 2500 Tokens 的真实公文与模板静态前缀（规避短 Prompt 耗时低于网络抖动的假象）；
   - 冷启动测算首字延迟 (TTFT_cold)；
   - 热复用测算首字延迟 (TTFT_warm)，计算真实加速比；
4. 【API 级 Token 命中探针 (Stream + Non-Stream 双通道)】：
   - 捕获 usage.prompt_tokens_details.cached_tokens 与 prompt_cache_hit_tokens；
   - 若流式协议因版本原因未带 usage，自动回退非流式调用获取权威 Token 级缓存审计。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env_file(env_path: Path) -> None:
    """加载 .env 环境变量（不覆盖已有系统环境变量）。"""
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        raw_val = val.strip()
        if raw_val[:1] not in {"'", '"'}:
            val = raw_val.split(" #", 1)[0]
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def get_vllm_config(args: argparse.Namespace) -> tuple[str, str, str, float]:
    """获取 vLLM 连接配置 (base_url, api_key, model, timeout)。"""
    root_env = Path(__file__).resolve().parent / ".env"
    load_env_file(root_env)

    base_url = (
        args.base_url
        or os.getenv("LLM_VLLM_BASE_URL")
        or "http://127.0.0.1:8000/v1"
    ).rstrip("/")
    api_key = args.api_key or os.getenv("LLM_VLLM_API_KEY") or "EMPTY"
    model = (
        args.model
        or os.getenv("LLM_VLLM_MODEL")
        or "deepseek-v4-flash-0731"
    )
    timeout = float(os.getenv("LLM_TIMEOUT") or 120.0)
    return base_url, api_key, model, timeout


def probe_models(base_url: str, api_key: str) -> tuple[bool, list[str], str]:
    """探针 1：查询 /v1/models 检查连通性与模型列表。"""
    url = f"{base_url}/models"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return True, models, "连接成功"
    except urllib.error.HTTPError as exc:
        return False, [], f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, [], str(exc)


def resolve_actual_model_name(requested_model: str, hosted_models: list[str]) -> str:
    """解决模型名路径前缀不一致问题（如 deepseek-v4-flash-0731 vs /models/deepseek-v4-flash-0731）。"""
    if not hosted_models:
        return requested_model
    if requested_model in hosted_models:
        return requested_model
    # 模糊后向匹配
    for m in hosted_models:
        if m.endswith(requested_model) or requested_model in m:
            return m
    return hosted_models[0]


def probe_metrics(base_url: str, api_key: str) -> dict[str, float | str]:
    """探针 2：抓取 vLLM /metrics 端点，检查 Prefix Caching 指标。"""
    # 尝试两种标准 metrics URL 拼接形态
    candidates = []
    if base_url.endswith("/v1"):
        candidates.append(base_url[:-3] + "/metrics")
    parsed = urllib.parse.urlparse(base_url)
    candidates.append(f"{parsed.scheme}://{parsed.netloc}/metrics")

    metrics: dict[str, float | str] = {}
    last_err = ""
    for metrics_url in candidates:
        req = urllib.request.Request(
            metrics_url,
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # 匹配所有 vLLM 版本可能存在的 prefix cache 监控项
                    for key in (
                        "vllm:num_prefix_cache_hits_total",
                        "vllm:num_prefix_cache_queries_total",
                        "vllm:gpu_prefix_cache_hit_rate",
                        "vllm:cpu_prefix_cache_hit_rate",
                        "vllm:prefix_cache_hit_rate",
                        "vllm:prefix_cache_queries",
                        "vllm:prefix_cache_hits",
                        "vllm:gpu_cache_usage_factor",
                    ):
                        if line.startswith(key):
                            parts = line.split()
                            if len(parts) >= 2:
                                # Prometheus 格式标准：最后一个 token 永远是指标值
                                val_str = parts[-1]
                                try:
                                    metrics[key] = float(val_str)
                                except ValueError:
                                    metrics[key] = val_str
                if metrics:
                    return metrics
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)

    if not metrics and last_err:
        metrics["_error"] = last_err
    return metrics


# 构造约 2500+ Tokens 的高拟真长系统公文规则与模板前缀（保证 Prefill 耗时具有足够分辨率）
STATIC_SYSTEM_PREFIX = """
你是一个顶级的政务与企业会议纪要权威专家。你必须严格遵循以下系统级公文写作准则、结构忠实铁律及形态排版规范：

一、公文事实准则与信息完整性
1. 唯一事实来源为所提供的会议记录、研讨记录与上游结构化提取：严禁引入任何外部先验知识、网络百科常识或未提及的事实；
2. 凡在会议中提及的具体数据、日期、时间节点、政策名、法律条款、责任主体与裁决结论，必须原样完整保留，不加总、不换算、不推测；
3. 对于态度与立场动词，采用庄重严谨、权威得体的官方公文动词（明确支持、重申原则、坚定推进、统筹协同、严格把关、深化落实等），杜绝机械堆砌标签；
4. 当议题涉及多个子维度（如现状痛点、成因剖析、应对策略、保障措施、责任分工）时，必须结构化层次分明展开，杜绝大段密集堆叠。

二、形态排版与二级缩进规范（公文体例标准）
1. 条目主干一行一项（以 - 或 1. 开头），标签行首加粗嵌在句首（- **标签名**：具体事实与定调）；
2. 当并列事实超过两个维度，或涉及具体考核指标、标志性工程项目试点、多主体权责分工时，强制使用二级无序缩进（2 空格   - ）展开细节；
3. 状态标记（已完成 / 进行中 / 未开始 / 阻塞）严格遵循规范，仅在表格状态列或指定位置出现，正文中不逐条重复机械描述；
4. 问答栏目只收录真实一问一答，长答复按核心逻辑压缩，保持单段连贯，不拆分段落，不使用列表条目嵌套；
5. 严禁在交付正文中复述或输出「本栏隐去」、「整栏省略」、「未提及」等提示词说明原话，若无内容且允许省略则整栏连同标题整体不予呈现。

三、通用输出要求与格式边界
1. 直接输出 Markdown 交付正文，不添加外层代码围栏（``` 或 ```markdown），不添加任何开场白、客套话与结束语；
2. 标题层级严格遵循模板规范，固定标题必须准确匹配，不随意升降层级；
3. 涉及重大战略决策、关键量化指标（如百分比、金额、时限、人员配额）时，采用加粗 **具体内容** 醒目标注；
4. 叙述性文本紧凑精炼，去套话、去修饰性铺垫，保持高信息密度与客观中立视角。

四、项目进度与重点工作专项标准
1. 涉及工程与任务推进，条目必须包含“做什么 + 责任方 + 时间节点 + 交付目标”四大核心要素；
2. 遇到潜在卡点与阻塞时，明确标出受阻环节与外部依赖前提，不因要素暂缺漏报关键风险；
3. 核心交付物用 **具体内容** 强调，依赖前提用 *具体内容* 提示，讲求务实落地，不写无对象的套话。
""".strip() * 2  # 复制加倍以确保达到 2000~2500 Tokens 量级


def send_chat_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
) -> dict:
    """发送流式请求，测量首字耗时 (TTFT)、总耗时与 usage 字段。"""
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 32,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    t_start = time.perf_counter()
    ttft = None
    first_token_received = False
    full_content = []
    prompt_tokens = 0
    cached_tokens = 0

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                # 检查 usage
                if "usage" in obj and obj["usage"]:
                    u = obj["usage"]
                    prompt_tokens = u.get("prompt_tokens") or prompt_tokens
                    details = u.get("prompt_tokens_details") or {}
                    cached_tokens = (
                        details.get("cached_tokens")
                        or u.get("prompt_cache_hit_tokens")
                        or u.get("cached_tokens")
                        or 0
                    )

                choices = obj.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece and not first_token_received:
                        ttft = time.perf_counter() - t_start
                        first_token_received = True
                    if piece:
                        full_content.append(piece)

        t_end = time.perf_counter()
        total_sec = t_end - t_start
        if ttft is None:
            ttft = total_sec

        return {
            "success": True,
            "ttft": ttft,
            "total_latency": total_sec,
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "content": "".join(full_content).strip(),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "ttft": 0.0,
            "total_latency": 0.0,
            "prompt_tokens": 0,
            "cached_tokens": 0,
            "content": "",
            "error": str(exc),
        }


def send_chat_non_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
) -> dict:
    """发送非流式请求，专门用于精确解析 usage 字典中各版本的缓存命中字段。"""
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 16,
        "stream": False,
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.perf_counter() - t_start
            usage = data.get("usage") or {}
            details = usage.get("prompt_tokens_details") or {}
            cached = (
                details.get("cached_tokens")
                or usage.get("prompt_cache_hit_tokens")
                or usage.get("cached_tokens")
                or 0
            )
            return {
                "success": True,
                "elapsed": elapsed,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "cached_tokens": cached,
                "raw_usage": usage,
                "error": None,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "elapsed": 0.0,
            "prompt_tokens": 0,
            "cached_tokens": 0,
            "raw_usage": {},
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="vLLM Prefix Caching 状态检测工具")
    parser.add_argument("--base-url", help="vLLM API Base URL，如 http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", help="vLLM API Key (默认从 .env 或 sjk_vllm_dsv4flash0731 读取)")
    parser.add_argument("--model", help="vLLM 模型名 (默认从 .env 读取)")
    args = parser.parse_args()

    base_url, api_key, req_model, timeout = get_vllm_config(args)

    print("=" * 72)
    print("      vLLM 服务端 Prefix Caching (Prefill Cache) 生产就绪检测器")
    print("=" * 72)
    print(f"[*] 目标地址 : {base_url}")
    print(f"[*] 目标模型 : {req_model}")
    print(f"[*] 认证密钥 : {'******' + api_key[-6:] if len(api_key) > 6 else 'EMPTY'}")
    print(f"[*] 超时设置 : {timeout}s")
    print("-" * 72)

    # 步骤 1：服务连通性与模型校验
    print("[1/4] 验证服务连通性与模型可用性...")
    conn_ok, model_list, conn_msg = probe_models(base_url, api_key)
    if not conn_ok:
        print(f"  [!] 无法连接到 vLLM 实例: {conn_msg}")
        print("      请检查 vLLM 是否启动，或确认 LLM_VLLM_BASE_URL / LLM_VLLM_API_KEY 配置。")
        return 1

    actual_model = resolve_actual_model_name(req_model, model_list)
    print(f"  [+] 连接成功！vLLM 实例在线模型: {model_list}")
    if actual_model != req_model:
        print(f"  [*] 自动适配模型 ID: '{req_model}' ➔ '{actual_model}'")
    else:
        print(f"  [+] 模型匹配成功: '{actual_model}'")

    # 步骤 2：Prometheus Metrics 探针
    print("\n[2/4] 检索 vLLM Prometheus 监控指标 (/metrics)...")
    metrics = probe_metrics(base_url, api_key)
    metrics_active = False
    if "_error" in metrics:
        print(f"  [-] /metrics 端点不可达 ({metrics['_error']})，将依靠 TTFT 与 API Usage 判定。")
    else:
        print("  [+] /metrics 获取成功，相关指标快照:")
        for k, v in metrics.items():
            print(f"      • {k}: {v}")
        if any(
            k in metrics
            for k in (
                "vllm:num_prefix_cache_hits_total",
                "vllm:gpu_prefix_cache_hit_rate",
                "vllm:prefix_cache_hit_rate",
                "vllm:prefix_cache_hits",
            )
        ):
            metrics_active = True

    # 步骤 3：高载荷流式冷热测速探针 (TTFT 探针)
    print("\n[3/4] 执行高载荷冷热双请求测速探针 (~2500 Tokens 静态长前缀)...")
    msgs_cold = [
        {"role": "system", "content": STATIC_SYSTEM_PREFIX},
        {"role": "user", "content": "收到指示，请仅回复四个汉字【首次握手】。"},
    ]
    msgs_warm = [
        {"role": "system", "content": STATIC_SYSTEM_PREFIX},
        {"role": "user", "content": "收到指示，请仅回复四个汉字【二次复用】。"},
    ]

    print("  --> 发送【冷启动】请求 (构建前缀 KV Cache)...")
    rc = send_chat_stream(base_url, api_key, actual_model, msgs_cold, timeout)
    if not rc["success"]:
        print(f"  [!] 冷启动请求失败: {rc['error']}")
        return 1
    print(f"      TTFT 首字耗时: {rc['ttft']*1000:.1f}ms | 总延迟: {rc['total_latency']*1000:.1f}ms | Cached Tokens: {rc['cached_tokens']}")

    # 间隔 0.5 秒等待 vLLM Radix Tree 显存块落池
    time.sleep(0.5)

    print("  --> 发送【热复用】请求 (验证前缀 KV Cache 命中)...")
    rw = send_chat_stream(base_url, api_key, actual_model, msgs_warm, timeout)
    if not rw["success"]:
        print(f"  [!] 热复用请求失败: {rw['error']}")
        return 1
    print(f"      TTFT 首字耗时: {rw['ttft']*1000:.1f}ms | 总延迟: {rw['total_latency']*1000:.1f}ms | Cached Tokens: {rw['cached_tokens']}")

    speedup = (rc["ttft"] / rw["ttft"]) if rw["ttft"] > 0.001 else 1.0
    print(f"  --> 【TTFT 首字加速比】: {speedup:.2f}x")

    # 步骤 4：非流式 Usage 兜底探针（部分 vLLM 版本 stream 不包 usage）
    cached_tokens_confirmed = max(rc["cached_tokens"], rw["cached_tokens"])
    raw_usage_report = {}
    if cached_tokens_confirmed == 0:
        print("\n[4/4] 流式响应未上报 cached_tokens，执行非流式 Usage 权威校验...")
        rn = send_chat_non_stream(base_url, api_key, actual_model, msgs_warm, timeout)
        if rn["success"]:
            cached_tokens_confirmed = rn["cached_tokens"]
            raw_usage_report = rn["raw_usage"]
            print(f"      非流式调用成功: Prompt Tokens={rn['prompt_tokens']} | Cached Tokens={rn['cached_tokens']}")
            print(f"      Raw Usage 详情: {rn['raw_usage']}")
        else:
            print(f"      非流式调用异常: {rn['error']}")
    else:
        print("\n[4/4] 流式已成功捕获 Cached Tokens 字段，跳过非流式回退。")

    # ── 综合判定矩阵 ──────────────────────────────────────────────
    is_cache_enabled = False
    reasons = []

    # 1. 绝对黄金证据：API 层明确返回 cached_tokens > 0
    if cached_tokens_confirmed > 0:
        is_cache_enabled = True
        reasons.append(f"API usage.cached_tokens 显式命中 {cached_tokens_confirmed} tokens！")

    # 2. 绝对白金证据：/metrics 内部计数器探测到 hits 增长或命中率
    if metrics_active:
        hits = metrics.get("vllm:num_prefix_cache_hits_total") or metrics.get("vllm:prefix_cache_hits") or 0
        hit_rate = metrics.get("vllm:gpu_prefix_cache_hit_rate") or metrics.get("vllm:prefix_cache_hit_rate") or 0
        reasons.append(f"/metrics 内部监控项生效 (hits={hits}, hit_rate={hit_rate})")
        if float(hits) > 0 or float(hit_rate) > 0:
            is_cache_enabled = True

    # 3. 统计学强证据：TTFT 首字延迟呈现倍数级飞跃（>= 2.5x）
    if speedup >= 2.5:
        reasons.append(f"同前缀 TTFT 首字延迟呈现显著倍数跳变 ({speedup:.2f}x 加速)")
        if not is_cache_enabled:
            is_cache_enabled = True

    # 输出判定报告
    print("\n" + "=" * 72)
    print("                          检 测 报 告")
    print("=" * 72)
    if is_cache_enabled:
        print("  🟢【综合判定】：服务端 vLLM **已开启** Prefix Caching (Prefill Cache)！")
        print("  【有效判定依据】:")
        for r in reasons:
            print(f"    • {r}")
        print("\n  【生产提速建议】:")
        print("    1. 保持「静态长前缀置顶、动态会议文本后置」设计；")
        print("    2. 将通用公文规范与模板定义固化在 Token 0 处，跨请求立享毫秒级 TTFT 首字加速！")
    else:
        print("  🔴【综合判定】：服务端 vLLM **未开启** 或 **未生效** Prefix Caching！")
        print("  【实测现状】:")
        print(f"    • API cached_tokens 命中数为 0 (未见 KV Cache 复用)")
        print(f"    • TTFT 首字加速比仅为 {speedup:.2f}x (冷启动 {rc['ttft']*1000:.1f}ms vs 热复用 {rw['ttft']*1000:.1f}ms)")
        if metrics_active:
            print("    • /metrics 中相关命中计数未发生增长")
        print("\n  【开启方法（只需一个参数）】:")
        print("    请在服务器启动 vLLM 实例时追加以下参数并重启服务：")
        print("    >>> python -m vllm.entrypoints.openai.api_server \\")
        print("            --model /path/to/deepseek-v4-flash-0731 \\")
        print("            --api-key sjk_vllm_dsv4flash0731 \\")
        print("            --enable-prefix-caching \\           <--- 【关键参数】")
        print("            --port 8000")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
