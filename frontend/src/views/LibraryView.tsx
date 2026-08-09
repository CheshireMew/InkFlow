import { Archive, BookOpen, FilePlus2, Save, Search, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ReferenceItem } from '../types'
import { confirmDiscardUnsavedChanges, useUnsavedChanges } from '../unsavedChanges'

type Draft = { id?: string; kind: 'case' | 'hook'; title: string; body: string; formats: string; techniques: string; active: boolean }
const emptyDraft: Draft = { kind: 'case', title: '', body: '', formats: 'short', techniques: '', active: true }

export function LibraryView({ perform }: { perform: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const [items, setItems] = useState<ReferenceItem[]>([])
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<'all' | 'case' | 'hook'>('all')
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [draftBaseline, setDraftBaseline] = useState(JSON.stringify(emptyDraft))
  const [importRoot, setImportRoot] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const load = async () => {
    try { setItems(await api.references(true)); setLoadError(null) }
    catch (error) { setLoadError(error instanceof Error ? error.message : '资料库读取失败') }
  }
  useEffect(() => {
    let active = true
    void api.references(true).then((next) => { if (active) { setItems(next); setLoadError(null) } }).catch((error: unknown) => { if (active) setLoadError(error instanceof Error ? error.message : '资料库读取失败') })
    return () => { active = false }
  }, [])
  const dirty = JSON.stringify(draft) !== draftBaseline
  useUnsavedChanges('reference-library', dirty)
  const filtered = useMemo(() => items.filter((item) => (kind === 'all' || item.kind === kind) && `${item.title} ${item.body_preview ?? ''} ${item.techniques_json.join(' ')}`.toLowerCase().includes(query.toLowerCase())), [items, kind, query])

  const edit = async (item: ReferenceItem) => {
    if (!confirmDiscardUnsavedChanges()) return
    try {
      const full = await api.reference(item.id)
      const next = { id: full.id, kind: full.kind, title: full.title, body: full.body ?? '', formats: full.formats_json.join(', '), techniques: full.techniques_json.join(', '), active: full.active }
      setDraft(next); setDraftBaseline(JSON.stringify(next)); setLoadError(null)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '参考条目读取失败')
    }
  }
  const newDraft = () => {
    if (!confirmDiscardUnsavedChanges()) return
    setDraft(emptyDraft); setDraftBaseline(JSON.stringify(emptyDraft))
  }
  const save = () => perform(async () => {
    const payload = { kind: draft.kind, title: draft.title, body: draft.body, formats: split(draft.formats), techniques: split(draft.techniques), active: draft.active }
    if (draft.id) await api.updateReference(draft.id, payload)
    else await api.addReference(payload)
    setDraft(emptyDraft); setDraftBaseline(JSON.stringify(emptyDraft)); await load()
  }, draft.id ? '参考条目已更新' : '参考条目已加入资料库')

  return <div className="page">
    {loadError && <div className="load-error" role="alert"><span>资料库读取失败：{loadError}</span><button className="button secondary small" onClick={() => void load()}>重试</button></div>}
    <header className="page-heading compact"><div><p className="kicker">REFERENCE LIBRARY</p><h1>案例与钩子资料库</h1><p>模型选择阶段只看到编号、形式和技巧；正文只在选中后进入交接。</p></div><button className="button secondary" onClick={newDraft}><FilePlus2 size={16} />新建条目</button></header>
    <div className="library-layout">
      <section className="sheet library-list"><div className="library-tools"><label className="search-field"><Search size={16} /><input aria-label="搜索资料库" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标题或技巧" /></label><div className="segmented"><button className={kind === 'all' ? 'active' : ''} onClick={() => setKind('all')}>全部</button><button className={kind === 'case' ? 'active' : ''} onClick={() => setKind('case')}>案例</button><button className={kind === 'hook' ? 'active' : ''} onClick={() => setKind('hook')}>钩子</button></div></div><div className="reference-list">{filtered.map((item) => <button key={item.id} className={!item.active ? 'archived' : ''} onClick={() => void edit(item)}><span className={`reference-kind ${item.kind}`}>{item.kind === 'case' ? <BookOpen size={15} /> : <Sparkles size={15} />}{item.kind === 'case' ? '案例' : '钩子'}</span><div><strong>{item.title}</strong><p>{item.body_preview}</p><small>{item.techniques_json.join(' · ') || '未标技巧'}</small></div>{!item.active && <Archive size={15} />}</button>)}</div></section>
      <aside className="sheet reference-editor"><div className="sheet-heading"><div><p className="kicker">{draft.id ? 'EDIT ITEM' : 'NEW ITEM'}</p><h2>{draft.id ? '编辑参考条目' : '添加参考条目'}</h2></div></div><div className="form-grid two"><label>类型<select value={draft.kind} disabled={Boolean(draft.id)} onChange={(e) => setDraft({ ...draft, kind: e.target.value as Draft['kind'] })}><option value="case">写作案例</option><option value="hook">开头钩子</option></select></label><label>状态<select value={draft.active ? 'active' : 'archived'} onChange={(e) => setDraft({ ...draft, active: e.target.value === 'active' })}><option value="active">启用</option><option value="archived">归档</option></select></label><label className="span-2">标题<input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label><label className="span-2">正文<textarea rows={12} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} /></label><label>适用形式<input value={draft.formats} onChange={(e) => setDraft({ ...draft, formats: e.target.value })} placeholder="short, article" /></label><label>写作技巧<input value={draft.techniques} onChange={(e) => setDraft({ ...draft, techniques: e.target.value })} placeholder="直接宣布变化, 信息递进" /></label></div><button className="button primary full" disabled={!draft.title.trim() || !draft.body.trim()} onClick={() => void save().catch(() => undefined)}><Save size={16} />保存条目</button><div className="import-box"><strong>导入 100x 私人库</strong><input value={importRoot} onChange={(e) => setImportRoot(e.target.value)} placeholder="System Knowledge 目录" /><button className="button secondary full" disabled={!importRoot.trim()} onClick={() => void perform(async () => { await api.import100x(importRoot); await load() }, '100x 资料库已导入').catch(() => undefined)}>读取并去重</button></div></aside>
    </div>
  </div>
}

function split(value: string) { return value.split(',').map((item) => item.trim()).filter(Boolean) }
