#!/usr/bin/env python3
"""check_vllm_cache.py -- 服务器端 vLLM Prefix Caching (Prefill Cache) 状态检测工具。

功能说明：
1. 【模型与连通性探针】：检测 vLLM 实例健康度、模型列表与服务延迟。
2. 【Prometheus 指标探针】：探查 vLLM 原生 /metrics 指标中的 prefix_cache_hit_rate、
   num_prefix_cache_hits_total 等内部监控项（最直接的引擎级凭证）。
3. 【双请求实测探针（Cold/Warm TTFT 对比）】：
   - 构造约 1500 tokens 的静态前缀（系统提示词公文规则）；
   - 请求 1（冷启动）：首次 prefill，测算首字延迟 (TTFT) 与 cached_tokens 字段；
   - 请求 2（热复用）：保持前缀完全一致，测算二次 prefill 首字延迟与缓存命中字段；
   - 综合计算 TTFT 加速比与 Token 级复用率。
4. 【诊断报告与运维建议】：输出明确的结论与服务器启动参数建议。

用法：
    python check_vllm_cache.py
    python check_vllm_cache.py --base-url http://10.x.x.x:8000/v1 --model deepseek-v4-flash-0731
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


def get_vllm_config(args: argparse.Namespace) -> tuple[str, str, str]:
    """获取 vLLM 连接配置 (base_url, api_key, model)。"""
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
    return base_url, api_key, model


def probe_models(base_url: str, api_key: str) -> tuple[bool, list[str], str]:
    """探针 1：查询 /v1/models 获取服务状态与加载的模型名。"""
    url = f"{base_url}/models"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return True, models, "连接成功"
    except Exception as exc:  # noqa: BLE001
        return False, [], str(exc)


def probe_metrics(base_url: str) -> dict[str, float | str]:
    """探针 2：抓取 vLLM /metrics 端点，检查 Prefix Caching 指标。"""
    # 转换为根 metrics 地址（例如 http://127.0.0.1:8000/v1 -> http://127.0.0.1:8000/metrics）
    parsed = urllib.parse.urlparse(base_url)
    metrics_url = f"{parsed.scheme}://{parsed.netloc}/metrics"

    req = urllib.request.Request(metrics_url, method="GET")
    metrics: dict[str, float | str] = {}
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 关注的 Prefix Caching 指标特征
                for key in (
                    "vllm:num_prefix_cache_hits_total",
                    "vllm:num_prefix_cache_queries_total",
                    "vllm:gpu_prefix_cache_hit_rate",
                    "vllm:prefix_cache_hit_rate",
                    "vllm:gpu_cache_usage_factor",
                ):
                    if line.startswith(key):
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                metrics[key] = float(parts[1])
                            except ValueError:
                                metrics[key] = parts[1]
    except Exception as exc:  # noqa: BLE001
        metrics["_error"] = str(exc)
    return metrics


# 构造约 1200-1500 字的高拟真系统规则静态前缀
STATIC_PREFIX_MOCK = """
你是一个专业的高级政务与企业会议纪要专家。你必须严格遵循以下全局公文规范与形态排版准则：
一、公文事实准则与信息完整性
1. 唯一事实来源为所提供的会议记录与内容来源：严禁引入外部常识、历史先验或未提及的事实；
2. 凡在会议中提及的具体数据、决策定调、责任人与时间节点，必须原样完整保留，不加总、不换算、不省略；
3. 对于态度与立场动词，采用庄重严谨的公文动词（明确支持、重申原则、坚定推进、统筹协同等），避免口语化或机械八股标签；
4. 当议题涉及多个子维度（如现状痛点、应对策略、保障措施）时，必须结构化层次分明展开，杜绝大段密集堆叠。

二、形态排版与二级缩进规范
1. 条目主干一行一项（以 - 或 1. 开头），标签行首加粗嵌在句首（- **标签名**：具体事实）；
2. 当并列事实超过两个维度，或涉及具体考核指标、标志性工程项目试点时，强制使用二级无序缩进（2 空格   - ）展开细节；
3. 状态标记（已完成/进行中/未开始/阻塞）仅在表格状态列或指定位置出现，正文中不逐条重复机械描述；
4. 问答栏目只收录真实一问一答，长答复按核心逻辑压缩，保持单段连贯，不拆分段落；
5. 严禁在正文中复述或输出「本栏隐去」、「整栏省略」、「未提及」等提示词说明原话，若无内容且允许省略则整栏整体不予呈现。

