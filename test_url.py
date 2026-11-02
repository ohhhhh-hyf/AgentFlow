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
from openpyxl import Workbook

os.environ['http_proxy'] = ""
os.environ['https_proxy'] = ""

proxy_vars = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
]

for key in proxy_vars:
    os.environ.pop(key, None)

print({
    key: value
    for key, value in os.environ.items()
    if "proxy" in key.lower()
})


def base64_to_image(base64_string, out_name):
    imgdata = base64.b64decode(base64_string)
    image = Image.open(io.BytesIO(imgdata))
    image.save(out_name)


# 图片转base64
def img2b64_string(path: str) -> str:
    # with open(path, "rb") as f:
    #     img_binary = f.read()
    # img_b64 = base64.b64encode(img_binary).decode("utf-8")
    PIL_img = Image.open(path).convert("RGB")
    PIL_img = ImageOps.exif_transpose(PIL_img)
    # PIL_img.show("test")
    # PIL_img.save("./images/IMG_20250706_175141_zhengtu.jpg")
    with io.BytesIO() as f:
        PIL_img.save(f, format='JPEG')
        img_b64 = base64.b64encode(f.getvalue()).decode('utf-8')

    return img_b64


# 图片做一个图片旋转矫正转base64
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
    except:
        PIL_img = Image.open(path).convert("RGB")

    with io.BytesIO() as f:
        PIL_img.save(f, format='JPEG')
        img_b64 = base64.b64encode(f.getvalue()).decode('utf-8')
    return img_b64


# 签名授权
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
    print('timestamp', timestamp)
    sign_str = "{}&{}&{}&{}&appid={}&timestamp={}".format(method, path_str, query_str, payload, app_id, timestamp)
    sign_key = sign_key.encode('utf-8')
    sign_str = sign_str.encode('utf-8')
    sign = base64.b64encode(hmac.new(sign_key, sign_str, digestmod=hashlib.sha256).digest()).decode("utf-8")
    return timestamp, sign


def get_ocr_response(file):
    params = {
        "data": {
            # "requestId": "1234",
            # "deviceId": "VCE-AL00",
            # "timeZone": "GMT+08:00",
            # "time": "1679587208075",
            # "language": "zh_CN",
            # "callingUid": "hivoice",
            # "deviceName": "ALP-AL00",
            # "romVer": "VCE-AL00 9.0.1.131(C00E143R1P17log)",
            # "serviceType": "0",
            # # "inputFormat": "byteFileId",
            # "sceneType": "order",
            # "imageUrl": "123.jpg",
            # "image": img2b64_string(file["path"]),

            "requestId": f"table_extractor{time.strftime('%Y%m%d%H%M%S')}",
            "deviceId": "grey",
            "callingUid": "KPItest",
            "osType": "2",
            "osVer": "osVer",
            "deviceName": "deviceName",
            "packageName": "packageName",
            "emuiVer": "EMUI8.0",
            "romVer": "romVer",
            "appVer": "appVer",
            "cpuModel": "cpuModel",
            "cpuVer": "cpuVer",
            "timeZone": "timeZone",
            "time": "time",
            "language": "language",
            "ext": "ext",
            "serviceType": 1,
            "textShape": "",
            "ocrLanguage": "0",
            "resize": "false",
            "image": img2b64_string(file)

        },
        "meta": {
            "subId": "2",
            # "bId": "test_focusocr_fun",
            # "flowId": "test_focusocr_fun",

            "bId": "test_focusocr_perf",
            "flowId": "test_focusocr_perf",

            "uuId": "1500627771776"
        },
        "version": "1.2"
    }

    path = ['service']
    signkey = 'FABF20DE27A11E763B7C0EC8E6F8F9C4'
    method = 'POST'
    appid = 'backend'
    query = {}
    mode = 'easy'
    timestamp, sign = calc_sign(json.dumps(params), signkey, query, path, method, appid, mode)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'CLOUDSOA-HMAC-SHA256 appid={appid}, timestamp={timestamp}, signmode=easy, signature="{sign}"'
    }
    # url = "http://10.32.213.89:8080/service"
    url = "http://10.33.111.223:8080/service"
    response = requests.request(method, url, data=json.dumps(params), headers=headers, timeout=120)
    result = response.json()
    ocr_result = json.loads(result["result"]["content"][0])["text"]
    return ocr_result


