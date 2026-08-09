import { BookOpenText, Boxes, Feather, Library, Plus, Settings2, SlidersHorizontal } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Project, ViewId } from '../types'

type Props = {
  children: ReactNode
  projects: Project[]
  view: ViewId
  selectedProjectId: string | null
  onNavigate: (view: ViewId) => void
  onProject: (id: string) => void
  onNewProject: () => void
}

const globalItems: Array<{ id: ViewId; label: string; icon: typeof Boxes }> = [
  { id: 'projects', label: '项目总览', icon: Boxes },
  { id: 'prompts', label: '提示词工坊', icon: SlidersHorizontal },
  { id: 'library', label: '案例与钩子', icon: Library },
  { id: 'providers', label: '模型与 API', icon: Settings2 },
]

export function AppShell({ children, projects, view, selectedProjectId, onNavigate, onProject, onNewProject }: Props) {
  return <div className="app-frame">
    <aside className="sidebar">
      <div className="wordmark"><span><Feather size={18} /></span><div><strong>InkFlow</strong><small>写作实验工作台</small></div></div>
      <nav className="primary-nav" aria-label="全局导航">
        {globalItems.map((item) => {
          const Icon = item.icon
          return <button key={item.id} className={view === item.id ? 'active' : ''} onClick={() => onNavigate(item.id)}><Icon size={17} /><span>{item.label}</span></button>
        })}
      </nav>
      <div className="sidebar-section-head"><span>最近项目</span><button title="新建项目" onClick={onNewProject}><Plus size={15} /></button></div>
      <div className="project-nav">
        {projects.map((project) => <button key={project.id} className={view === 'project' && selectedProjectId === project.id ? 'active' : ''} onClick={() => onProject(project.id)}><BookOpenText size={15} /><span><strong>{project.title}</strong><small>{project.user_request}</small></span></button>)}
        {!projects.length && <p>还没有写作项目</p>}
      </div>
      <div className="sidebar-foot"><span className="connection-dot" />本地数据 · SQLite</div>
    </aside>
    <main className="app-main">{children}</main>
  </div>
}
