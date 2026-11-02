#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""智能眼镜/手机大屏识别工具：批量/单图提取显示屏有效文字内容与视觉世界理解信息。

场景定位：
智能眼镜、手机等随身设备拍摄的大屏幕（会议屏、电脑显示器、投影幕等）。
画面往往包含外部复杂环境（会议室、人物、桌椅、反光等）。
本脚本调用内部多模态 VLM 接口，将注意力聚焦于【屏幕视口内部】，
输出两个顶层核心 JSON 字段：
1. screen_text: 显示屏内提取的有效文字内容
2. screen_understanding: 显示屏内内容的视觉世界理解信息

支持模式：
1. 文件夹批量模式（推荐）：
   输入文件夹路径，自动遍历其中的所有图片（.jpg / .jpeg / .png），
   每张图片独立调用接口识别，并将结果保存至该文件夹下的 `output/<图片名>.json`。
2. 单张图片模式：
   输入单张图片路径，识别后将结果输出到终端，并保存到根目录 JSON 文件中。

用法：
  python test_screen_vlm.py <文件夹路径或图片路径>
  或直接运行 python test_screen_vlm.py 根据提示输入路径
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageOps

# ── 1. 清理代理环境变量，防止内网请求被外部代理拦截 ──
for proxy_var in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
]:
    os.environ.pop(proxy_var, None)

# ── 2. VLM 接口配置 ──
BID = "llm_texthawk_test"
FLOW_ID = "llm_texthawk_test"
VLM_HOST = "http://10.34.23.78:8888"
SIGN_KEY = "7F04F5043B894BA598D66E03845F44C10C68B8E90D7347058771209D0B582A7B"
APP_ID = "cvcloud_classify"

# 支持的图片扩展名
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# ── 3. 聚焦显示屏视口的精简多模态 Prompt ──
SCREEN_EXTRACTION_PROMPT = """你是一名专业的多模态视觉理解专家。当前图片由智能眼镜或手机等随身设备拍摄，画面中包含一块物理显示屏（如会议大屏、投影幕、电脑显示器等），并可能夹杂外部现实环境。

请将视觉注意力完全聚焦于画面中的【显示屏内部】，主动忽略屏幕外部的物理环境（如人物、桌椅、背景等）。

请严格输出包含且仅包含以下两个顶级字段的标准 JSON 对象：

{
  "screen_text": "显示屏内提取的所有有效文字内容。按阅读逻辑完整还原屏幕文字，保留自然的换行与段落排版，过滤掉外部无关文字。",
  "screen_understanding": "对显示屏内容的整体理解信息。概括屏幕展示的形式（如PPT/数据看板/架构图/文档等）、图形或图表所表达的含义，以及屏幕所传达的核心主题与关键结论。"
}

输出要求：
1. 聚焦屏内：所有文字与理解信息必须 100% 来源于画面中的显示屏内部，忽略屏幕外的任何现实背景。
2. 真实准确：文字内容忠实还原原文，不臆测；理解信息紧扣屏幕内容，客观精炼。
3. 纯净输出：仅输出标准合法的 JSON 格式，不要使用 Markdown 代码围栏（不要 ```json），不要包含任何前言后记。"""