def mm_visit_mep_sse(
        image_path='',

        bId="dev_kie_base_qwen3vl_8b",
        flowId="dev_kie_base_qwen3vl_8b",

        prompt_id="",
        slot_prompt='',
        prompt="",
        target=""
):
    # bId = "dev_kie_stream"
    # flowId = "dev_kie_stream"
    
    bId = "llm_texthawk_test"
    flowId = "llm_texthawk_test"
    ocr_result = {}
    # ocr_results = get_ocr_response(image_path)
    # if ocr_results:
    #     ocr_result = ocr_results[0]

    uuId = str(int(time.time()))
    # url = f"http://10.41.1.17:8080/predict?bId={bId}&flowId={flowId}&uuId={uuId}"
    url = f"http://10.34.23.78:8888/predict?bId={bId}&flowId={flowId}&uuId={uuId}"
    print(url)
    print("translocationId len is " + str(len(f'testcase_{uuId}')))

    translocation_id = f'jlq_{uuId}'[:63]
    print("translocation_id", translocation_id)
    params = {
        "data": {
            "translocationId": translocation_id,
            "promptId": prompt_id,
            "inputFormat": "base64",
            "requestId": translocation_id,
            "image": img2b64_string(image_path),
            # "ocrResponse": ocr_result,
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


    params = json.dumps(params, indent=4, ensure_ascii=False)

    path = ['predict']
    signkey = '7F04F5043B894BA598D66E03845F44C10C68B8E90D7347058771209D0B582A7B'
    method = 'POST'
    appid = 'cvcloud_classify'
    # appid = 'hiai'
    # signkey = 'CB663177458347D19A07D03E7728C878D1C413811F0C4526AEDD26DDD4334980'
    query = {
        "bId": bId,
        "flowId": flowId,
        "uuId": uuId
    }
    mode = 'easy'
    timestamp, sign = calc_sign(str(params), signkey, query, path, method, appid, mode)
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "text/event-stream;charset=UTF-8",
        'Authorization': f'CLOUDSOA-HMAC-SHA256 appid={appid}, timestamp={timestamp}, signmode=easy, signature="{sign}"'
    }
    response = requests.request(
        method, url, data=params.encode('utf-8'), headers=headers, timeout=120,
        proxies=None, verify=False, stream=False
    )
    print("mep status_code =========" + str(response.status_code))
    import re
    PATTERN = "\$@START_PREFIX@#\{[\s\S]*?\}\$@END_SUFFIX@#"
    ret_list = re.findall(PATTERN, response.text)
    results = []
    for ret in ret_list[:-1]:
        res = json.loads(ret.replace("$@START_PREFIX@#", "").replace("$@END_SUFFIX@#", ""))
        # print("-----多模接口结果----- \n" + str(res) + "\n--------------------\n")
        # print('-' * 66)
        text = res['text']
        results.append(text)
        # small_anwers.append(res.get('calcText', ''))
    print(results)
    print("------------- final ori results -------------", )
    json_dict = safe_load_json(results)
    print(''.join(results).replace('\u200b', ""))

    return response.status_code, json_dict


def safe_load_json(results_list):
    # 1. 合并并清理不可见字符
    full_str = ''.join(results_list).replace('\u200b', "").strip()

    try:
        # 尝试标准解析
        return json.loads(full_str)
    except json.JSONDecodeError:
        # 2. 如果解析失败，尝试简单修复末尾（补齐引号和括号）
        fixed_str = full_str
        if fixed_str.count('"') % 2 != 0:
            fixed_str += '"'

        # 补齐层级大括号
        braces_needed = fixed_str.count('{') - fixed_str.count('}')
        if braces_needed > 0:
            fixed_str += '}' * braces_needed

        try:
            return json.loads(fixed_str)
        except:
            # 3. 如果还是失败，说明格式彻底乱了，返回原始字符串以供人工审计
            # 在评测中，这种通常记录为 "Invalid JSON"
            return {
                "parse_error": "JSON_INCOMPLETE",
                "raw_content": full_str
            }


def upload(file_path: str) -> str:
    url = "http://10.34.23.79:8098/nsp/upload/image"

    file_id = os.path.basename(file_path)
    files = {
        'file': (file_id, open(file_path, 'rb'))
    }
    headers = {}
    response = requests.post(url, headers=headers, files=files)
    print(response)
    return file_id


if __name__ == '__main__':
    # image_path = "./test.jpg"

    # 测试：需要自己传入prompt
    prompt_id = "TEST_PROMPT"
    # image_path = fr"C:/Users/s00954045/Desktop/cases/带议题会议/商评1.png"
    # image_path = fr"C:/Users/s00954045/Desktop/04-10.PNG"
    image_path = fr"D:\edge_download\image_110220509659740.png"
    mm_visit_mep_sse(image_path=image_path, prompt_id=prompt_id)
