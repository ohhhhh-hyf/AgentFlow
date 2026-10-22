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
            "prompt": """你是一名「会议议程与日程结构化解析专家」。请仔细识读图片中的文字、表格排版与时间流线，高保真提取会议议程清单，并严格按标准 JSON 格式输出。

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
若图片内容与会议/议程完全无关，请输出：{"theme": null, "date_time": null, "attendees": [], "agenda_items": []}""",
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