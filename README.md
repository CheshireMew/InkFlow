# InkFlow

InkFlow 是一个本地优先的写作工作台。它把原始要求、素材、参考案例、当前提示词、模型配置、写作交接、生成运行和最终稿放在同一条可追溯链路里。它能准确回答“这次用了什么输入和运行条件”；只有受控规则对比才用于判断写作规则造成的差异。

旧版配方、翻译和通用工具箱已经退出活动代码，保存在 `archive/`。当前运行时只有一套写作架构，Web 与 CLI 共用同一个 Python 服务和 SQLite 数据库。

## 完整写作链路

正式写作分为五个可见阶段：

1. 保存用户的原始写作要求，粘贴文本、读取本地文件或抓取网页正文。
2. 使用当前提示词净化材料，再按写作技巧和成品形式选择参考案例与开头钩子。
3. 审阅交接文件。交接只包含原始要求、净化后材料、参考正文、钩子正文和其它实际输入；来源路径与链接留在本地来源记录中。任何修改都会生成新版本并撤销批准。
4. 批准交接后，进行单篇生成、一次调用生成五篇，或通过同一个内置 API 模型配置，用正好五版不同写作规则做五次串行受控对比。外部 Agent 可执行单篇和批量生成，但不参与受控对比。
5. 在结果工作区并排阅读、筛选、接受或拒绝、复制、导出和人工修改。运行成功的结果默认“未审阅”；人工修改保存为不可变的新版本，不覆盖模型原稿，并撤销此前的接受或拒绝决定。

材料准备、参考选择和成品生成各有独立的可编辑提示词。生成阶段的系统提示词只负责稳定的运行与事实边界，`writing_rules.body` 是唯一创作方法；规则对比只替换它。每次任务都保存当时真正发给模型的完整提示词快照、写作规则快照和非敏感模型配置快照，因此以后修改当前配置不会篡改历史运行。

## 提示词文件与完整日志

所有会发送给 AI 的固定文字都有实体文件：阶段提示词和 GitHub 写作资料位于 `src/inkflow/prompt_files/seeds/`，防治 AI 味的当前与历史资料位于 `src/inkflow/prompt_files/library/ai_flavor/`，连接测试位于 `src/inkflow/prompt_files/operations/`，结构化输出约束位于 `src/inkflow/prompt_files/contracts/`。运行时只读取数据目录 `prompts/current/` 下每个阶段唯一的当前 JSON 文件，数据库只索引文件位置、内容指纹和来源。

AI 调用没有修改提示词的入口。每个阶段在数据目录的 `prompts/current/` 中只有一个当前提示词文件，用户可以在 Prompt Studio 保存，也可以直接手动编辑该 JSON 文件；两种方式都会直接覆盖当前内容，不产生版本记录。任务和实验在启动时保存完整提示词快照，因此后来覆盖当前提示词不会改变旧任务或旧结果。

每次 AI 交互都经过同一条结构化日志边界。请求事件完整记录系统提示词、用户提示词和 JSON Schema；响应事件记录模型正文、提供方原始响应、用量、请求 ID、结束原因、耗时与失败信息。JSONL 同时写入控制台和数据目录的 `logs/ai-interactions.jsonl`，也可从 `/api/diagnostics/ai-audit` 下载；内置 API、提供方连接测试和外部执行器领取/提交任务不会绕过这条边界。

仓库已经保存 100x-learning 当前的 GitHub 单项目与项目清单提示词、Git 中 27 个历史版本，以及 63 份防治 AI 味相关实体：4 份当前组合或原文、57 份 Git 历史和 2 份归档旧版。正向自然表达原则仍作为可审阅资料保存在 `src/inkflow/prompt_files/components/general-writing-naturalness.txt`，但不会自动混入生成运行合同或掩盖当前写作规则。只有用户明确要求重新同步时才运行：

```powershell
python scripts/sync_100x_writing_prompts.py --source E:\Work\100x-learning
```

## 工作台

左侧固定导航包含项目、提示词、参考库和模型配置。项目内部依次提供要求与材料、准备交接、审阅交接、生成与对比、结果工作区。界面使用 Hash 路由，刷新、前进和后退都能保持当前项目与阶段。

运行开发版本需要 Python 3.10+ 与 Node.js 20+：

```powershell
python -m pip install -e ".[dev]"
Push-Location frontend
npm ci
npm run build
Pop-Location
inkflow app
```

`inkflow app` 默认在 `127.0.0.1` 上选择一个空闲随机端口，并把实际地址输出到终端后打开浏览器。可以用 `--port` 固定端口，或用 `--no-open` 禁止自动打开：

```powershell
inkflow app --port 8765 --no-open
inkflow --data-dir D:\InkFlowData app
```

数据目录遵循 Windows、macOS 和 Linux 的系统约定，也可以通过 `--data-dir` 或 `INKFLOW_DATA_DIR` 显式指定。`inkflow doctor` 会检查数据库版本、WAL、外键和前端资源。

## 参考库

参考案例和开头钩子可以在工作台中维护，也可以从 100x-learning 的现有知识库导入。导入只读取源目录；导入完成后，InkFlow 数据库是运行时唯一来源。

```powershell
inkflow reference import-100x "E:\Work\100x-learning\System Knowledge"
inkflow reference list --kind case
```

相同正文不能同时充当案例和钩子。重复正文会被跳过并出现在导入报告中，重复执行不会产生重复数据或重复规则版本。

