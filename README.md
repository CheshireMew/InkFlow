# InkFlow

InkFlow 是一个跨平台、本地优先的写作工作台。它把原始材料、经过确认的写作交接、写作规则和模型原始成品放在同一条可检查的链路里，专门解决“提示词到底改了什么、为什么结果变了”这类问题。

它不再运行旧版的配方、翻译和通用工具箱。旧实现完整保存在 `archive/v0.1-prototype/`，生产代码只有一套写作架构。

## 工作方式

一次正式写作分成两轮：

1. InkFlow 净化材料，并按写作技巧索引自动选择参考写作案例和开头钩子，形成正式交接文件。
2. 用户检查并批准交接后，模型才会得到这份固定输入和指定的写作规则，开始生成成品。

参考案例和钩子由模型自动选择，不需要人工挑选。选择只看写作技巧和成品形式，不按案例主题匹配；入选后读取完整正文。来源路径、文件名和链接只保存在本地数据库的来源记录里，不进入正式写作执行包。

生成阶段提供三种模式：

- 单篇：当前规则生成一篇。
- 一次写五篇：同一次模型调用、同一条规则，返回五篇互相独立的成品。
- 最近五版规则串行对比：五次独立调用，交接材料、案例、钩子和执行器不变，只替换写作规则。

InkFlow 不自动评审、融合、改写或润色结果，也不会替用户选择所谓最佳稿。这样可以直接观察第一次生成和提示词变量的真实效果。

## 架构

- `src/inkflow/`：Python 领域模型、SQLite/Alembic 存储、任务队列、模型提供方、CLI 和 FastAPI。
- `frontend/`：React/Vite 本地 Web 工作台。
- `tests/`：从项目创建到交接批准、任务领取、模型回传和结果展示的真实链路测试。
- `archive/v0.1-prototype/`：已退出运行时的旧配方系统和旧测试。

SQLite 数据库是唯一真实来源。命令行和 Web 界面调用同一组服务，不各自保存状态。API 密钥进入操作系统密钥环；数据库只保存提供方配置和密钥名。

## 开发运行

需要 Python 3.10+ 与 Node.js 20+。

```bash
python -m pip install -e ".[dev]"
cd frontend
npm ci
npm run build
cd ..
inkflow app
```

默认打开 `http://127.0.0.1:8765`。数据目录遵循 Windows、macOS 和 Linux 的系统约定，也可以显式指定：

```bash
inkflow --data-dir /path/to/inkflow-data app
```

Windows 也可以运行 `start_inkflow.bat`，macOS/Linux 可以运行 `./start_inkflow.sh`。

## 迁移现有参考库

迁移只读取 100x-learning 的现有库，不会修改它。导入完成后，InkFlow 数据库成为参考内容的真实来源。

```bash
inkflow reference import-100x "/path/to/100x-learning/System Knowledge"
```

相同正文不能同时充当案例和钩子；重复内容会被跳过并出现在导入报告中。导入可重复执行，不会制造重复数据或重复规则版本。

## 让外部 Codex 或 Agent 执行任务

InkFlow 不反向调用 Codex CLI。外部执行器主动领取任务，把任务中的 `model_input` 交给全新会话，再原样回传结构化结果：

```bash
inkflow job next --project PROJECT_ID
inkflow job submit JOB_ID --lease-token TOKEN --result-file result.json
```

材料准备任务允许外部执行器搜索，但搜索目的只限于发现能够补充正文或增强传播力的新信息，不做例行核查。内置 API 只有在提供方明确支持原生搜索时才会联网。

## CLI 主流程

```bash
inkflow project create --title "项目名" --request-file request.txt --material-file source.txt
inkflow prepare start PROJECT_ID
inkflow handoff show PROJECT_ID
inkflow handoff approve PROJECT_ID
inkflow generate start PROJECT_ID --batch-five
inkflow result list PROJECT_ID
```

提示词对比要求正好五条正文不同的规则：

```bash
inkflow experiment compare-rules PROJECT_ID \
  --rule RULE_1 --rule RULE_2 --rule RULE_3 --rule RULE_4 --rule RULE_5
```

所有成功的 CLI 数据输出都是 JSON，方便 Codex、脚本和其它 Agent 稳定读取。

## 内置 API 提供方

支持两类适配器：

- `openai-compatible-chat`：调用 `/chat/completions`，不声明搜索能力。
- `openai-responses`：调用 `/responses`，材料准备阶段可以使用原生 `web_search`。

```bash
inkflow provider configure \
  --name my-provider \
  --adapter openai-responses \
  --base-url https://api.openai.com/v1 \
  --model MODEL_NAME \
  --api-key YOUR_KEY
```

也可以通过 `INKFLOW_API_KEY` 或 `INKFLOW_API_KEY_<PROVIDER_NAME>` 提供密钥。

## 测试

```bash
pytest -q
cd frontend && npm run build
```

本机存在 100x-learning 库时，测试会额外验证真实导入数量、包装标题清理、幂等迁移，以及完整 CLI 交接与五篇生成链路。

## 构建独立可执行文件

仓库提供 `inkflow.spec`，但不会自动打包。先完成前端构建，再在目标操作系统上运行 PyInstaller，分别产出 Windows、macOS 和 Linux 可执行文件：

```bash
cd frontend && npm ci && npm run build && cd ..
pyinstaller --clean inkflow.spec
```

## 许可证

InkFlow 使用 AGPL-3.0-or-later。用户材料、生成内容、提示词、凭据和第三方参考数据不因使用本软件而改变归属。
