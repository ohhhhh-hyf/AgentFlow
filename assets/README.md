# assets/ —— 运行时数据资产

这里放**代码之外的、运行时直接读取的数据**（不含逻辑）。目前只有：

| 目录 | 内容 | 读取方 |
|---|---|---|
| `profiles/` | 视角画像注册表：`object.json`（客观全员）+ 6 个职业模板（algorithm_engineer / client_manager / developer / product_manager / project_manager / tester） | `tools/core/profiles.py`（`SHARED_PROFILE_DIR`）；`extra.profile` 传职业模板名时按名加载 |

约定：
- 文件名即 `extra.profile` 的取值（`.json` 后缀可省），改名等于改对外契约。
- 每个画像必须含非空 `name`；`persona_type: "role_template"` 表示职业模板（真人档案走 `data/{X-User-Id}/user.json`，不放这里）。
- 新增职业模板：放一个 json 即可（字段见现有模板或根 `api.md` 的 `user.json` 小节），无需改代码。
