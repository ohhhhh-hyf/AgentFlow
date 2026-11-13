"""infra.vlm.agenda_client -- 视觉多模态大模型议程识别客户端 (零旧代码依赖).

核心能力:
1. 从 .env 读取配置 (VLM_AGENDA_*), 支持 CloudSOA HMAC-SHA256 签名鉴权;
2. 图片 Base64 转码与 EXIF 方向自适应校正;
3. SSE 流式响应解析与基于语法栈的 JSON 容错逆序补齐;
4. 失败返回 None 直接平滑降级为普通纪要, 彻底废除传统 OCR 依赖.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
import requests
from dotenv import load_dotenv

logger = logging.getLogger("infra.vlm.agenda")

# 保证优先加载 demo 根目录 .env
_DEMO_ROOT = Path(__file__).resolve().parents[2]
if (_DEMO_ROOT / ".env").is_file():
    load_dotenv(_DEMO_ROOT / ".env", override=False)
load_dotenv(override=False)

# 默认服务配置（优先从环境变量/.env读取）
DEFAULT_VLM_ENDPOINT = os.getenv("VLM_AGENDA_ENDPOINT", "http://10.34.23.78:8888/predict")
DEFAULT_VLM_APP_ID = os.getenv("VLM_AGENDA_APPID", "cvcloud_classify")
DEFAULT_VLM_SIGN_KEY = os.getenv(
    "VLM_AGENDA_SIGNKEY", "7F04F5043B894BA598D66E03845F44C10C68B8E90D7347058771209D0B582A7B"
)
DEFAULT_VLM_BID = os.getenv("VLM_AGENDA_BID", "llm_texthawk_test")
DEFAULT_VLM_FLOWID = os.getenv("VLM_AGENDA_FLOWID", "llm_texthawk_test")
DEFAULT_VLM_TIMEOUT = int(os.getenv("VLM_AGENDA_TIMEOUT", "10"))

# 通用级议程识别提示词
AGENDA_VISION_PROMPT = """你是一名「会议议程与日程结构化解析专家」。请仔细识读图片中的文字、表格排版与时间流线，高保真提取会议议程清单，并严格按标准 JSON 格式输出。

【字段定义】：
1. theme: 会议总主题/大会名称（字符串，未提及填 null）
2. attendees: 全程主持人、大会主席、召集人或主要参会人员名单（字符串数组，提取纯真实姓名，无则填 []）
3. agenda_items: 实质性议题列表（对象数组，每个元素仅包含以下 4 项）：
   - seq: 序号（按出现顺序格式化为补零数字，如 "01"、"02"……）
   - title: 议题全称（保留完整的技术报告名称、方案标题或审议事项，不擅自缩写）
   - presenters: 汇报人/主讲人姓名列表（字符串数组，仅保留纯真实姓名，无明确汇报人填 []）
   - time_range: 预定起止时间范围（字符串，如 "10:00-10:30"，未注明填 null）

【提纯与清洗规约】：
1. 人名去噪提纯：严格提取纯净真实姓名，自动剥离工号、部门及职衔称谓（如教授、博士、总等）。
2. 研讨边界：聚焦具有实质研讨、汇报审议的议程；自动过滤签到、餐饮茶歇、交通等纯后勤环节。
3. 全量完整：按出现顺序完整提取所有独立研讨事项，严禁跳项、合并或截断。

