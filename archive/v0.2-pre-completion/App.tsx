import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  Check,
  ChevronRight,
  CircleAlert,
  Copy,
  Database,
  FileText,
  FlaskConical,
  LoaderCircle,
  Plus,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { api, type Generation, type Handoff, type Project, type ProjectDetail, type WritingRule } from './api/client'

type Notice = { kind: 'ok' | 'error'; text: string } | null

function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [handoff, setHandoff] = useState<Handoff | null>(null)
  const [rules, setRules] = useState<WritingRule[]>([])
  const [results, setResults] = useState<Generation[]>([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [showCreate, setShowCreate] = useState(false)

  const loadProjects = useCallback(async () => setProjects(await api.projects()), [])
  const refresh = useCallback(async () => {
    await loadProjects()
    setRules(await api.rules())
    if (!projectId) return
    const nextDetail = await api.project(projectId)
    setDetail(nextDetail)
    setResults(await api.results(projectId))
    try {
      setHandoff(await api.handoff(projectId))
    } catch {
      setHandoff(null)
    }
  }, [loadProjects, projectId])

  useEffect(() => {
    refresh().catch((error) => setNotice({ kind: 'error', text: error.message }))
  }, [refresh])

  const perform = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true)
    setNotice(null)
    try {
      await action()
      await refresh()
      setNotice({ kind: 'ok', text: message })
    } catch (error) {
      setNotice({ kind: 'error', text: error instanceof Error ? error.message : '操作失败' })
    } finally {
      setBusy(false)
    }
  }

  if (!projectId || !detail) {
    return (
      <Shell notice={notice} busy={busy}>
        <Home
          projects={projects}
          showCreate={showCreate}
          setShowCreate={setShowCreate}
          onOpen={setProjectId}
          onCreated={(id) => {
            setProjectId(id)
            setShowCreate(false)
          }}
          perform={perform}
        />
      </Shell>
    )
  }

  return (
    <Shell notice={notice} busy={busy}>
      <button className="back" onClick={() => { setProjectId(null); setDetail(null); setHandoff(null) }}>
        <ArrowLeft size={16} /> 全部项目
      </button>
      <header className="project-heading">
        <div>
          <p className="eyebrow">写作项目</p>
          <h1>{detail.project.title}</h1>
        </div>
        <button className="icon-button" onClick={() => refresh()} title="刷新"><RefreshCw size={17} /></button>
      </header>
      <div className="workflow-grid">
        <ProjectInputs detail={detail} perform={perform} />
        <PreparationPanel key={handoff?.handoff.id ?? 'empty'} projectId={projectId} detail={detail} handoff={handoff} perform={perform} />
        <GenerationPanel projectId={projectId} handoff={handoff} rules={rules} perform={perform} />
        <ResultsPanel results={results} perform={perform} />
      </div>
    </Shell>
  )
}

function Shell({ children, notice, busy }: { children: React.ReactNode; notice: Notice; busy: boolean }) {
  return (
    <div className="app-shell">
      <nav>
        <div className="brand"><span>i</span> InkFlow <small>0.2</small></div>
        <div className="nav-note">本地写作工作台</div>
      </nav>
      <main>{children}</main>
      {notice && <div className={`notice ${notice.kind}`}>
        {notice.kind === 'ok' ? <Check size={16} /> : <CircleAlert size={16} />}{notice.text}
      </div>}
      {busy && <div className="busy"><LoaderCircle className="spin" size={18} /> 正在处理</div>}
    </div>
  )
}

