"""infra.vlm.agenda_client -- 视觉多模态大模型议程识别客户端。

封装内部多模态视觉服务调用：
1. CloudSOA HMAC-SHA256 签名鉴权；
2. 图片 Base64 转码与 EXIF 方向自适应校正；
3. SSE 流式响应解析与 JSON 容错提纯；
4. 最大 3 次指数退避重试（网络波动/超时/服务异常安全捕获，失败平滑降级）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any

from PIL import Image, ImageOps
import requests

logger = logging.getLogger("agentflow.infra.vlm.agenda")

# 默认服务配置（支持环境变量覆盖）
DEFAULT_VLM_ENDPOINT = os.getenv("VLM_AGENDA_ENDPOINT", "http://10.34.23.78:8888/predict")
DEFAULT_VLM_APP_ID = os.getenv("VLM_AGENDA_APPID", "cvcloud_classify")
DEFAULT_VLM_SIGN_KEY = os.getenv(
    "VLM_AGENDA_SIGNKEY", "7F04F5043B894BA598D66E03845F44C10C68B8E90D7347058771209D0B582A7B"
)
DEFAULT_VLM_BID = os.getenv("VLM_AGENDA_BID", "llm_texthawk_test")
DEFAULT_VLM_FLOW_ID = os.getenv("VLM_AGENDA_FLOWID", "llm_texthawk_test")
DEFAULT_VLM_TIMEOUT = int(os.getenv("VLM_AGENDA_TIMEOUT", "60"))

# 泛化通用级议程识别提示词
AGENDA_VISION_PROMPT = """你是一名「会议议程与日程结构化解析专家」。请仔细识读图片中的文字、表格排版与时间流线，高保真提取会议议程清单，并严格按标准 JSON 格式输出。

【字段定义】：
1. theme: 会议总主题/大会名称（字符串，未提及填 null）
2. date_time: 会议举办日期或起止时间（字符串，未提及填 null）
3. attendees: 全程主持人、大会主席或主要参会人员姓名列表（字符串数组，提取纯姓名，无则填 []）
4. agenda_items: 实质性议题列表（对象数组，每个元素包含）：
   - seq: 序号（按出现顺序格式化为补零数字，如 "01"、"02"……）
   - title: 议题全称（保留完整的技术报告名称、方案标题或审议事项，不擅自缩写）
   - presenters: 汇报人/主讲人姓名列表（字符串数组，仅保留纯真实姓名，无明确汇报人填 []）
   - time_range: 预定起止时间（字符串，未注明填 null）
   - duration: 预定时长（字符串，未注明填 null）

【提纯与清洗规约】：
1. 人名去职化提纯：严格提取纯净真实姓名，自动剥离所属机构、所属部门以及头衔职称（如教授、研究员、博士、主任、工程师、专家、顾问、总等称谓），仅保留人名主体。
2. 研讨与后勤边界：聚焦提炼具有实质研讨、方案汇报、业务审议、主旨演讲或正式仪式的有效议程；自动过滤签到、餐饮茶歇、集合乘车、休会漫步等纯事务性后勤环节。
3. 全量完整性规约：依序完整提取所有独立研讨事项，不因缺少序号标号或排版居于末尾而遗漏，严禁跳项、合并或截断。