## 外部 Agent 执行

InkFlow 不依赖 Codex CLI，也不反向调用任何 Agent。外部执行器主动领取原子租约任务，把 `payload.prompt_snapshot.system_prompt` 和 `payload.prompt_snapshot.user_prompt` 交给实际会话，并严格按 `payload.result_schema` 回传 JSON。外部运行不是受控实验；生成结果必须自行声明真实运行时、模型、上下文状态和工具，工作台会显示这组运行身份：

```powershell
inkflow job next --project PROJECT_ID --json
inkflow job submit JOB_ID `
  --attempt-id ATTEMPT_ID `
  --lease-token LEASE_TOKEN `
  --result-file result.json
```

外部生成任务的 `result.json` 形如：

```json
{
  "outputs": ["完整成品"],
  "executor_metadata": {
    "runtime": "Codex Desktop",
    "model": "实际使用的模型",
    "runtime_version": "可选版本",
    "context_mode": "fresh",
    "tools": []
  }
}
```

租约令牌和尝试编号共同标识一次执行，旧尝试不能覆盖新尝试。格式错误会保存原始返回和解析错误。进程意外中断后，租约不会因为另一个 CLI 命令启动而被偷偷改写；用户可在工作台选择“释放并重试”，或执行 `inkflow job retry JOB_ID`。

材料准备任务允许外部执行器搜索，但搜索只用于发现实际进入净化材料的新信息。每个采用的来源必须返回 `title`、`url`、实际采用原文 `content` 和用途 `use`，四项会沿生产链保存到项目来源记录。内置 API 仅在当前适配器明确声明支持原生搜索时联网。

## CLI 主流程

```powershell
inkflow project create --title "项目名" --request-file request.txt --material-file source.txt
inkflow prepare start PROJECT_ID
inkflow handoff show PROJECT_ID --markdown
inkflow handoff approve PROJECT_ID
inkflow generate start PROJECT_ID
inkflow experiment batch-five PROJECT_ID
inkflow result list PROJECT_ID
inkflow result review GENERATION_ID --state accepted
```

五版规则对比要求正好提供五个正文不同的规则版本，并始终由指定的内置 API 配置串行执行：

```powershell
inkflow experiment compare-rules PROJECT_ID `
  --provider PROVIDER_PROFILE_ID `
  --rule RULE_1 --rule RULE_2 --rule RULE_3 --rule RULE_4 --rule RULE_5
```

提示词可通过工作台逐环节修改，也可以使用 `inkflow prompt list` 查看当前值、使用 `inkflow prompt set` 直接覆盖。模型配置、规则、结果编辑与导出同样都有对应的 CLI 命令。CLI 的结构化输出统一为 JSON，便于脚本和 Agent 读取。

## 内置 API 提供方

当前有两种适配器：

- `openai-compatible-chat` 调用 `/chat/completions`，不声明搜索能力。
- `openai-responses` 调用 `/responses`，材料准备阶段可使用原生 `web_search`。

```powershell
inkflow provider configure `
  --name my-provider `
  --adapter openai-responses `
  --base-url https://api.openai.com/v1 `
  --model MODEL_NAME `
  --api-key YOUR_KEY
```

API 密钥优先保存到操作系统密钥环，数据库只保存密钥名称。也可以使用 `INKFLOW_API_KEY` 或 `INKFLOW_API_KEY_<PROVIDER_NAME>`。

## 项目结构与验证

- `src/inkflow/application/`：项目输入、任务、交接、实验、结果查询和模型运行六个应用边界。
- `src/inkflow/storage/`：SQLite/Alembic 持久化边界；`service.py` 只组装这些边界。
- `src/inkflow/api.py` 与 `src/inkflow/cli.py`：共用同一组应用边界的两个入口。
- `src/inkflow/prompt_files/`：可审阅、可追溯的提示词实体、运行约束、历史 GitHub 写作版本和防治 AI 味提示词全集。
- `frontend/`：React、TypeScript 与 Vite 工作台。
- `scripts/sync_100x_writing_prompts.py`：仅在用户明确运行时，从 100x-learning 重新复制当前与历史写作提示词。
- `tests/`：迁移、并发租约、提示词快照、结构化边界，以及 API/CLI 真实生产者到消费者链路。
- `archive/`：已退出运行时的原型和改造前版本。

目标验证命令：

```powershell
python -m pytest -q
python -m ruff check src tests scripts
Push-Location frontend
npm run lint
npm run build
Pop-Location
```

如本机有 100x-learning 库，可通过 `INKFLOW_100X_LIBRARY` 指定路径，测试会额外验证真实导入数量、标题清理、幂等迁移，以及完整 CLI 交接与五篇生成链路。

## 独立可执行文件

仓库提供 PyInstaller `onedir` 配置 `inkflow.spec`。打包前必须先构建前端，然后在每个目标操作系统上分别构建和验证。仓库不会在普通开发或测试流程中自动打包。

```powershell
Push-Location frontend; npm ci; npm run build; Pop-Location
pyinstaller --clean inkflow.spec
```

## 许可证

InkFlow 原创代码采用 AGPL-3.0-or-later；从 100x-learning 同步且带有对应来源标记的提示词仍采用 MPL-2.0。用户材料、生成内容、凭据和第三方参考数据不会因使用本软件而改变归属。完整边界与依赖归属见 [LICENSING.md](LICENSING.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
