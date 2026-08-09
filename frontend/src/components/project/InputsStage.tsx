import { FileText, Link2, Plus, Save, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api/client'
import type { ProjectDetail } from '../../types'

export function InputsStage({ detail, run }: { detail: ProjectDetail; run: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const [request, setRequest] = useState(detail.project.user_request)
  const [sourceMode, setSourceMode] = useState<'text' | 'url'>('text')
  const [source, setSource] = useState('')
  const requestChanged = request !== detail.project.user_request
  return <div className="stage-layout">
    <section className="sheet stage-main"><div className="stage-heading"><span>01</span><div><p className="kicker">SOURCE OF TRUTH</p><h2>写作要求与原始材料</h2><p>这里保留你真正交给 InkFlow 的原文。来源信息只留在素材层，不会混进最终交接。</p></div></div><label className="editor-label">本次写作要求<textarea rows={7} value={request} onChange={(e) => setRequest(e.target.value)} /></label>{requestChanged && <div className="warning-box"><ShieldAlert size={17} /><p>修改写作要求后，当前交接会退出活动状态，需要重新完成材料准备和审批；历史结果仍然保留。</p></div>}<div className="sheet-actions"><span className="mono subtle">{detail.project.id}</span><button className="button primary" disabled={!request.trim() || !requestChanged} onClick={() => void run(() => api.updateProject(detail.project.id, request), '写作要求已更新，请重新准备交接').catch(() => undefined)}><Save size={16} />保存要求</button></div></section>
    <aside className="sheet stage-side"><div className="sheet-heading"><div><p className="kicker">MATERIALS · {detail.sources.length}</p><h2>素材箱</h2></div></div><div className="source-list">{detail.sources.map((item, index) => <article key={item.id}><header><span>{String(index + 1).padStart(2, '0')}</span><strong>{item.kind === 'url' ? '网页来源' : item.kind === 'file' ? '本地文件' : item.kind === 'search' ? '搜索补充' : '粘贴材料'}</strong></header><p>{item.content}</p>{Object.keys(item.provenance_json).length > 0 && <details><summary>来源信息</summary><pre>{JSON.stringify(item.provenance_json, null, 2)}</pre></details>}</article>)}</div><div className="source-composer"><div className="segmented"><button className={sourceMode === 'text' ? 'active' : ''} onClick={() => setSourceMode('text')}><FileText size={14} />粘贴文字</button><button className={sourceMode === 'url' ? 'active' : ''} onClick={() => setSourceMode('url')}><Link2 size={14} />读取网址</button></div>{sourceMode === 'text' ? <textarea rows={6} value={source} onChange={(e) => setSource(e.target.value)} placeholder="追加会议记录、采访或原始资料" /> : <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="https://…" />}<button className="button secondary full" disabled={!source.trim()} onClick={() => void run(async () => { await api.addSource(detail.project.id, sourceMode === 'url' ? { url: source } : { content: source }); setSource('') }, '素材已加入项目').catch(() => undefined)}><Plus size={15} />加入素材箱</button></div></aside>
  </div>
}