【输出约束】：
只输出标准 JSON 文本，严禁包含 Markdown 代码块标记（```json ```）或任何前后导语。
若图片内容与会议/议程完全无关，请输出：{"theme": null, "attendees": [], "agenda_items": []}"""


def img2b64_string(path: str | Path) -> str:
    """读取图片，依据 EXIF 自动校正旋转方向，并输出标准 JPEG Base64 字符串。"""
    try:
        pil_img = Image.open(path).convert("RGB")
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ImageOps.exif_transpose fallback: %s", exc)
        pil_img = Image.open(path).convert("RGB")

    with io.BytesIO() as buf:
        pil_img.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")


def calc_sign(
    data: str,
    sign_key: str,
    query_param: dict[str, str],
    path: list[str],
    method: str,
    app_id: str,
    mode: str = "easy",
) -> tuple[int, str]:
    """生成 CloudSOA-HMAC-SHA256 请求签名。"""
    payload = "" if mode == "easy" else (data or "")

    query_str = ""
    for k, v in query_param.items():
        query_str += f"{k}={v}&"
    if query_str.endswith("&"):
        query_str = query_str[:-1]

    path_str = "".join(f"/{v}" for v in path)
    timestamp = int(time.time() * 1000)
    sign_str = f"{method}&{path_str}&{query_str}&{payload}&appid={app_id}&timestamp={timestamp}"

    sign_key_bytes = sign_key.encode("utf-8")
    sign_str_bytes = sign_str.encode("utf-8")
    sign = base64.b64encode(
        hmac.new(sign_key_bytes, sign_str_bytes, digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return timestamp, sign


def safe_load_json(results_list: list[str] | str) -> dict[str, Any]:
    """安全解析大模型返回的 JSON 文本，包含 Markdown 代码块剔除、栈级括号逆序闭合与容错提纯。"""
    full_str = "".join(results_list) if isinstance(results_list, list) else str(results_list)
    full_str = full_str.replace("\u200b", "").strip()

    if full_str.startswith("```"):
        full_str = re.sub(r"^```(?:json)?\s*", "", full_str, flags=re.I)
        full_str = re.sub(r"\s*```$", "", full_str)
        full_str = full_str.strip()

    try:
        parsed = json.loads(full_str)
        if isinstance(parsed, dict):
            return parsed
        return {"agenda_items": parsed if isinstance(parsed, list) else []}
    except json.JSONDecodeError:
        # 基于语法栈自动补齐未闭合的字符串与括号
        fixed_str = full_str
        in_string = False
        escape = False
        stack: list[str] = []

        for ch in fixed_str:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if ch in ("{", "["):
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()

        if in_string:
            fixed_str += '"'

        while stack:
            top = stack.pop()
            if top == "{":
                fixed_str += "}"
            elif top == "[":
                fixed_str += "]"

        try:
            parsed = json.loads(fixed_str)
            if isinstance(parsed, dict):
                return parsed
            return {"agenda_items": parsed if isinstance(parsed, list) else []}
        except Exception:
            m = re.search(r"(\{[\s\S]*\})", full_str)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
            logger.warning("[VLM] JSON 解析失败，原始文本: %s", full_str[:200])
            return {"parse_error": "JSON_INCOMPLETE", "raw_content": full_str}


class AgendaVisionClient:
    """视觉多模态大模型议程单结构化识别客户端 (纯 VLM 直连)."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        app_id: str | None = None,
        sign_key: str | None = None,
        b_id: str | None = None,
        flow_id: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url or os.getenv("VLM_AGENDA_ENDPOINT") or DEFAULT_VLM_ENDPOINT
        self.app_id = app_id or os.getenv("VLM_AGENDA_APPID") or DEFAULT_VLM_APP_ID
        self.sign_key = sign_key or os.getenv("VLM_AGENDA_SIGNKEY") or DEFAULT_VLM_SIGN_KEY
        self.b_id = b_id or os.getenv("VLM_AGENDA_BID") or DEFAULT_VLM_BID
        self.flow_id = flow_id or os.getenv("VLM_AGENDA_FLOWID") or DEFAULT_VLM_FLOWID
        timeout_val = timeout if timeout is not None else int(os.getenv("VLM_AGENDA_TIMEOUT", str(DEFAULT_VLM_TIMEOUT)))
        self.timeout = timeout_val

    def extract_agenda(
        self,
        image_input: str | Path | bytes,
        max_retries: int = 1,
        retry_delay: float = 1.0,
    ) -> dict[str, Any] | None:
        """从图片提取结构化议程 JSON. 失败时直接返回 None 平滑降级走普通纪要."""
        temp_file: Path | None = None
        if isinstance(image_input, bytes):
            import tempfile
            temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            temp.write(image_input)
            temp.close()
            temp_file = Path(temp.name)
            path_obj = temp_file
        else:
            path_obj = Path(image_input)

        if not path_obj.exists():
            logger.warning("[VLM] 待提取图片文件不存在: %s", image_input)
            return None

        try:
            for attempt in range(1, max_retries + 1):
                try:
                    status_code, result = self._predict_once(path_obj)
                    if status_code == 200 and isinstance(result, dict) and "parse_error" not in result:
                        items = result.get("agenda_items")
                        if isinstance(items, list) and len(items) > 0:
                            logger.info("[VLM] 议程识别成功: 包含 %d 项议题", len(items))
                            return result
                        logger.warning("[VLM] 识别结果未包含实质议题项, 准备降级")
                        return None

                except Exception as exc:  # noqa: BLE001
                    logger.warning("[VLM] 调用发生异常 (attempt=%d/%d): %s", attempt, max_retries, exc)

                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)

            logger.info("[VLM] 视觉议程识别未获得有效结果，平滑降级为普通纪要模式")
            return None
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def _predict_once(self, image_path: Path) -> tuple[int, dict[str, Any]]:
        uuid_str = str(int(time.time()))
        url = f"{self.endpoint_url}?bId={self.b_id}&flowId={self.flow_id}&uuId={uuid_str}"
        translocation_id = f"jlq_{uuid_str}"[:63]

        img_b64 = img2b64_string(image_path)
        params = {
            "data": {
                "translocationId": translocation_id,
                "promptId": "AGENDA_VISION",
                "inputFormat": "base64",
                "requestId": translocation_id,
                "image": img_b64,
                "prompt": AGENDA_VISION_PROMPT,
            },
            "meta": {
                "subId": "2",
                "bId": self.b_id,
                "flowId": self.flow_id,
                "uuId": uuid_str,
            },
            "version": "1.2",
        }

        params_str = json.dumps(params, indent=4, ensure_ascii=False)
        path = ["predict"]
        query = {"bId": self.b_id, "flowId": self.flow_id, "uuId": uuid_str}

        timestamp, sign = calc_sign(
            data=params_str,
            sign_key=self.sign_key,
            query_param=query,
            path=path,
            method="POST",
            app_id=self.app_id,
            mode="easy",
        )

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "text/event-stream;charset=UTF-8",
            "Authorization": (
                f'CLOUDSOA-HMAC-SHA256 appid={self.app_id}, timestamp={timestamp}, '
                f'signmode=easy, signature="{sign}"'
            ),
        }

        session = requests.Session()
        session.trust_env = False

        timeout_val = (min(3.0, float(self.timeout)), float(self.timeout))
        response = session.post(
            url,
            data=params_str.encode("utf-8"),
            headers=headers,
            timeout=timeout_val,
            verify=False,
        )

        if response.status_code != 200:
            return response.status_code, {
                "parse_error": f"HTTP_{response.status_code}",
                "raw_content": response.text[:500],
            }

        pattern = r"\$@START_PREFIX@#\{[\s\S]*?\}\$@END_SUFFIX@#"
        ret_list = re.findall(pattern, response.text)
        results: list[str] = []

        if ret_list:
            chunks = ret_list[:-1] if len(ret_list) > 1 else ret_list
            for ret in chunks:
                try:
                    payload = ret.replace("$@START_PREFIX@#", "").replace("$@END_SUFFIX@#", "")
                    res = json.loads(payload)
                    if isinstance(res, dict) and "text" in res and res["text"]:
                        results.append(res["text"])
                except Exception:
                    pass

        json_dict = safe_load_json(results if results else [response.text])
        return response.status_code, json_dict


def extract_agenda_from_image(image_input: str | Path | bytes) -> dict[str, Any] | None:
    """模块级便捷函数: 从图片路径或字节抽取结构化议程 JSON."""
    client = AgendaVisionClient()
    return client.extract_agenda(image_input)

