import { ArrowRight, Check, Edit3, History, Save } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api/client'
import type { Handoff, HandoffCore } from '../../types'

const divider = '\n\n---\n\n'

export function HandoffStage({ projectId, handoff, history, run, onContinue }: { projectId: string; handoff: Handoff | null; history: Handoff[]; run: (action: () => Promise<unknown>, message: string) => Promise<void>; onContinue: () => void }) {
  const [draft, setDraft] = useState<HandoffCore | null>(handoff?.core ?? null)
  const [cases, setCases] = useState(handoff?.core.reference_cases.join(divider) ?? '')
  const [hooks, setHooks] = useState(handoff?.core.reference_hooks.join(divider) ?? '')
  if (!handoff || !draft) return <div className="handoff-layout"><div className="sheet empty-state wide"><Edit3 size={28} /><h3>还没有当前交接</h3><p>新增材料或修改要求后，旧交接会退出当前版本。重新完成材料净化与参考选择即可形成新草稿。</p></div><HistoryPanel history={history} /></div>
  const save = () => run(() => api.reviseHandoff(projectId, { ...draft, reference_cases: splitBodies(cases), reference_hooks: splitBodies(hooks) }), '交接已保存为新草稿，批准状态已撤销')
  const approved = handoff.handoff.status === 'approved'
  return <div className="handoff-layout">
    <section className="sheet handoff-paper"><div className="handoff-masthead"><div><p>INKFLOW HANDOFF</p><h2>正式写作交接</h2></div><div><span className={`status-pill ${handoff.handoff.status}`}>{approved ? '已批准' : '待批准'}</span><small>Revision {handoff.handoff.revision}</small></div></div><label><span>本次写作要求 <em>来自项目真源</em></span><textarea rows={4} value={draft.user_request} readOnly /></label><label><span>净化后材料</span><textarea rows={13} value={draft.purified_material} onChange={(e) => setDraft({ ...draft, purified_material: e.target.value })} /></label><div className="form-grid two"><label><span>参考写作案例 <em>用 --- 分隔</em></span><textarea rows={10} value={cases} onChange={(e) => setCases(e.target.value)} /></label><label><span>参考开头钩子 <em>用 --- 分隔</em></span><textarea rows={10} value={hooks} onChange={(e) => setHooks(e.target.value)} /></label></div><label><span>其它实际写作输入</span><textarea rows={4} value={draft.other_inputs} onChange={(e) => setDraft({ ...draft, other_inputs: e.target.value })} /></label><div className="handoff-foot"><span className="mono">CORE {handoff.handoff.core_hash.slice(0, 14)}</span><div><button className="button secondary" onClick={() => void save().catch(() => undefined)}><Save size={15} />保存新修订</button>{!approved ? <button className="button primary" onClick={() => void run(() => api.approveHandoff(projectId), '交接已批准，可以开始生成').catch(() => undefined)}><Check size={16} />批准交接</button> : <button className="button primary" onClick={onContinue}>进入生成实验<ArrowRight size={16} /></button>}</div></div></section>
    <HistoryPanel history={history} currentId={handoff.handoff.id} />
  </div>
}

function HistoryPanel({ history, currentId }: { history: Handoff[]; currentId?: string }) {
  return <aside className="sheet history-panel"><div className="sheet-heading"><div><p className="kicker">IMMUTABLE HISTORY</p><h2>修订历史</h2></div><History size={18} /></div><div className="revision-list">{history.map((item) => <article className={item.handoff.id === currentId ? 'current' : ''} key={item.handoff.id}><header><strong>v{item.handoff.revision}</strong><span className={`status-pill ${item.handoff.status}`}>{item.handoff.status === 'approved' ? '已批准' : item.handoff.status === 'draft' ? '草稿' : '已接替'}</span></header><p>{item.core.purified_material.slice(0, 110)}</p><small className="mono">{item.handoff.core_hash.slice(0, 12)}</small></article>)}</div><div className="history-note">历史交接与旧结果永远保留，但新实验只会读取当前已批准版本。</div></aside>
}

function splitBodies(value: string) { return value.split(/\n\s*---\s*\n/g).map((item) => item.trim()).filter(Boolean) }
