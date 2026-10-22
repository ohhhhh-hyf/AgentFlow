#!/usr/bin/env python
# -*- coding:utf-8 -*-
import io
import os
from PIL import Image, ImageOps
import time
import base64
import json
import hmac
import hashlib
import requests

os.environ['http_proxy'] = ""
os.environ['https_proxy'] = ""

proxy_vars = [
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
]
for key in proxy_vars:
    os.environ.pop(key, None)


def base64_to_image(base64_string, out_name):
    imgdata = base64.b64decode(base64_string)
    image = Image.open(io.BytesIO(imgdata))
    image.save(out_name)


def img2b64_string(path: str) -> str:
    PIL_img = Image.open(path).convert("RGB")
    PIL_img = ImageOps.exif_transpose(PIL_img)
    with io.BytesIO() as f:
        PIL_img.save(f, format='JPEG')
        img_b64 = base64.b64encode(f.getvalue()).decode('utf-8')
    return img_b64


def img_rotage2b64_string(path):
    try:
        PIL_img = Image.open(path).convert("RGB")
        if hasattr(PIL_img, 'getexif'):
            exif = PIL_img.getexif()
            orientation_key = 274
            if exif is not None and orientation_key in exif.keys():
                orientation = exif[orientation_key]
                if orientation == 6:
                    PIL_img = PIL_img.rotate(-90, expand=True)
                elif orientation == 8:
                    PIL_img = PIL_img.rotate(90, expand=True)
                elif orientation == 3:
                    PIL_img = PIL_img.rotate(180, expand=True)
                elif orientation == 2:
                    PIL_img = PIL_img.transpose(Image.FLIP_LEFT_RIGHT)
                elif orientation == 5:
                    PIL_img = PIL_img.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
                elif orientation == 7:
                    PIL_img = PIL_img.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
                elif orientation == 4:
                    PIL_img = PIL_img.rotate(180, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
    except Exception:
        PIL_img = Image.open(path).convert("RGB")

    with io.BytesIO() as f:
        PIL_img.save(f, format='JPEG')
        img_b64 = base64.b64encode(f.getvalue()).decode('utf-8')
    return img_b64


def calc_sign(data, sign_key, query_param, path, method, app_id, mode):
    payload = ""
    if data is not None and data != "" and len(data) > 0:
        if mode == 'easy':
            payload = ''
        else:
            payload += data
    query_str = ""
    path_str = ""
    for k, v in query_param.items():
        query_str += "{}={}&".format(k, v)
    query_str = query_str[:-1]

    for v in path:
        path_str += "/{}".format(v)
    timestamp = int(time.time() * 1000)
    sign_str = "{}&{}&{}&{}&appid={}&timestamp={}".format(method, path_str, query_str, payload, app_id, timestamp)
    sign_key = sign_key.encode('utf-8')
    sign_str = sign_str.encode('utf-8')
    sign = base64.b64encode(hmac.new(sign_key, sign_str, digestmod=hashlib.sha256).digest()).decode("utf-8")
    return timestamp, sign


def safe_load_json(results_list):
    full_str = ''.join(results_list).replace('\u200b', "").strip()
    try:
        return json.loads(full_str)
    except json.JSONDecodeError:
        fixed_str = full_str
        if fixed_str.count('"') % 2 != 0:
            fixed_str += '"'
        braces_needed = fixed_str.count('{') - fixed_str.count('}')
        if braces_needed > 0:
            fixed_str += '}' * braces_needed
        brackets_needed = fixed_str.count('[') - fixed_str.count(']')
        if brackets_needed > 0:
            fixed_str += ']' * brackets_needed
        try:
            return json.loads(fixed_str)
        except Exception:
            return {
                "parse_error": "JSON_INCOMPLETE",
                "raw_content": full_str
            }


def mm_visit_mep_sse(image_path='', prompt_id="", **kwargs):
    bId = "llm_texthawk_test"
    flowId = "llm_texthawk_test"

    uuId = str(int(time.time()))
    url = f"http://10.34.23.78:8888/predict?bId={bId}&flowId={flowId}&uuId={uuId}"
    translocation_id = f'jlq_{uuId}'[:63]

    params = {
        "data": {
            "translocationId": translocation_id,
            "promptId": prompt_id,
            "inputFormat": "base64",
            "requestId": translocation_id,
            "image": img2b64_string(image_path),
            "prompt": """你是一名会议信息提取助手。请仔细识别图片中的文字内容，从中提取会议关键信息，并严格按 JSON 格式输出。

需要提取的字段如下：

- topic：会议主题，代表整个会议的大主题
- time：会议时间，尽量还原为“YYYY-MM-DD HH:MM”格式；如果无法确定完整时间，可保留图片中的原始描述；若图片中未提及，可保留为空
- participants：参会人员列表，应包含分享人、参与人等，字符串数组，
- agenda_items：会议议题列表，字符串数组，可能包含多个议题，若无具体议题则保留为空，会议主题不作为具体议题，除非明确在议题表中列出

输出要求：

1. 只输出标准 JSON，不要输出任何解释、推理过程、Markdown 代码块标记或其他多余文字。
2. 如果某个字段在图片中无法确认，请设为 null 或空数组，不要编造。
4. time 字段如果包含多个时间描述，可保留最明确的会议开始时间。
5. 如果图片内容与会议无关，请输出：{"topic": null, "time": null, "participants": [], "agenda_items": []}""",
        },
        "meta": {
            "subId": "2",
            "bId": bId,
            "flowId": flowId,
            "uuId": uuId
        },
        "version": "1.2"
    }

    params_str = json.dumps(params, indent=4, ensure_ascii=False)
    path = ['predict']
    signkey = '7F04F5043B894BA598D66E03845F44C10C68B8E90D7347058771209D0B582A7B'
    method = 'POST'
    appid = 'cvcloud_classify'
    query = {"bId": bId, "flowId": flowId, "uuId": uuId}
    mode = 'easy'

    timestamp, sign = calc_sign(str(params_str), signkey, query, path, method, appid, mode)
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "text/event-stream;charset=UTF-8",
        'Authorization': f'CLOUDSOA-HMAC-SHA256 appid={appid}, timestamp={timestamp}, signmode=easy, signature="{sign}"'
    }
    response = requests.request(
        method, url, data=params_str.encode('utf-8'), headers=headers,
        timeout=120, proxies=None, verify=False, stream=False
    )

    import re
    PATTERN = r"\$@START_PREFIX@#\{[\s\S]*?\}\$@END_SUFFIX@#"
    ret_list = re.findall(PATTERN, response.text)
    results = []
    for ret in ret_list[:-1]:
        res = json.loads(ret.replace("$@START_PREFIX@#", "").replace("$@END_SUFFIX@#", ""))
        results.append(res['text'])

    json_dict = safe_load_json(results)
    return response.status_code, json_dict


if __name__ == '__main__':
    prompt_id = "TEST_PROMPT"
    image_path = fr"D:\Agentdemo\data\1\agenda\test6\学术年会.png"

    status, result = mm_visit_mep_sse(image_path=image_path, prompt_id=prompt_id)

    # 只输出最终 JSON 结果（一行，中文正常显示）
    print(json.dumps(result, ensure_ascii=False))


#输出示例：{"topic": null, "time": null, "participants": ["上海交通大学 俞凯教授", "清华大学 高虹教授", "中国科学院自动化研究所 陶建华研究员", "中国科学院声学研究所 颜永红研究员", "百度时代网络技术（北京）有限公司 贾磊博士", "清华大学 郑方教授", "上海交通大学 俞凯教授"], "agenda_items": ["开幕式：领导致辞 & 合影", "语音模仿与鉴别", "茶歇", "声学所语音识别最新进展及应用", "百度语音在建模技术、多模态和芯片方面的最新进展", "声纹识别应用的技术挑战", "语音合成中的自然韵律多样性建模"]}    