function Home({ projects, showCreate, setShowCreate, onOpen, onCreated, perform }: {
  projects: Project[]
  showCreate: boolean
  setShowCreate: (value: boolean) => void
  onOpen: (id: string) => void
  onCreated: (id: string) => void
  perform: (action: () => Promise<unknown>, message: string) => Promise<void>
}) {
  const [title, setTitle] = useState('')
  const [request, setRequest] = useState('')
  const [material, setMaterial] = useState('')
  const [libraryPath, setLibraryPath] = useState('')
  const [providerName, setProviderName] = useState('default')
  const [providerAdapter, setProviderAdapter] = useState<'openai-compatible-chat' | 'openai-responses'>('openai-responses')
  const [providerUrl, setProviderUrl] = useState('https://api.openai.com/v1')
  const [providerModel, setProviderModel] = useState('')
  const [providerKey, setProviderKey] = useState('')

  const create = async () => {
    let createdId = ''
    await perform(async () => {
      const response = await api.createProject({ title, user_request: request, materials: material.trim() ? [material] : [] })
      createdId = response.project_id
    }, '项目已创建')
    if (createdId) onCreated(createdId)
  }

  return <>
    <section className="hero">
      <div>
        <p className="eyebrow">WRITE · COMPARE · KEEP</p>
        <h1>把写作材料、提示词和结果<br />放回同一条可检查的链路。</h1>
        <p>先确认交接材料，再生成成品。一次写五篇，或只改变写作规则做五轮串行实验。</p>
      </div>
      <button className="primary" onClick={() => setShowCreate(!showCreate)}><Plus size={18} /> 新建写作项目</button>
    </section>
    {showCreate && <section className="panel create-panel">
      <label>项目名<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：X 创作者政策短帖" /></label>
      <label>你真正要写什么<textarea value={request} onChange={(event) => setRequest(event.target.value)} rows={4} /></label>
      <label>原始材料<textarea value={material} onChange={(event) => setMaterial(event.target.value)} rows={8} /></label>
      <button className="primary" disabled={!title.trim() || !request.trim() || !material.trim()} onClick={create}>创建并进入</button>
    </section>}
    <section className="section-head"><h2>最近项目</h2><span>{projects.length} 个</span></section>
    <div className="project-list">
      {projects.map((project) => <button className="project-card" key={project.id} onClick={() => onOpen(project.id)}>
        <FileText size={20} />
        <div><strong>{project.title}</strong><p>{project.user_request}</p></div>
        <ChevronRight size={18} />
      </button>)}
      {!projects.length && <div className="empty">还没有写作项目。</div>}
    </div>
    <section className="library-strip">
      <Database size={18} />
      <div><strong>导入现有参考库</strong><p>只在首次迁移时使用。导入后 InkFlow 数据库成为真实来源。</p></div>
      <input value={libraryPath} onChange={(event) => setLibraryPath(event.target.value)} placeholder="100x System Knowledge 目录" />
      <button className="secondary" disabled={!libraryPath.trim()} onClick={() => perform(() => api.import100x(libraryPath), '参考库已导入')}>导入</button>
    </section>
    <details className="provider-setup">
      <summary>配置可选的内置 API 提供方</summary>
      <div className="provider-grid">
        <label>配置名<input value={providerName} onChange={(event) => setProviderName(event.target.value)} /></label>
        <label>接口类型<select value={providerAdapter} onChange={(event) => setProviderAdapter(event.target.value as 'openai-compatible-chat' | 'openai-responses')}><option value="openai-responses">Responses API（支持原生搜索）</option><option value="openai-compatible-chat">兼容 Chat Completions</option></select></label>
        <label>Base URL<input value={providerUrl} onChange={(event) => setProviderUrl(event.target.value)} /></label>
        <label>模型<input value={providerModel} onChange={(event) => setProviderModel(event.target.value)} /></label>
        <label className="span-2">API Key<input type="password" value={providerKey} onChange={(event) => setProviderKey(event.target.value)} /></label>
        <button className="secondary" disabled={!providerName.trim() || !providerUrl.trim() || !providerModel.trim() || !providerKey.trim()} onClick={() => perform(async () => { await api.configureProvider({ name: providerName, adapter: providerAdapter, base_url: providerUrl, model: providerModel, api_key: providerKey, parameters: {}, activate: true }); setProviderKey('') }, 'API 提供方已保存，密钥已进入系统密钥环')}>保存并启用</button>
      </div>
    </details>
  </>
}

