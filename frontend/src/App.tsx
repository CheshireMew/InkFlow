import { LoaderCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { AppShell } from './components/AppShell'
import type { Project, ProjectStage, ViewId } from './types'
import { HomeView } from './views/HomeView'
import { LibraryView } from './views/LibraryView'
import { ProjectView } from './views/ProjectView'
import { PromptStudio } from './views/PromptStudio'
import { ProviderView } from './views/ProviderView'

type Notice = { kind: 'ok' | 'error'; text: string } | null

export default function App() {
  const initialRoute = readRoute()
  const [projects, setProjects] = useState<Project[]>([])
  const [view, setView] = useState<ViewId>(initialRoute.view)
  const [projectId, setProjectId] = useState<string | null>(initialRoute.projectId)
  const [projectStage, setProjectStage] = useState<ProjectStage>(initialRoute.stage)
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)

  const reloadProjects = useCallback(async () => setProjects(await api.projects()), [])
  useEffect(() => { void reloadProjects() }, [reloadProjects])
  useEffect(() => {
    const restore = () => {
      const route = readRoute()
      setView(route.view); setProjectId(route.projectId); setProjectStage(route.stage)
    }
    window.addEventListener('hashchange', restore)
    return () => window.removeEventListener('hashchange', restore)
  }, [])
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 4200)
    return () => window.clearTimeout(timer)
  }, [notice])

  const perform = useCallback(async (action: () => Promise<unknown>, message: string) => {
    setBusy(true)
    try {
      await action()
      await reloadProjects()
      setNotice({ kind: 'ok', text: message })
    } catch (error) {
      setNotice({ kind: 'error', text: error instanceof Error ? error.message : '操作失败' })
      throw error
    } finally {
      setBusy(false)
    }
  }, [reloadProjects])

  const openProject = (id: string, stage: ProjectStage = 'inputs') => { window.location.hash = `/project/${id}/${stage}` }
  const navigate = (next: ViewId) => { window.location.hash = `/${next}` }
  const changeProjectStage = (stage: ProjectStage) => { if (projectId) openProject(projectId, stage) }

  return <AppShell projects={projects} view={view} selectedProjectId={projectId} onNavigate={navigate} onProject={openProject} onNewProject={() => { setView('projects'); setCreateOpen(true) }}>
    {view === 'projects' && <HomeView projects={projects} createOpen={createOpen} onCreateOpen={setCreateOpen} onCreated={openProject} onProject={openProject} perform={perform} />}
    {view === 'prompts' && <PromptStudio perform={perform} />}
    {view === 'library' && <LibraryView perform={perform} />}
    {view === 'providers' && <ProviderView perform={perform} />}
    {view === 'project' && projectId && <ProjectView projectId={projectId} stage={projectStage} onStage={changeProjectStage} perform={perform} onBack={() => navigate('projects')} />}
    {busy && <div className="busy-indicator"><LoaderCircle className="spin" size={17} />正在提交到本地工作台</div>}
    {notice && <div role="status" className={`toast ${notice.kind}`}>{notice.text}</div>}
  </AppShell>
}

function readRoute(): { view: ViewId; projectId: string | null; stage: ProjectStage } {
  const parts = window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const globalViews: ViewId[] = ['projects', 'prompts', 'library', 'providers']
  const projectStages: ProjectStage[] = ['inputs', 'prepare', 'handoff', 'experiments', 'results']
  if (parts[0] === 'project' && parts[1]) {
    return { view: 'project', projectId: parts[1], stage: projectStages.includes(parts[2] as ProjectStage) ? parts[2] as ProjectStage : 'inputs' }
  }
  return { view: globalViews.includes(parts[0] as ViewId) ? parts[0] as ViewId : 'projects', projectId: null, stage: 'inputs' }
}
