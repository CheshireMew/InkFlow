import { CheckCircle2, FlaskConical, KeyRound, Plus, Radio, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ProviderProfile } from '../types'

export function ProviderView({ perform }: { perform: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const [items, setItems] = useState<ProviderProfile[]>([])
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('OpenAI')
  const [adapter, setAdapter] = useState<ProviderProfile['adapter']>('openai-responses')
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [parameters, setParameters] = useState('{}')
  const load = async () => setItems(await api.providers())
  useEffect(() => { void api.providers().then(setItems) }, [])
  const save = () => perform(async () => {
    const parsed = JSON.parse(parameters) as Record<string, unknown>
    await api.configureProvider({ name, adapter, base_url: baseUrl, model, api_key: apiKey, parameters: parsed, activate: true })
    setApiKey(''); setOpen(false); await load()
  }, '提供方新版本已保存并启用')

  return <div className="page">
    <header className="page-heading compact"><div><p className="kicker">MODEL RUNTIME</p><h1>模型与 API</h1><p>配置按版本保存。每次运行都会冻结模型、参数与能力快照，旧结果不会随设置变化。</p></div><button className="button primary" onClick={() => setOpen(!open)}><Plus size={16} />新增配置</button></header>
    {open && <section className="sheet provider-form"><div className="form-grid three"><label>配置名称<input value={name} onChange={(e) => setName(e.target.value)} /></label><label>适配器<select value={adapter} onChange={(e) => setAdapter(e.target.value as ProviderProfile['adapter'])}><option value="openai-responses">原生 Responses + 搜索</option><option value="openai-compatible-chat">兼容 Chat，无搜索</option></select></label><label>模型<input value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-5" /></label><label className="span-2">Base URL<input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} /></label><label><span>API Key</span><span className="secret-input"><KeyRound size={15} /><input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} /></span></label><label className="span-3">模型参数 JSON<textarea className="code-field" rows={4} value={parameters} onChange={(e) => setParameters(e.target.value)} /></label></div><div className="sheet-actions"><p>密钥进入系统凭据库或环境变量，不写入数据库。</p><button className="button primary" disabled={!name.trim() || !model.trim() || !apiKey.trim()} onClick={() => void save().catch(() => undefined)}><Save size={16} />保存不可变版本</button></div></section>}
    <div className="provider-grid">{items.map((item) => <article className={`provider-card ${item.active ? 'active' : ''}`} key={item.id}><header><span className="provider-icon"><Radio size={18} /></span><div><h2>{item.name}</h2><p>版本 {item.revision}</p></div>{item.active && <span className="active-badge"><CheckCircle2 size={14} />当前</span>}</header><dl><div><dt>模型</dt><dd>{item.model}</dd></div><div><dt>适配器</dt><dd>{item.adapter}</dd></div><div><dt>联网搜索</dt><dd>{item.capabilities_json.web_search ? '支持' : '不支持'}</dd></div><div><dt>配置指纹</dt><dd className="mono">{item.config_hash.slice(0, 12)}</dd></div></dl><footer>{!item.active && <button className="button secondary" onClick={() => void perform(async () => { await api.activateProvider(item.id); await load() }, '提供方版本已启用').catch(() => undefined)}>设为当前</button>}<button className="button ghost" onClick={() => void perform(() => api.testProvider(item.id), '连接测试通过').catch(() => undefined)}><FlaskConical size={15} />测试连接</button></footer></article>)}</div>
    {!items.length && <div className="empty-state wide"><Radio size={28} /><h3>还没有模型配置</h3><p>外部执行模式不需要 API；要在工作台内直接运行时，再添加提供方。</p></div>}
  </div>
}