function ProjectInputs({ detail, perform }: { detail: ProjectDetail; perform: Performer }) {
  const [source, setSource] = useState('')
  return <section className="panel span-2">
    <div className="step-title"><span>1</span><div><h2>用户要求与原始材料</h2><p>来源路径只留在数据库，不进入模型交接。</p></div></div>
    <div className="request-box">{detail.project.user_request}</div>
    {detail.sources.map((item) => <details key={item.id}><summary>{item.kind === 'search' ? '搜索补充材料' : '原始材料'}</summary><pre>{item.content}</pre></details>)}
    <div className="inline-form"><textarea value={source} onChange={(event) => setSource(event.target.value)} rows={3} placeholder="补充材料" /><button className="secondary" disabled={!source.trim()} onClick={() => perform(async () => { await api.addSource(detail.project.id, source); setSource('') }, '材料已加入')}>加入</button></div>
  </section>
}

function PreparationPanel({ projectId, detail, handoff, perform }: { projectId: string; detail: ProjectDetail; handoff: Handoff | null; perform: Performer }) {
  const [executor, setExecutor] = useState<'external' | 'api'>('external')
  const [material, setMaterial] = useState(handoff?.core.purified_material ?? '')
  const [other, setOther] = useState(handoff?.core.other_inputs ?? '无')
  const pending = detail.jobs.filter((job) => job.status === 'pending' || job.status === 'leased')
  return <section className="panel span-2">
    <div className="step-title"><span>2</span><div><h2>正式写作交接</h2><p>先检查净化材料与自动筛选出的完整参考，再决定是否批准。</p></div></div>
    {!handoff && <>
      <div className="toolbar"><select value={executor} onChange={(event) => setExecutor(event.target.value as 'external' | 'api')}><option value="external">外部 Codex / Agent</option><option value="api">内置 API</option></select><button className="primary" onClick={() => perform(() => api.prepare(projectId, executor, executor === 'api'), '写作准备已启动')}><Sparkles size={16} /> 生成写作准备</button></div>
      {pending.length > 0 && <div className="callout">当前有 {pending.length} 个外部任务等待执行。可用 <code>inkflow job next --project {projectId}</code> 领取。</div>}
    </>}
    {handoff && <>
      <div className="status-line"><span className={`status ${handoff.handoff.status}`}>{handoff.handoff.status === 'approved' ? '已批准' : '待确认'}</span><span>第 {handoff.handoff.revision} 版</span></div>
      <label>净化后材料<textarea rows={12} value={material} onChange={(event) => setMaterial(event.target.value)} /></label>
      <label>其它实际写作输入<textarea rows={3} value={other} onChange={(event) => setOther(event.target.value)} /></label>
      <ReferencePreview title="参考写作案例" items={handoff.core.reference_cases} />
      <ReferencePreview title="参考开头钩子" items={handoff.core.reference_hooks} />
      <div className="toolbar end">
        <button className="secondary" onClick={() => perform(() => api.reviseHandoff(projectId, { ...handoff.core, purified_material: material, other_inputs: other }), '交接材料已保存为新版本')}>保存修改</button>
        {handoff.handoff.status !== 'approved' && <button className="primary" onClick={() => perform(() => api.approveHandoff(projectId), '交接已批准，可以生成成品')}><Check size={16} /> 批准交接</button>}
      </div>
    </>}
  </section>
}

function ReferencePreview({ title, items }: { title: string; items: string[] }) {
  return <details><summary>{title} · {items.length}</summary>{items.length ? items.map((item, index) => <pre key={index}>{item}</pre>) : <p className="muted">本次未使用</p>}</details>
}

