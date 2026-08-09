import { Braces, Check, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Prompt, PromptStage } from '../types'
import { confirmDiscardUnsavedChanges, useUnsavedChanges } from '../unsavedChanges'

const stages: Array<{ id: PromptStage; number: string; label: string; description: string; placeholders: string[] }> = [
  { id: 'prepare_material', number: '01', label: '材料净化', description: '删除无关与来源包装，保留足够成文的事实。', placeholders: ['{{user_request}}', '{{materials}}'] },
  { id: 'select_references', number: '02', label: '参考选择', description: '只看形式和技巧，从案例与钩子索引中挑选。', placeholders: ['{{user_request}}', '{{purified_material}}', '{{reference_index}}'] },
  { id: 'generate', number: '03', label: '成品生成', description: '在批准交接和写作规则之上生成原始成品。', placeholders: ['{{execution_package}}'] },
]

export function PromptStudio({ perform }: { perform: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const [stage, setStage] = useState<PromptStage>('prepare_material')
  const [items, setItems] = useState<Prompt[]>([])
  const [name, setName] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [template, setTemplate] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadPrompt = (item: Prompt) => {
    setName(item.name)
    setSystemPrompt(item.system_prompt)
    setTemplate(item.user_template)
  }
  const load = async () => {
    try {
      const next = await api.prompts()
      setItems(next)
      const initial = next.find((item) => item.stage === 'prepare_material')
      if (initial) loadPrompt(initial)
      setLoadError(null)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '提示词读取失败')
    }
  }
  useEffect(() => {
    let active = true
    void api.prompts().then((next) => {
      if (!active) return
      setItems(next)
      const initial = next.find((item) => item.stage === 'prepare_material')
      if (initial) loadPrompt(initial)
      setLoadError(null)
    }).catch((error: unknown) => { if (active) setLoadError(error instanceof Error ? error.message : '提示词读取失败') })
    return () => { active = false }
  }, [])
  const selected = items.find((item) => item.stage === stage)
  const meta = stages.find((item) => item.id === stage)!
  const dirty = Boolean(selected && (name !== selected.name || systemPrompt !== selected.system_prompt || template !== selected.user_template))
  useUnsavedChanges('prompt-studio', dirty)
  const switchStage = (nextStage: PromptStage) => {
    if (nextStage === stage || !confirmDiscardUnsavedChanges()) return
    setStage(nextStage)
    const prompt = items.find((candidate) => candidate.stage === nextStage)
    if (prompt) loadPrompt(prompt)
  }

  const save = () => perform(async () => {
    const saved = await api.savePrompt(stage, { name, system_prompt: systemPrompt, user_template: template })
    setItems((current) => current.map((item) => item.stage === stage ? saved : item))
    loadPrompt(saved)
  }, '当前提示词已覆盖保存')

  return <div className="page prompt-page">
    {loadError && <div className="load-error" role="alert"><span>提示词读取失败：{loadError}</span><button className="button secondary small" onClick={() => void load()}>重试</button></div>}
    <header className="page-heading"><div><p className="kicker">PROMPT STUDIO</p><h1>每个环节，只保留一个当前提示词。</h1><p>你在这里保存或直接修改文件时会覆盖当前内容，不生成版本记录。已经开始的任务保存完整快照，因此旧结果不会受到影响；AI 仍然没有提示词写入权限。</p></div><div className="trust-chip"><ShieldCheck size={17} />仅用户可修改</div></header>
    <div className="prompt-layout">
      <aside className="stage-rail">
        {stages.map((item) => <button key={item.id} className={stage === item.id ? 'active' : ''} onClick={() => switchStage(item.id)}><span>{item.number}</span><div><strong>{item.label}</strong><small>{item.description}</small></div></button>)}
      </aside>
      <section className="sheet prompt-editor">
        <div className="sheet-heading"><div><p className="kicker">{meta.number} / CURRENT</p><h2>{meta.label}</h2></div><span className="active-badge">当前</span></div>
        <div className="prompt-meta"><span><Braces size={14} />可用变量：{meta.placeholders.join('  ')}</span><span>内容指纹：{selected?.prompt_hash.slice(0, 12)}</span></div>
        {selected && <p className="prompt-file-path">可手动编辑的当前文件：{selected.current_path}</p>}
        <div className="form-grid"><label>提示词名称<input value={name} onChange={(e) => setName(e.target.value)} /></label><label>系统提示词<textarea className="prompt-textarea" rows={12} value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} /></label><label>用户提示词模板<textarea className="prompt-textarea" rows={10} value={template} onChange={(e) => setTemplate(e.target.value)} /></label></div>
        <div className="locked-contract"><Check size={16} /><div><strong>JSON 输出结构不随提示词编辑</strong><p>你负责写作目标与表达方式；InkFlow 负责把结果约束成准备、选择或生成阶段可读取的结构。</p></div></div>
        <div className="sheet-actions"><p>保存会直接覆盖当前提示词，不产生旧版本。已开始的任务仍使用当时保存的完整快照。</p><button className="button primary" disabled={!dirty || !name.trim() || !systemPrompt.trim() || !template.trim()} onClick={() => void save().catch(() => undefined)}><Save size={16} />覆盖保存</button></div>
      </section>
    </div>
  </div>
}
