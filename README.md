# Meeting Agent Service (Lightweight)

自包含、零旧依赖的现代极简会议智能体服务。

## 核心特性

1. **接口职责严格对齐**：
   - **纪要任务**：`POST /api/agent/v1/stream`，NDJSON 极速流式事件直出，首字到达时延（TTFT）压入 1.5 秒内；
   - **待办任务**：`POST /api/agent/v1`，阻塞式返回带绝对时间的标准 JSON 数组。
2. **待办任务双态支持**：
   - 传会议时间 $\rightarrow$ 经过 Calendar 模块推导，产出并保存 `actions` + `actions_update`；
   - 未传时间 $\rightarrow$ 完全跳过 Calendar（0ms），产出并保存 `actions`。
3. **前置智能模板内建必选（无开关）**：
   - `template` 留空时自动检测；若识别出有效议题则候选集收敛为 20 个，否则为全量 29 个。
4. **视觉议程智能识别**：
   - 纯 VLM 视觉议程单抽取，识别失败或无有效议题时自动平滑降级为普通纪要。
5. **中英双语与后处理**：
   - 支持 `lang="zh"` 与 `lang="en"`，自动匹配中英文提示词规范与中英文模板；
   - 纯正则轻量后处理，防御大模型围栏与方括号指令残留。
6. **用户级目录隔离落盘**：
   - 产物按用户严格隔离至 `data/{user_id}/output/{request_id}/`，纪要仅保存 `minutes.md`，待办仅保存 `actions.json`。
7. **隔离式英文日志系统**：
   - 外挂非侵入式 `LoggingMiddleware`，全量 `logs/service.log` 与核心诊断 `logs/diag.log` 双文件自动轮转。
8. **批量自动化评测**：
   - 内置 `api_test/test_stream.py` 与 `test.py`，支持基于 Excel 的批量流式/同步跑测与时延写回。

---

## 快速开始

### 1. 安装依赖
```bash
pip install fastapi uvicorn requests openpyxl pydantic pytest
```

### 2. 配置环境
复制 `.env.example` 为 `.env` 并填写 API Key：
```bash
cp .env.example .env
```
配置示例：
```env
LLM_BACKEND=http
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```
若使用私有化 vLLM 服务器：
```env
LLM_BACKEND=vllm
LLM_VLLM_BASE_URL=http://127.0.0.1:8000/v1
LLM_VLLM_API_KEY=EMPTY
LLM_VLLM_MODEL=deepseek-v4-flash-0731
```

### 3. 启动服务
```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. 运行测试
```bash
pytest tests/ -v
```

---

## 接口调用契约（TaskRequest 标准格式）

### 请求体字段说明

```json
{
  "task": "minutes",
  "texts": {
    "transcript": "会议转写正文...",
    "keypoints": "",
    "notes": "",
    "vision_info": "",
    "actions_text": ""
  },
  "docs": [
    "小艺语音技术委员会.png"
  ],
  "extra": {
    "template": "general_minutes",
    "time": "2026/11/13 14:00",
    "agenda_plan": null
  },
  "lang": "zh"
}
```

* **Headers 约定**：
  * `X-User-Id`：用户标识（如 `1`）。`docs` 中的文件名会自动映射至 `data/{user_id}/docs/{filename}`；产物落盘至 `data/{user_id}/output/{request_id}/`。
  * `X-Request-Id`：全局链路追踪唯一 ID。
* **`texts` 字段说明**：
  * `transcript`：会议语音转写全文（纪要或待办的核心输入）；
  * `actions_text`：仅待办（`task="actions"`）消费的用户候选待办，纪要任务自动物理隔离；
  * `keypoints` / `notes` / `vision_info`：辅助线索与术语参考材料。
* **`extra` 字段说明**：
  * `template`：模板名称（留空自动智能分类）；
  * `time`：会议召开时间（待办传时间走 Calendar 回填，未传则跳过 Calendar）；
  * `agenda_plan`：直接注入结构化议程 JSON。