function GenerationPanel({ projectId, handoff, rules, perform }: { projectId: string; handoff: Handoff | null; rules: WritingRule[]; perform: Performer }) {
  const [executor, setExecutor] = useState<'external' | 'api'>('external')
  const [ruleName, setRuleName] = useState('短内容写作规则')
  const [ruleBody, setRuleBody] = useState('')
  const activeRule = rules.find((rule) => rule.active)
  const comparisonRules = useMemo(() => {
    const seen = new Set<string>()
    return rules.filter((rule) => {
      if (seen.has(rule.body_hash)) return false
      seen.add(rule.body_hash)
      return true
    }).slice(0, 5)
  }, [rules])
  const approved = handoff?.handoff.status === 'approved'
  return <section className="panel span-2">
    <div className="step-title"><span>3</span><div><h2>生成与提示词实验</h2><p>不自动评审、不融合、不润色。结果保持模型第一次交付的原样。</p></div></div>
    <div className="active-rule"><div><span>当前写作规则</span><strong>{activeRule ? `${activeRule.name} · v${activeRule.revision}` : '尚未设置'}</strong></div>{activeRule && <details><summary>查看规则</summary><pre>{activeRule.body}</pre></details>}</div>
    <details className="rule-editor"><summary>新增一版写作规则</summary><div className="rule-editor-body"><label>规则名<input value={ruleName} onChange={(event) => setRuleName(event.target.value)} /></label><label>提示词正文<textarea rows={7} value={ruleBody} onChange={(event) => setRuleBody(event.target.value)} placeholder="只写真正需要模型遵守的规则。" /></label><button className="secondary" disabled={!ruleName.trim() || !ruleBody.trim()} onClick={() => perform(async () => { await api.addRule({ name: ruleName, body: ruleBody, activate: true }); setRuleBody('') }, '新规则已保存并设为当前版本')}>保存并启用</button></div></details>
    <div className="toolbar"><select value={executor} onChange={(event) => setExecutor(event.target.value as 'external' | 'api')}><option value="external">外部 Codex / Agent</option><option value="api">内置 API</option></select></div>
    <div className="experiment-cards">
      <button disabled={!approved || !activeRule} onClick={() => perform(() => api.generate(projectId, { executor, run: executor === 'api', batch_five: false }), '单篇生成已启动')}><FileText size={19} /><strong>单篇</strong><span>当前规则，生成一次</span></button>
      <button disabled={!approved || !activeRule} onClick={() => perform(() => api.generate(projectId, { executor, run: executor === 'api', batch_five: true }), '同一规则五篇生成已启动')}><Sparkles size={19} /><strong>一次写五篇</strong><span>一个调用，五个成品</span></button>
      <button disabled={!approved || comparisonRules.length !== 5} onClick={() => perform(() => api.compareRules(projectId, comparisonRules.map((rule) => rule.id), executor, executor === 'api'), '五轮串行规则实验已启动')}><FlaskConical size={19} /><strong>最近五版规则串行对比</strong><span>{comparisonRules.length}/5 版可用；除写作规则外，其它输入完全相同</span></button>
    </div>
  </section>
}

function ResultsPanel({ results, perform }: { results: Generation[]; perform: Performer }) {
  return <section className="panel span-2">
    <div className="step-title"><span>4</span><div><h2>原始生成结果</h2><p>选择只做标记，不触发修改。</p></div></div>
    <div className="results">
      {results.map((result, index) => <article className={result.selected ? 'selected' : ''} key={result.id}>
        <header><span>结果 {index + 1}</span><div><button className="icon-button" title="复制" onClick={() => navigator.clipboard.writeText(result.content)}><Copy size={15} /></button><button className="secondary small" onClick={() => perform(() => api.selectResult(result.id), '已标记为选中结果')}>{result.selected ? '已选中' : '选中'}</button></div></header>
        <pre>{result.content}</pre>
      </article>)}
      {!results.length && <div className="empty">生成完成后，结果会原样出现在这里。</div>}
    </div>
  </section>
}

type Performer = (action: () => Promise<unknown>, message: string) => Promise<void>

export default App
