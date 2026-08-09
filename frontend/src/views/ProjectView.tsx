import { ArrowLeft, Check, FileStack, FlaskConical, Layers3, ScrollText } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { ExperimentStage } from '../components/project/ExperimentStage'
import { HandoffStage } from '../components/project/HandoffStage'
import { InputsStage } from '../components/project/InputsStage'
import { PreparationStage } from '../components/project/PreparationStage'
import { ResultsStage } from '../components/project/ResultsStage'
import type { Generation, Handoff, ProjectActivity, ProjectDetail, ProjectStage, Prompt, ProviderProfile, WritingRule } from '../types'

const stages: Array<{ id: ProjectStage; number: string; label: string; icon: typeof FileStack }> = [
  { id: 'inputs', number: '01', label: '要求与材料', icon: FileStack },
  { id: 'prepare', number: '02', label: '准备交接', icon: Layers3 },
  { id: 'handoff', number: '03', label: '审阅交接', icon: ScrollText },
  { id: 'experiments', number: '04', label: '生成与对比', icon: FlaskConical },
  { id: 'results', number: '05', label: '结果工作区', icon: Check },
]

export function ProjectView({ projectId, stage, onStage, perform, onBack }: { projectId: string; stage: ProjectStage; onStage: (stage: ProjectStage) => void; perform: (action: () => Promise<unknown>, message: string) => Promise<void>; onBack: () => void }) {
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [handoff, setHandoff] = useState<Handoff | null>(null)
  const [handoffHistory, setHandoffHistory] = useState<Handoff[]>([])
  const [rules, setRules] = useState<WritingRule[]>([])
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [providers, setProviders] = useState<ProviderProfile[]>([])
  const [results, setResults] = useState<Generation[]>([])
  const [activity, setActivity] = useState<ProjectActivity | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const fetchState = useCallback(() => Promise.all([
      api.project(projectId), api.handoffs(projectId), api.rules(), api.prompts(), api.providers(), api.results(projectId), api.projectActivity(projectId),
    ]), [projectId])
  const applyState = useCallback((state: Awaited<ReturnType<typeof fetchState>>) => {
    const [nextDetail, nextHistory, nextRules, nextPrompts, nextProviders, nextResults, nextActivity] = state
    setDetail(nextDetail); setHandoffHistory(nextHistory); setHandoff(nextHistory.find((item) => item.handoff.status !== 'superseded') ?? null); setRules(nextRules); setPrompts(nextPrompts); setProviders(nextProviders); setResults(nextResults); setActivity(nextActivity); setLoadError(null)
  }, [])
  const load = useCallback(async () => {
    try { applyState(await fetchState()) }
    catch (error) { setLoadError(error instanceof Error ? error.message : '写作桌面读取失败'); throw error }
  }, [applyState, fetchState])
  useEffect(() => {
    let activeRequest = true
    void fetchState().then((state) => { if (activeRequest) applyState(state) }).catch((error: unknown) => { if (activeRequest) setLoadError(error instanceof Error ? error.message : '写作桌面读取失败') })
    return () => { activeRequest = false }
  }, [applyState, fetchState])
  useEffect(() => {
    if (!activity?.active) return
    const timer = window.setInterval(() => {
      void api.projectActivity(projectId).then(async (next) => {
        if (next.state_token !== activity.state_token) await load()
        else setActivity(next)
      }).catch((error: unknown) => setLoadError(error instanceof Error ? error.message : '任务状态读取失败'))
    }, 1600)
    return () => window.clearInterval(timer)
  }, [activity, load, projectId])
  if (!detail) return <div className="page loading-page">{loadError ? <div className="load-error"><strong>写作桌面未能打开</strong><p>{loadError}</p><button className="button secondary" onClick={() => void load().catch(() => undefined)}>重新读取</button></div> : '正在打开写作桌面……'}</div>
  const run = async (action: () => Promise<unknown>, message: string) => { await perform(action, message); await load() }
  const approved = handoff?.handoff.status === 'approved'

  return <div className="project-page">
    <header className="project-topbar"><button className="back-button" onClick={onBack}><ArrowLeft size={17} />全部项目</button><div><p className="kicker">WRITING PROJECT</p><h1>{detail.project.title}</h1></div><div className={`approval-state ${approved ? 'approved' : ''}`}><span />{approved ? `交接 v${handoff?.handoff.revision} 已批准` : handoff ? `交接 v${handoff.handoff.revision} 待审` : '尚未形成交接'}</div></header>
    <nav className="project-stages" aria-label="项目阶段">{stages.map((item) => { const Icon = item.icon; return <button key={item.id} aria-current={stage === item.id ? 'step' : undefined} className={stage === item.id ? 'active' : ''} onClick={() => onStage(item.id)}><span>{item.number}</span><Icon size={16} /><strong>{item.label}</strong></button> })}</nav>
    <div className="project-canvas">
      {loadError && <div className="warning-box load-warning"><span>!</span><p>{loadError}。当前仍显示上次成功读取的内容。</p><button className="button ghost small" onClick={() => void load().catch(() => undefined)}>重试</button></div>}
      {stage === 'inputs' && <InputsStage key={detail.project.input_revision} detail={detail} run={run} />}
      {stage === 'prepare' && <PreparationStage detail={detail} prompts={prompts} providers={providers} run={run} onContinue={() => onStage('handoff')} />}
      {stage === 'handoff' && <HandoffStage key={handoff?.handoff.id ?? 'empty'} projectId={projectId} handoff={handoff} history={handoffHistory} run={run} onContinue={() => onStage('experiments')} />}
      {stage === 'experiments' && <ExperimentStage projectId={projectId} handoff={handoff} detail={detail} rules={rules} prompts={prompts} providers={providers} run={run} onResults={() => onStage('results')} />}
      {stage === 'results' && <ResultsStage results={results} experiments={detail.experiments} run={run} />}
    </div>
  </div>
}