三、通用输出要求与格式边界
1. 直接输出 Markdown 交付正文，不添加外层代码围栏（``` 或 ```markdown），不添加任何开场白与结束语；
2. 标题层级严格遵循模板规范，固定标题必须准确匹配，不随意升降层级；
3. 涉及重大战略决策、关键量化指标（如百分比、金额、时限、人员配额）时，采用加粗 **具体内容** 醒目标注；
4. 叙述性文本紧凑精炼，去套话、去修饰性铺垫，保持高信息密度与客观中立视角。
""".strip()


def send_chat_stream_request(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> dict[str, float | int | str | None]:
    """发送单次流式请求，精确记录 TTFT（首字耗时）、总耗时与 usage.cached_tokens。"""
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 64,
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
    total_tokens = 0

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
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

                # 捕获 usage（vLLM 支持在流式末尾返回 prompt_tokens_details）
                if "usage" in obj and obj["usage"]:
                    u = obj["usage"]
                    prompt_tokens = u.get("prompt_tokens") or prompt_tokens
                    total_tokens = u.get("total_tokens") or total_tokens
                    # 探测三种常见的 cache 字段标准
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
                    content_piece = delta.get("content") or ""
                    if content_piece and not first_token_received:
                        ttft = time.perf_counter() - t_start
                        first_token_received = True
                    if content_piece:
                        full_content.append(content_piece)

        t_end = time.perf_counter()
        total_latency = t_end - t_start
        if ttft is None:
            ttft = total_latency

        return {
            "success": True,
            "ttft": ttft,
            "total_latency": total_latency,
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


def run_cache_probe(
    base_url: str,
    api_key: str,
    model: str,
) -> dict:
    """运行双请求探针（冷启动 vs 热复用）。"""
    # 请求 1：冷启动（首次加载静态前缀）
    msgs_cold = [
        {"role": "system", "content": STATIC_PREFIX_MOCK},
        {"role": "user", "content": "请测试连通性，回答数字【1001】。"},
    ]
    res_cold = send_chat_stream_request(base_url, api_key, model, msgs_cold)
    if not res_cold["success"]:
        return {"status": "fail", "reason": f"冷启动请求失败: {res_cold['error']}"}

    # 间隔 0.5 秒，确保 vLLM 完成 KV cache 归档入池
    time.sleep(0.5)

    # 请求 2：热复用（前缀 100% 一致，仅尾部提问略微不同）
    msgs_warm = [
        {"role": "system", "content": STATIC_PREFIX_MOCK},
        {"role": "user", "content": "请测试连通性，回答数字【2002】。"},
    ]
    res_warm = send_chat_stream_request(base_url, api_key, model, msgs_warm)
    if not res_warm["success"]:
        return {"status": "fail", "reason": f"热复用请求失败: {res_warm['error']}"}

    ttft_cold = float(res_cold["ttft"])
    ttft_warm = float(res_warm["ttft"])
    speedup = (ttft_cold / ttft_warm) if ttft_warm > 0.001 else 1.0

    return {
        "status": "ok",
        "res_cold": res_cold,
        "res_warm": res_warm,
        "speedup": speedup,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="vLLM Prefix Caching 状态检测工具")
    parser.add_argument("--base-url", help="vLLM API Base URL，如 http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", help="vLLM API Key (默认从 .env 或 EMPTY 读取)")
    parser.add_argument("--model", help="vLLM 模型名 (默认从 .env 读取)")
    args = parser.parse_args()

    base_url, api_key, model = get_vllm_config(args)

    print("=" * 70)
    print("      vLLM 服务端 Prefix Caching (Prefill Cache) 状态检测器")
    print("=" * 70)
    print(f"[*] 目标地址 : {base_url}")
    print(f"[*] 目标模型 : {model}")
    print(f"[*] 认证密钥 : {'******' if api_key != 'EMPTY' else 'EMPTY'}")
    print("-" * 70)

    # 步骤 1：服务连通性
    print("[1/3] 检查 vLLM 服务连通性与模型列表...")
    conn_ok, model_list, conn_msg = probe_models(base_url, api_key)
    if not conn_ok:
        print(f"  [!] 无法连接到 vLLM 实例: {conn_msg}")
        print("      请检查 vLLM 是否启动，或确认 LLM_VLLM_BASE_URL 配置。")
        return 1
    print(f"  [+] 连接成功！vLLM 实例加载的模型: {model_list}")
    if model not in model_list and model_list:
        print(f"  [!] 警告: 指定的模型 '{model}' 未在列表中，选用: '{model_list[0]}'")
        model = model_list[0]

    # 步骤 2：Prometheus Metrics 探针
    print("\n[2/3] 检索 vLLM 原生 Prometheus 指标 (/metrics)...")
    metrics = probe_metrics(base_url)
    metrics_active = False
    if "_error" in metrics:
        print(f"  [-] /metrics 端点不可达 ({metrics['_error']})，跳过指标判定。")
    else:
        print("  [+] /metrics 获取成功，相关指标如下:")
        for k, v in metrics.items():
            print(f"      - {k}: {v}")
        if any(
            k in metrics
            for k in (
                "vllm:num_prefix_cache_hits_total",
                "vllm:gpu_prefix_cache_hit_rate",
                "vllm:prefix_cache_hit_rate",
            )
        ):
            metrics_active = True

    # 步骤 3：冷热双请求实测探针
    print("\n[3/3] 执行冷热双请求实测探针 (同前缀 Prefill 测速)...")
    probe_result = run_cache_probe(base_url, api_key, model)
    if probe_result.get("status") != "ok":
        print(f"  [!] 实测探针执行失败: {probe_result.get('reason')}")
        return 1

    rc = probe_result["res_cold"]
    rw = probe_result["res_warm"]
    speedup = probe_result["speedup"]

    print("  -------------------------------------------------------------")
    print(f"  【冷启动请求】 TTFT: {rc['ttft']*1000:.1f}ms | 总耗时: {rc['total_latency']*1000:.1f}ms | Cached Tokens: {rc['cached_tokens']}")
    print(f"  【热复用请求】 TTFT: {rw['ttft']*1000:.1f}ms | 总耗时: {rw['total_latency']*1000:.1f}ms | Cached Tokens: {rw['cached_tokens']}")
    print(f"  【首字加速比】 TTFT Speedup: {speedup:.2f}x")
    print("  -------------------------------------------------------------")

    # 综合判定
    # 判定规则：
    # 1. 强特征：热请求返回 cached_tokens > 0；
    # 2. 次强特征：TTFT 加速比 >= 2.0x 且 /metrics 中存在 prefix_cache_hits 计数；
    # 3. 弱特征：TTFT 加速比显著（>= 2.5x）。
    is_cache_enabled = False
    reasons = []

    if rw["cached_tokens"] > 0:
        is_cache_enabled = True
        reasons.append(f"API usage.cached_tokens 显式命中 {rw['cached_tokens']} tokens")

    if metrics_active:
        queries = metrics.get("vllm:num_prefix_cache_queries_total", 0)
        hits = metrics.get("vllm:num_prefix_cache_hits_total", 0)
        reasons.append(f"/metrics 探测到 Prefix Cache 统计项 (queries={queries}, hits={hits})")
        if hits > 0:
            is_cache_enabled = True

    if speedup >= 2.0:
        reasons.append(f"热复用 TTFT 首字加速比显著 ({speedup:.2f}x)")
        if not is_cache_enabled and speedup >= 3.0:
            is_cache_enabled = True

    print("\n" + "=" * 70)
    print("                      检 测 结 论")
    print("=" * 70)
    if is_cache_enabled:
        print("  🟢【判定结果】：服务端 vLLM **已开启** Prefix Caching (Prefill Cache)！")
        print("  【判定依据】:")
        for r in reasons:
            print(f"    • {r}")
        print("\n  【生产建议】:")
        print("    1. 确保 Prompt 架构遵循「静态长前缀置顶、动态会议文本后置」原则；")
        print("    2. 将通用公文规则、模板说明与固定结构推至最左侧 (Token 0~N)，以最大化缓存命中率。")
    else:
        print("  🔴【判定结果】：服务端 vLLM **未开启** 或 **未生效** Prefix Caching！")
        print("  【判定依据】:")
        print(f"    • 热请求 cached_tokens 为 0 (冷={rc['cached_tokens']}, 热={rw['cached_tokens']})")
        print(f"    • 首字加速比仅为 {speedup:.2f}x (未见明显 Prefill 复用跳变)")
        if not metrics_active:
            print("    • /metrics 中未发现活跃的 prefix_cache_hits 监控项")
        print("\n  【开启方法】:")
        print("    请在服务器启动 vLLM 时显式添加参数：")
        print("    >>> python -m vllm.entrypoints.openai.api_server \\")
        print("            --model <模型路径> \\")
        print("            --enable-prefix-caching \\      <--- 核心参数")
        print("            --port 8000")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
