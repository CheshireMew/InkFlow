import { Braces, Check, GitBranch, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { PromptRevision, PromptStage } from '../types'

const stages: Array<{ id: PromptStage; number: string; label: string; description: string; placeholders: string[] }> = [
  { id: 'prepare_material', number: '01', label: '材料净化', description: '删除无关与来源包装，保留足够成文的事实。', placeholders: ['{{user_request}}', '{{materials}}'] },
  { id: 'select_references', number: '02', label: '参考选择', description: '只看形式和技巧，从案例与钩子索引中挑选。', placeholders: ['{{user_request}}', '{{purified_material}}', '{{reference_index}}'] },
  { id: 'generate', number: '03', label: '成品生成', description: '在批准交接和写作规则之上生成原始成品。', placeholders: ['{{execution_package}}'] },
]

export function PromptStudio({ perform }: { perform: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const [stage, setStage] = useState<PromptStage>('prepare_material')
  const [items, setItems] = useState<PromptRevision[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [name, setName] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [template, setTemplate] = useState('')

  const selectRevision = (item: PromptRevision) => {
    setSelectedId(item.id)
    setName(`${item.name} · 修订`)
    setSystemPrompt(item.system_prompt)
    setTemplate(item.user_template)
  }
  useEffect(() => {
    void api.prompts().then((next) => {
      setItems(next)
      const initial = next.find((item) => item.stage === 'prepare_material' && item.active)
      if (initial) selectRevision(initial)
    })
  }, [])
  const stageItems = useMemo(() => items.filter((item) => item.stage === stage), [items, stage])
  const selected = stageItems.find((item) => item.id === selectedId)
  const meta = stages.find((item) => item.id === stage)!

  const save = () => perform(async () => {
    await api.addPrompt({ stage, name, system_prompt: systemPrompt, user_template: template, activate: true })
    const next = await api.prompts()
    setItems(next)
    const active = next.find((item) => item.stage === stage && item.active)
    if (active) selectRevision(active)
  }, '新提示词版本已保存并启用')

  return <div className="page prompt-page">
    <header className="page-heading"><div><p className="kicker">PROMPT STUDIO</p><h1>每个环节，都有自己的提示词文件。</h1><p>只有你在这里保存或从命令行明确添加时才会创建新版本。AI 运行只能读取快照，不能改写提示词；每个版本同时保存为独立实体文件。</p></div><div className="trust-chip"><ShieldCheck size={17} />AI 只读提示词</div></header>
    <div className="prompt-layout">
      <aside className="stage-rail">
        {stages.map((item) => <button key={item.id} className={stage === item.id ? 'active' : ''} onClick={() => { setStage(item.id); const active = items.find((prompt) => prompt.stage === item.id && prompt.active) ?? items.find((prompt) => prompt.stage === item.id); if (active) selectRevision(active) }}><span>{item.number}</span><div><strong>{item.label}</strong><small>{item.description}</small></div></button>)}
      </aside>
      <section className="sheet prompt-editor">
        <div className="sheet-heading"><div><p className="kicker">{meta.number} / EDITING</p><h2>{meta.label}</h2></div><select aria-label="选择历史版本" value={selected?.id ?? ''} onChange={(e) => { const item = stageItems.find((prompt) => prompt.id === e.target.value); if (item) selectRevision(item) }}>{stageItems.map((item) => <option value={item.id} key={item.id}>v{item.revision} · {item.name}{item.active ? ' · 当前' : ''}</option>)}</select></div>
        <div className="prompt-meta"><span><GitBranch size={14} />当前从 v{selected?.revision ?? 0} 派生</span><span><Braces size={14} />可用变量：{meta.placeholders.join('  ')}</span></div>
        {selected && <p className="prompt-file-path">{selected.active ? `可手动编辑的当前文件：${selected.editable_file}` : `只读历史文件：${selected.entity_path}`}</p>}
        <div className="form-grid"><label>新版本名称<input value={name} onChange={(e) => setName(e.target.value)} /></label><label>系统提示词<textarea className="prompt-textarea" rows={12} value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} /></label><label>用户提示词模板<textarea className="prompt-textarea" rows={10} value={template} onChange={(e) => setTemplate(e.target.value)} /></label></div>
        <div className="locked-contract"><Check size={16} /><div><strong>JSON 输出结构不随提示词编辑</strong><p>你负责写作目标与表达方式；InkFlow 负责把结果约束成准备、选择或生成阶段可读取的结构。</p></div></div>
        <div className="sheet-actions"><p>可以在这里保存，也可以直接修改上面的当前文件；应用下次读取时会自动登记为新版本。已开始的任务仍使用当时快照。</p><button className="button primary" disabled={!name.trim() || !systemPrompt.trim() || !template.trim()} onClick={() => void save().catch(() => undefined)}><Save size={16} />保存为新版本</button></div>
      </section>
      <aside className="version-panel"><p className="kicker">VERSION HISTORY</p><h3>版本记录</h3>{stageItems.map((item) => <button key={item.id} onClick={() => selectRevision(item)} className={selected?.id === item.id ? 'active' : ''}><div><strong>v{item.revision}</strong>{item.active && <span>当前</span>}</div><p>{item.name}</p><small>{item.prompt_hash.slice(0, 10)}</small></button>)}</aside>
    </div>
  </div>
}