【输出约束】：
只输出标准 JSON 文本，严禁包含 Markdown 代码块标记（```json ```）、前言、解释或任何多余文字。
若图片内容与会议/议程完全无关，请输出：{"theme": null, "date_time": null, "attendees": [], "agenda_items": []}"""


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
    payload = ""
    if data is not None and data != "" and len(data) > 0:
        if mode == "easy":
            payload = ""
        else:
            payload += data

    query_str = ""
    for k, v in query_param.items():
        query_str += f"{k}={v}&"
    if query_str.endswith("&"):
        query_str = query_str[:-1]

    path_str = ""
    for v in path:
        path_str += f"/{v}"

    timestamp = int(time.time() * 1000)
    sign_str = f"{method}&{path_str}&{query_str}&{payload}&appid={app_id}&timestamp={timestamp}"

    sign_key_bytes = sign_key.encode("utf-8")
    sign_str_bytes = sign_str.encode("utf-8")
    sign = base64.b64encode(
        hmac.new(sign_key_bytes, sign_str_bytes, digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    return timestamp, sign


def safe_load_json(results_list: list[str] | str) -> dict[str, Any]:
    """安全解析大模型返回的 JSON 文本，包含 Markdown 代码块剔除、栈级括号闭合补齐与容错提纯。"""
    if isinstance(results_list, list):
        full_str = "".join(results_list)
    else:
        full_str = str(results_list)

    full_str = full_str.replace("\u200b", "").strip()

    # 剔除可能的 ```json ... ``` 标记
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

        # 逆序闭合栈中的开括号
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
            # 正则贪婪匹配提取最外层 {...}
            m = re.search(r"(\{[\s\S]*\})", full_str)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
            logger.warning("[VLM] JSON 解析失败，原始文本: %s", full_str[:200])
            return {
                "parse_error": "JSON_INCOMPLETE",
                "raw_content": full_str,
            }


class AgendaVisionClient:
    """视觉多模态大模型议程单结构化识别客户端。"""

    def __init__(
        self,
        endpoint_url: str = DEFAULT_VLM_ENDPOINT,
        app_id: str = DEFAULT_VLM_APP_ID,
        sign_key: str = DEFAULT_VLM_SIGN_KEY,
        b_id: str = DEFAULT_VLM_BID,
        flow_id: str = DEFAULT_VLM_FLOW_ID,
        timeout: int = DEFAULT_VLM_TIMEOUT,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.app_id = app_id
        self.sign_key = sign_key
        self.b_id = b_id
        self.flow_id = flow_id
        self.timeout = timeout

    def extract_agenda(
        self,
        image_path: str | Path,
        prompt_id: str = "AGENDA_VISION",
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> dict[str, Any] | None:
        """从图片提取结构化议程 JSON，具备最多 max_retries 次指数退避重试。

        Returns:
            dict: 成功时返回议程 JSON（至少包含 agenda_items 键且格式合法）；
            None: 经过 max_retries 次重试后仍失败时返回 None，供调用方安全降级至传统 OCR。
        """
        path_obj = Path(image_path)
        if not path_obj.exists():
            logger.warning("[VLM] 待提取图片文件不存在: %s", image_path)
            return None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "[VLM] 发起议程视觉识别 (尝试 %d/%d): %s",
                    attempt,
                    max_retries,
                    path_obj.name,
                )
                status_code, result = self._predict_once(path_obj, prompt_id=prompt_id)
                if status_code == 200 and isinstance(result, dict) and "parse_error" not in result:
                    items = result.get("agenda_items")
                    logger.info(
                        "[VLM] 议程识别成功 (尝试 %d/%d): 包含 %d 项议题",
                        attempt,
                        max_retries,
                        len(items) if isinstance(items, list) else 0,
                    )
                    return result

                error_hint = result.get("parse_error") if isinstance(result, dict) else f"HTTP {status_code}"
                logger.warning(
                    "[VLM] 尝试 %d/%d 返回异常响应: %s",
                    attempt,
                    max_retries,
                    error_hint,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[VLM] 尝试 %d/%d 发生网络或通信异常: %s",
                    attempt,
                    max_retries,
                    exc,
                )

            if attempt < max_retries:
                sleep_secs = retry_delay * attempt
                logger.info("[VLM] 等待 %.1f 秒后发起下一次重试...", sleep_secs)
                time.sleep(sleep_secs)

        logger.warning(
            "[VLM] 议程视觉识别已达到最大重试次数 (%d)，返回 None 以平滑降级至传统 OCR",
            max_retries,
        )
        return None

    def _predict_once(self, image_path: Path, prompt_id: str) -> tuple[int, dict[str, Any]]:
        """执行单次 HTTP SSE 预测请求并解析流式数据。"""
        uuid_str = str(int(time.time()))
        url = (
            f"{self.endpoint_url}?bId={self.b_id}&flowId={self.flow_id}&uuId={uuid_str}"
        )
        translocation_id = f"jlq_{uuid_str}"[:63]

        img_b64 = img2b64_string(image_path)
        params = {
            "data": {
                "translocationId": translocation_id,
                "promptId": prompt_id,
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

        # 禁用环境变量代理，防止内网请求被外部代理拦截
        session = requests.Session()
        session.trust_env = False

        response = session.post(
            url,
            data=params_str.encode("utf-8"),
            headers=headers,
            timeout=self.timeout,
            verify=False,
        )

        if response.status_code != 200:
            return response.status_code, {
                "parse_error": f"HTTP_{response.status_code}",
                "raw_content": response.text[:500],
            }

        # 解析 SSE 数据帧
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
