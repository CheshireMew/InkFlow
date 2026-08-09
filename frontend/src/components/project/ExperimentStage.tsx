import { ArrowRight, CheckCircle2, FileText, FlaskConical, Layers3, Plus, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Executor, Handoff, ProjectDetail, Prompt, ProviderProfile, WritingRule } from '../../types'
import { useUnsavedChanges } from '../../unsavedChanges'

export function ExperimentStage({ projectId, handoff, detail, rules, prompts, providers, run, onResults }: { projectId: string; handoff: Handoff | null; detail: ProjectDetail; rules: WritingRule[]; prompts: Prompt[]; providers: ProviderProfile[]; run: (action: () => Promise<unknown>, message: string) => Promise<void>; onResults: () => void }) {
  const [executor, setExecutor] = useState<Executor>('api')
  const [provider, setProvider] = useState(providers.find((item) => item.active)?.id ?? '')
  const providerId = provider || providers.find((item) => item.active)?.id || ''
  const generationPrompt = prompts.find((item) => item.stage === 'generate')
  const [ruleName, setRuleName] = useState('短内容写作规则')
  const [ruleBody, setRuleBody] = useState('')
  useUnsavedChanges('new-writing-rule', ruleName !== '短内容写作规则' || Boolean(ruleBody.trim()))
  const activeRule = rules.find((item) => item.active)
  const comparisonRules = useMemo(() => { const seen = new Set<string>(); return rules.filter((item) => !seen.has(item.body_hash) && Boolean(seen.add(item.body_hash))).slice(0, 5) }, [rules])
  const approved = handoff?.handoff.status === 'approved'
  const common = { executor, rule_id: activeRule?.id, provider_profile_id: executor === 'api' ? providerId || undefined : undefined }
  const start = (mode: 'single' | 'batch' | 'compare') => run(
    () => mode === 'single'
      ? api.generate(projectId, common)
      : mode === 'batch'
        ? api.batchFive(projectId, common)
        : api.compareRules(projectId, { rule_ids: comparisonRules.map((item) => item.id), provider_profile_id: providerId }),
    mode === 'single' ? '单篇生成任务已创建' : mode === 'batch' ? '五篇批量任务已创建' : '五规则受控对比已创建',
  )
  return <div className="experiment-layout">
    <section className="sheet experiment-console"><div className="stage-heading"><span>04</span><div><p className="kicker">GENERATION LAB</p><h2>选择生成或受控对比</h2><p>每次运行只交付原始结果，不自动评审、改写或融合；是否接受由你明确决定。</p></div></div>{!approved && <div className="warning-box"><FlaskConical size={17} /><p>生成已锁定。先完成并批准当前交接，旧交接不能自动混入新任务。</p></div>}<div className="runtime-strip"><label>单篇 / 批量执行方式<select value={executor} onChange={(e) => setExecutor(e.target.value as Executor)}><option value="api">工作台内 API（运行条件可记录）</option><option value="external">外部 Agent / Codex（非受控）</option></select></label><label>受控对比模型<select value={providerId} onChange={(e) => setProvider(e.target.value)}><option value="">选择当前配置</option>{providers.map((item) => <option value={item.id} key={item.id}>{item.name} v{item.revision} · {item.model}</option>)}</select></label><label>当前生成提示词<input value={generationPrompt?.name ?? '未配置'} readOnly /></label></div>{executor === 'external' && <div className="warning-box"><FlaskConical size={17} /><p>外部运行可用于单篇或批量生成，但环境、模型和上下文不能由 InkFlow 固定，因此不会被标记为受控实验。提交结果时必须声明实际运行时与模型。</p></div>}<div className="experiment-options"><button disabled={!approved || !activeRule || !generationPrompt || (executor === 'api' && !providerId)} onClick={() => void start('single').catch(() => undefined)}><span><FileText size={20} /></span><div><strong>单篇生成</strong><p>一次调用，一篇完整成品；结果先进入未审阅。</p></div><ArrowRight size={17} /></button><button disabled={!approved || !activeRule || !generationPrompt || (executor === 'api' && !providerId)} onClick={() => void start('batch').catch(() => undefined)}><span><Layers3 size={20} /></span><div><strong>同规则五篇</strong><p>一次调用返回五篇，五个结果全部保留。</p></div><ArrowRight size={17} /></button><button disabled={!approved || comparisonRules.length !== 5 || !generationPrompt || !providerId} onClick={() => void start('compare').catch(() => undefined)}><span><Sparkles size={20} /></span><div><strong>五规则受控对比</strong><p>{comparisonRules.length}/5 个不同规则；固定 API 模型、交接、提示词和生成设置。</p></div><ArrowRight size={17} /></button></div></section>
    <aside className="sheet rule-panel"><div className="sheet-heading"><div><p className="kicker">WRITING RULE</p><h2>写作规则版本</h2></div>{activeRule && <span className="active-badge"><CheckCircle2 size={14} />v{activeRule.revision}</span>}</div>{activeRule ? <details open><summary>{activeRule.name}</summary><pre>{activeRule.body}</pre></details> : <div className="empty-mini">尚未建立写作规则</div>}<details className="new-rule"><summary><Plus size={14} />新增规则版本</summary><div className="details-form"><label>规则名称<input value={ruleName} onChange={(e) => setRuleName(e.target.value)} /></label><label>规则正文<textarea rows={9} value={ruleBody} onChange={(e) => setRuleBody(e.target.value)} /></label><button className="button secondary full" disabled={!ruleName.trim() || !ruleBody.trim()} onClick={() => void run(async () => { await api.addRule({ name: ruleName, body: ruleBody, activate: true }); setRuleBody('') }, '写作规则新版本已启用').catch(() => undefined)}>保存并启用</button></div></details><div className="rule-history">{rules.slice(0, 8).map((item) => <button className={item.active ? 'active' : ''} key={item.id} onClick={() => void run(() => api.activateRule(item.id), '写作规则已切换').catch(() => undefined)}><span>v{item.revision}</span><strong>{item.name}</strong><small>{item.body_hash.slice(0, 8)}</small></button>)}</div></aside>
    <section className="sheet experiment-history"><div className="sheet-heading"><div><p className="kicker">RUN HISTORY</p><h2>运行记录</h2></div><button className="button ghost" disabled={!detail.experiments.length} onClick={onResults}>查看全部结果<ArrowRight size={15} /></button></div><div className="experiment-table">{detail.experiments.map((item) => <article key={item.id}><span className={`job-state ${item.status}`} /><div><strong>{item.kind === 'single' ? '单篇生成' : item.kind === 'batch_five' ? '同规则五篇' : '五规则受控对比'}</strong><small>{new Date(item.created_at).toLocaleString()} · {item.executor === 'api' ? '内置 API · 可核对运行条件' : '外部执行 · 非受控'}</small></div><em>{item.status === 'completed' ? '结果已返回' : item.status === 'failed' ? '运行失败' : '运行中'}</em><code>{item.input_package_hash.slice(0, 10)}</code></article>)}</div></section>
  </div>
}
