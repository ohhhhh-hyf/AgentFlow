# 数据存储规范与物理隔离说明 (Data Storage & Isolation)

本目录为 AgentFlow 多租户数据持久化根目录。系统严格贯彻**多租户物理沙箱隔离原则**，禁止任何越权穿透或向公共无主目录回退。

## 目录分层结构

```text
data/
├── {user_id}/                    # 严格按用户 ID（如 X-User-Id）隔离的物理领地
│   ├── docs/                     # 用户输入的原始素材文件（待解析文本、转录稿、议程单图片等）
│   ├── output/{request_id}/      # 每次调用的专属生成结果（result.md, minutes.html, mindmap.png）
│   ├── knowledge/                # 用户专属知识库
│   │   ├── chromadb/             # 用户专有 ChromaDB 向量库物理存储
│   │   ├── catalogs/             # 用户学科/领域知识目录树 JSON
│   │   └── ocr_archives/         # OCR 归档与历史快照
│   ├── memory/                   # 跨会话长期演进记忆
│   │   ├── meeting/              # 会议状态机 (sessions.json) 与场次事实记录
│   │   └── notes/                # 个人知识图谱增量演进数据
│   └── profile/                  # 用户的个性化档案（user.json）
└── monitor/                      # 系统级脱敏运行指标（耗时、Token 消耗统计日志）
```

## 安全规范与隔离纪律

1. **绝对路径约束**：所有读写操作均须经由 `infra.storage.path_resolver.StoragePathResolver` 解析，严禁直接通过字符串拼接访问用户路径。
2. **防路径穿越**：`user_id` 与文件名中严禁包含 `..`、`/`、`\\` 等非法字符；解析后的物理路径必须严格位于对应的用户沙箱之内。
3. **零跨租户回退**：当用户目录中未找到目标文件时，系统将直接抛出明确的 404 错误，严厉杜绝回退至公共根目录的越权行为。
