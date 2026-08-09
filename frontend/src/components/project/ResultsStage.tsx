import { Check, Copy, Download, Edit3, RotateCcw, Save, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Experiment, Generation } from '../../types'
import { confirmDiscardUnsavedChanges, useUnsavedChanges } from '../../unsavedChanges'

export function ResultsStage({ results, experiments, run }: { results: Generation[]; experiments: Experiment[]; run: (action: () => Promise<unknown>, message: string) => Promise<void> }) {
  const [experimentId, setExperimentId] = useState('all')
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const visible = useMemo(() => experimentId === 'all' ? results : results.filter((item) => item.experiment_id === experimentId), [results, experimentId])
  const handoffCount = new Set(visible.map((item) => item.handoff_id)).size
  const runtimeCount = new Set(visible.map((item) => item.runtime_fingerprint)).size
  const hasNonControlledRuns = visible.some((item) => !item.controlled)
  const editedResult = results.find((item) => item.id === editing)
  const dirty = Boolean(editedResult && draft !== editedResult.current_content)
  useUnsavedChanges('result-editor', dirty)
  const beginEdit = (item: Generation) => {
    if (editing !== item.id && !confirmDiscardUnsavedChanges()) return
    setEditing(item.id); setDraft(item.current_content)
  }
  const review = (item: Generation, state: Generation['review_state']) => run(
    () => api.reviewResult(item.id, state),
    state === 'accepted' ? '已接受当前结果' : state === 'rejected' ? '已拒绝当前结果' : '已撤回审阅决定',
  )
  return <div className="results-workspace"><header className="results-toolbar"><div><p className="kicker">RESULT WORKSPACE</p><h2>并排阅读，再明确审阅</h2><p>运行成功只表示结果已生成，所有新结果默认未审阅。模型原文永不改写；人工编辑会保存新修订，并撤销此前的接受或拒绝决定。</p></div><label>运行筛选<select value={experimentId} onChange={(e) => setExperimentId(e.target.value)}><option value="all">全部运行</option>{experiments.map((item) => <option value={item.id} key={item.id}>{item.kind} · {new Date(item.created_at).toLocaleString()}</option>)}</select></label></header>{handoffCount > 1 && <div className="warning-box"><span>!</span><p>当前结果来自 {handoffCount} 个交接版本。每张卡片都标明版本，不能把它们当作只改变写作规则的同组结果。</p></div>}{(runtimeCount > 1 || hasNonControlledRuns) && <div className="warning-box"><span>!</span><p>{hasNonControlledRuns ? '当前包含不属于受控规则对比的生成结果。' : ''}{runtimeCount > 1 ? `当前结果包含 ${runtimeCount} 组不同运行条件。` : ''} 这些结果可以并排阅读，但不能据此断言差异由写作规则造成。</p></div>}<div className="result-grid">{visible.map((item, index) => <article className={`result-card ${item.review_state}`} key={item.id}><header><div><span>OUTPUT {String(index + 1).padStart(2, '0')}</span><strong>{item.writing_rule.name} · v{item.writing_rule.revision}</strong></div><span className={`review-mark ${item.review_state}`}>{item.review_state === 'accepted' ? <><Check size={14} />已接受</> : item.review_state === 'rejected' ? <><X size={14} />已拒绝</> : '未审阅'}</span></header><div className="result-context"><span>交接 {item.handoff_id.split('-').at(-1)?.slice(0, 7)}</span><span>{item.edit_revision ? `人工修订 v${item.edit_revision}` : '模型原文'}</span><span>{item.controlled ? '受控规则对比' : item.executor === 'api' ? 'API 生成运行' : '外部非受控运行'}</span></div><div className="runtime-identity"><strong>{item.runtime_label}</strong><code>{item.runtime_fingerprint.slice(0, 12)}</code></div>{editing === item.id ? <textarea className="result-editor" value={draft} onChange={(e) => setDraft(e.target.value)} /> : <div className="result-body">{item.current_content}</div>}<footer><div><button title="复制" onClick={() => void navigator.clipboard.writeText(item.current_content)}><Copy size={15} /></button><a title="导出 Markdown" href={api.exportUrl(item.id)}><Download size={15} /></a><button title="编辑" onClick={() => beginEdit(item)}><Edit3 size={15} /></button></div>{editing === item.id ? <button className="button primary small" disabled={!draft.trim()} onClick={() => void run(async () => { await api.editResult(item.id, draft); setEditing(null) }, '人工修订已保存，结果已恢复为未审阅').catch(() => undefined)}><Save size={14} />保存修订</button> : <div className="review-actions"><button className="button secondary small" disabled={item.review_state === 'accepted'} onClick={() => void review(item, 'accepted').catch(() => undefined)}><Check size={14} />接受</button><button className="button secondary small" disabled={item.review_state === 'rejected'} onClick={() => void review(item, 'rejected').catch(() => undefined)}><X size={14} />拒绝</button>{item.review_state !== 'unreviewed' && <button className="button ghost small" onClick={() => void review(item, 'unreviewed').catch(() => undefined)}><RotateCcw size={14} />撤回</button>}</div>}</footer><details className="result-metadata"><summary>查看本次完整输入与运行快照</summary><div><h4>写作规则</h4><pre>{item.writing_rule.body}</pre><h4>模型配置</h4><pre>{Object.keys(item.provider_snapshot).length ? JSON.stringify(item.provider_snapshot, null, 2) : '外部执行未使用 InkFlow 模型配置'}</pre><h4>提示词快照</h4><pre>{JSON.stringify(item.prompt_snapshot, null, 2)}</pre><h4>执行元数据</h4><pre>{JSON.stringify(item.executor_metadata, null, 2)}</pre></div></details></article>)}</div>{!visible.length && <div className="empty-state wide"><Edit3 size={28} /><h3>还没有生成结果</h3><p>完成单篇、批量或五规则受控对比后，原始结果会出现在这里并等待你的审阅。</p></div>}</div>
}
