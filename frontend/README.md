# InkFlow 前端

这里是 InkFlow 本地写作工作台的 React、TypeScript 与 Vite 界面。它不单独保存业务状态，所有项目、提示词、参考库、任务、交接、实验和结果都通过同源 `/api` 读取 Python 服务。Prompt Studio 会显示当前可手动编辑文件的完整路径；用户直接修改后，后端会保存为新的不可变版本。SQLite 只保存索引与不可变快照，AI 调用没有写回提示词的入口。

```bash
npm ci
npm run dev
npm run lint
npm run build
```

开发服务器把 `/api` 转发给本地 FastAPI。正式运行时先执行 `npm run build`，FastAPI 会直接托管 `dist/`；应用使用 Hash 路由，因此静态托管刷新时不需要额外的服务器回退规则。

主要界面位于 `src/views/`，项目五阶段位于 `src/components/project/`，统一请求封装在 `src/api/client.ts`，视觉系统集中在 `src/index.css`。不要在前端复制领域状态或伪造任务结果。