def image_to_base64(image_path: str | Path) -> str:
    """加载图片并自动进行 EXIF 方向校正，转为 RGB base64 字符串。"""
    path_obj = Path(image_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    if path_obj.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"不支持的图片格式: {path_obj.suffix}，仅支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    with Image.open(path_obj) as img:
        img_rgb = img.convert("RGB")
        # 智能眼镜/手机随手拍常带有 EXIF 旋转标记，自动矫正为正向画面
        img_transposed = ImageOps.exif_transpose(img_rgb)
        with io.BytesIO() as buffer:
            img_transposed.save(buffer, format="JPEG", quality=95)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")


def calc_sign(
    data: str,
    sign_key: str,
    query_param: dict,
    path: list,
    method: str,
    app_id: str,
    mode: str = "easy",
) -> Tuple[int, str]:
    """计算 CLOUDSOA-HMAC-SHA256 签名。"""
    payload = ""
    if data and mode != "easy":
        payload = data

    query_str = "&".join(f"{k}={v}" for k, v in query_param.items())
    path_str = "/" + "/".join(str(p) for p in path)
    timestamp = int(time.time() * 1000)

    sign_str = f"{method}&{path_str}&{query_str}&{payload}&appid={app_id}&timestamp={timestamp}"
    signature = base64.b64encode(
        hmac.new(
            sign_key.encode("utf-8"),
            sign_str.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return timestamp, signature


def parse_vlm_stream_response(response_text: str) -> str:
    """从 MEP-SSE 流式响应中提取并拼接所有 text 碎片。"""
    pattern = r"\$@START_PREFIX@#(\{[\s\S]*?\})\$@END_SUFFIX@#"
    ret_list = re.findall(pattern, response_text)
    if not ret_list:
        return response_text.strip()

    text_pieces = []
    chunks = ret_list[:-1] if len(ret_list) > 1 else ret_list
    for chunk in chunks:
        try:
            res = json.loads(chunk)
            if "text" in res and res["text"]:
                text_pieces.append(res["text"])
        except Exception:
            continue

    return "".join(text_pieces).replace("\u200b", "").strip()


def safe_load_json(raw_str: str) -> Dict[str, Any]:
    """健壮的 JSON 解析器，自动处理 Markdown 代码围栏与末尾截断补齐。"""
    clean_str = raw_str.replace("\u200b", "").strip()

    # 1. 剥离 Markdown 代码围栏 (```json ... ```)
    if clean_str.startswith("```"):
        lines = clean_str.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean_str = "\n".join(lines).strip()

    # 2. 尝试标准解析
    try:
        data = json.loads(clean_str)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 3. 截断容错修复（补充未闭合的双引号和大括号）
    fixed_str = clean_str
    if fixed_str.count('"') % 2 != 0:
        fixed_str += '"'
    braces_needed = fixed_str.count("{") - fixed_str.count("}")
    if braces_needed > 0:
        fixed_str += "}" * braces_needed

    try:
        data = json.loads(fixed_str)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 4. 极端异常兜底
    return {
        "parse_error": "JSON_DECODE_FAILED",
        "raw_content": raw_str,
    }


def call_vlm_api(
    img_b64: str,
    *,
    b_id: str = BID,
    flow_id: str = FLOW_ID,
    custom_prompt: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """调用底层的多模态 VLM HTTP 接口并返回解析后的 JSON 字典。"""
    uu_id = str(int(time.time() * 1000))
    translocation_id = f"screen_vlm_{uu_id}"[:63]
    prompt_text = custom_prompt or SCREEN_EXTRACTION_PROMPT

    params = {
        "data": {
            "translocationId": translocation_id,
            "promptId": "SCREEN_VLM_PROMPT",
            "inputFormat": "base64",
            "requestId": translocation_id,
            "image": img_b64,
            "prompt": prompt_text,
        },
        "meta": {
            "subId": "2",
            "bId": b_id,
            "flowId": flow_id,
            "uuId": uu_id,
        },
        "version": "1.2",
    }
    payload_str = json.dumps(params, ensure_ascii=False)

    query_param = {"bId": b_id, "flowId": flow_id, "uuId": uu_id}
    timestamp, sign = calc_sign(
        payload_str,
        SIGN_KEY,
        query_param,
        path=["predict"],
        method="POST",
        app_id=APP_ID,
        mode="easy",
    )
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "text/event-stream;charset=UTF-8",
        "Authorization": f'CLOUDSOA-HMAC-SHA256 appid={APP_ID}, timestamp={timestamp}, signmode=easy, signature="{sign}"',
    }

    url = f"{VLM_HOST}/predict?bId={b_id}&flowId={flow_id}&uuId={uu_id}"
    response = requests.post(
        url,
        data=payload_str.encode("utf-8"),
        headers=headers,
        timeout=timeout,
        verify=False,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"VLM 请求失败: HTTP {response.status_code}, 响应: {response.text[:300]}"
        )

    raw_vlm_text = parse_vlm_stream_response(response.text)
    result_dict = safe_load_json(raw_vlm_text)

    # 规范化最外层两个字段
    if "screen_text" not in result_dict and "screen_understanding" not in result_dict:
        result_dict = {
            "screen_text": result_dict.get("text") or result_dict.get("ocr") or raw_vlm_text,
            "screen_understanding": result_dict.get("understanding") or result_dict.get("summary") or "未能成功提取结构化理解",
            "_raw_response": raw_vlm_text,
        }

    return result_dict


def process_single_image(
    image_path: Path,
    output_dir: Optional[Path] = None,
    *,
    b_id: str = BID,
    flow_id: str = FLOW_ID,
    timeout: int = 120,
) -> Tuple[bool, Dict[str, Any], Path]:
    """处理单张图片，调用 VLM 并将结果保存为 `<image_stem>.json`。
    
    返回: (是否成功, 结果字典, 保存文件路径)
    """
    path_obj = image_path.resolve()
    target_output_dir = output_dir or Path(__file__).resolve().parent
    target_output_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_output_dir / f"{path_obj.stem}.json"

    try:
        img_b64 = image_to_base64(path_obj)
        result_dict = call_vlm_api(img_b64, b_id=b_id, flow_id=flow_id, timeout=timeout)
        
        # 写入 JSON
        out_file.write_text(
            json.dumps(result_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True, result_dict, out_file

    except Exception as exc:
        err_dict = {
            "status": "failed",
            "error_message": str(exc),
            "image_path": str(path_obj),
            "screen_text": "",
            "screen_understanding": "",
        }
        out_file.write_text(
            json.dumps(err_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return False, err_dict, out_file


def natural_sort_key(p: Path) -> list:
    """自然排序键，使图片按文件名数字顺序排列 (如 1, 2, 10 而非 1, 10, 2)。"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", p.name)]


def find_images_in_folder(folder_path: Path) -> List[Path]:
    """查找目标文件夹中的所有图片，自动排除 output 目录与隐藏文件。"""
    # 优先检索直接子目录中的图片
    direct_images = [
        p for p in folder_path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(".")
    ]
    if direct_images:
        return sorted(direct_images, key=natural_sort_key)

    # 若根层没有图片，则递归搜索子目录（排除 output 目录）
    recursive_images = [
        p for p in folder_path.rglob("*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and "output" not in [part.lower() for part in p.parts]
        and not p.name.startswith(".")
    ]
    return sorted(recursive_images, key=natural_sort_key)


def batch_process_folder(
    folder_path: str | Path,
    *,
    b_id: str = BID,
    flow_id: str = FLOW_ID,
    timeout: int = 120,
) -> None:
    """批量遍历文件夹下的所有图片，调用 VLM 并将每个 json 存入 `<folder>/output/`。"""
    folder = Path(folder_path).resolve()
    if not folder.exists() or not folder.is_dir():
        print(f"[错误] 文件夹不存在或不是有效目录: {folder}")
        return

    output_dir = folder / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    image_files = find_images_in_folder(folder)
    total = len(image_files)

    print("\n" + "=" * 70)
    print(" 开始批量大屏图片识别任务")
    print("=" * 70)
    print(f"输入文件夹: {folder}")
    print(f"输出文件夹: {output_dir}")
    print(f"发现图片数: {total} 张 (支持 {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
    print("=" * 70)

    if total == 0:
        print("[提示] 目标文件夹内未找到支持的图片文件。")
        return

    success_count = 0
    fail_count = 0
    start_time = time.time()

    for idx, img_path in enumerate(image_files, start=1):
        print(f"\n[{idx}/{total}] 正在处理: {img_path.name}")
        t0 = time.time()
        ok, res, saved_path = process_single_image(
            img_path,
            output_dir=output_dir,
            b_id=b_id,
            flow_id=flow_id,
            timeout=timeout,
        )
        elapsed = time.time() - t0

        if ok:
            success_count += 1
            print(f"  -> 成功 ({elapsed:.2f}s) | JSON 保存至: {saved_path.name}")
            # 简短打印文字与理解概要
            text_preview = (res.get("screen_text") or "").strip().replace("\n", " ")[:60]
            und_preview = (res.get("screen_understanding") or "").strip().replace("\n", " ")[:60]
            if text_preview:
                print(f"     [文字预览]: {text_preview}...")
            if und_preview:
                print(f"     [理解预览]: {und_preview}...")
        else:
            fail_count += 1
            print(f"  -> 失败 ({elapsed:.2f}s): {res.get('error_message')}")

    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print(" 批量识别任务完成！")
    print("=" * 70)
    print(f"总处理图片: {total} 张")
    print(f"成功数量  : {success_count} 张")
    print(f"失败数量  : {fail_count} 张")
    print(f"累计耗时  : {total_time:.2f} 秒 (平均 {(total_time/total):.2f}s/张)")
    print(f"所有结果均保存在: {output_dir}")
    print("=" * 70 + "\n")


def main() -> None:
    print("=" * 70)
    print(" 智能眼镜/手机大屏识别工具（支持文件夹批量与单图测试）")
    print("=" * 70)

    if len(sys.argv) > 1:
        target_path_str = sys.argv[1].strip().strip('"').strip("'")
    else:
        target_path_str = input("请输入文件夹路径 (或单张图片路径): ").strip().strip('"').strip("'")

    if not target_path_str:
        print("未输入有效路径，程序退出。")
        return

    target_path = Path(target_path_str).resolve()
    if not target_path.exists():
        print(f"[错误] 路径不存在: {target_path}")
        return

    if target_path.is_dir():
        # 1. 文件夹批量处理模式
        batch_process_folder(target_path)
    elif target_path.is_file():
        # 2. 单张图片处理模式
        print(f"\n检测到单张图片输入: {target_path.name}")
        root_dir = Path(__file__).resolve().parent
        ok, res, saved_path = process_single_image(target_path, output_dir=root_dir)
        
        # 额外更新一份固定的 screen_result_latest.json 方便直接查看
        latest_path = root_dir / "screen_result_latest.json"
        latest_path.write_text(
            json.dumps(res, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("\n" + "=" * 70)
        print("【1. 图中屏幕上提取的有效文字内容 (screen_text)】:")
        print("-" * 70)
        print(res.get("screen_text", "(无内容)"))

        print("\n" + "=" * 70)
        print("【2. 图中屏幕上的有效世界理解信息 (screen_understanding)】:")
        print("-" * 70)
        print(res.get("screen_understanding", "(无内容)"))
        print("=" * 70)
        print(f"结果已保存至: {saved_path}")
        print(f"最新记录已保存至: {latest_path}\n")


if __name__ == "__main__":
    main()
