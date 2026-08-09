import { ArrowRight, FilePlus2, FolderOpen, WandSparkles } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import type { Project } from '../types'

type Props = {
  projects: Project[]
  createOpen: boolean
  onCreateOpen: (value: boolean) => void
  onCreated: (id: string) => void
  onProject: (id: string) => void
  perform: (action: () => Promise<unknown>, message: string) => Promise<void>
}

export function HomeView({ projects, createOpen, onCreateOpen, onCreated, onProject, perform }: Props) {
  const [title, setTitle] = useState('')
  const [request, setRequest] = useState('')
  const [material, setMaterial] = useState('')

  const create = async () => {
    let createdId = ''
    await perform(async () => {
      const result = await api.createProject({ title, user_request: request, materials: material.trim() ? [material] : [] })
      createdId = result.project_id
    }, '项目已创建')
    if (createdId) {
      setTitle(''); setRequest(''); setMaterial(''); onCreateOpen(false); onCreated(createdId)
    }
  }

  return <div className="page page-home">
    <header className="page-hero">
      <div><p className="kicker">WRITING OPERATIONS</p><h1>把材料、提示词和每一次成稿，<em>放在同一张写作桌上。</em></h1><p>从材料净化到五规则对比，所有输入都有版本，所有结果都能回到当时的真实运行现场。</p></div>
      <button className="button primary large" onClick={() => onCreateOpen(true)}><FilePlus2 size={18} />新建写作项目</button>
    </header>
    {createOpen && <section className="sheet create-sheet">
      <div className="sheet-heading"><div><span className="step-number">01</span><h2>先说清楚这次要写什么</h2></div><button className="text-button" onClick={() => onCreateOpen(false)}>收起</button></div>
      <div className="form-grid two"><label>项目名称<input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例如：X 原创内容奖励计划" /></label><label className="span-2">原始写作要求<textarea rows={4} value={request} onChange={(e) => setRequest(e.target.value)} placeholder="原样记录你的要求，不自动改写。" /></label><label className="span-2">第一份材料（可稍后补充）<textarea rows={7} value={material} onChange={(e) => setMaterial(e.target.value)} placeholder="粘贴原文、会议记录或研究材料……" /></label></div>
      <div className="sheet-actions"><p>写作要求将作为项目真源，修改后需要重新准备交接。</p><button className="button primary" disabled={!title.trim() || !request.trim()} onClick={create}><WandSparkles size={16} />建立工作区</button></div>
    </section>}
    <section className="home-section">
      <div className="section-heading"><div><p className="kicker">WORKSPACES</p><h2>最近的写作项目</h2></div><span>{projects.length} 个项目</span></div>
      <div className="project-grid">
        {projects.map((project, index) => <button className="project-tile" key={project.id} onClick={() => onProject(project.id)}><span className="project-index">{String(index + 1).padStart(2, '0')}</span><div><h3>{project.title}</h3><p>{project.user_request}</p><small>更新于 {new Date(project.updated_at).toLocaleString()}</small></div><ArrowRight size={18} /></button>)}
        {!projects.length && <div className="empty-state"><FolderOpen size={28} /><h3>桌面还是空的</h3><p>新建第一个项目，InkFlow 会引导你从材料走到可导出的成稿。</p></div>}
      </div>
    </section>
  </div>
}
