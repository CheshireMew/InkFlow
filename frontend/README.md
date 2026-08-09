# InkFlow 前端

这里是 InkFlow 本地写作工作台的 React、TypeScript 与 Vite 界面。它不单独保存业务状态，所有项目、提示词、参考库、任务、交接、运行和结果都通过同源 `/api` 读取 Python 服务。Prompt Studio 会显示当前可手动编辑文件的完整路径；用户保存或直接修改时都会覆盖每个阶段唯一的当前值。每次运行单独保存启动时的完整快照，AI 调用没有写回提示词的入口。界面只把固定内置 API 配置的五规则串行任务称为受控对比；外部结果必须显示运行身份并标记为非受控。运行成功与用户接受是两个状态，编辑结果会恢复为未审阅。

```bash
npm ci
npm run dev
npm run lint
npm run build
```

开发服务器把 `/api` 转发给本地 FastAPI。正式运行时先执行 `npm run build`，FastAPI 会直接托管 `dist/`；应用使用 Hash 路由，因此静态托管刷新时不需要额外的服务器回退规则。

主要界面位于 `src/views/`，项目五阶段位于 `src/components/project/`，统一请求封装在 `src/api/client.ts`，视觉系统集中在 `src/index.css`。不要在前端复制领域状态或伪造任务结果。
