import { useState, useEffect } from 'react'
import ToolboxWorkspace from './components/toolbox/Workspace'
// CSS import
import './index.css'

export default function App() {
  const [mounted, setMounted] = useState(false)

  // Prevent hydration mismatch
  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null

  return (
    <div className="flex h-screen bg-[var(--bg-main)] text-[var(--text-main)] overflow-hidden font-sans selection:bg-[var(--primary)] selection:text-white">
      <div className="flex-1 flex flex-col h-full relative overflow-y-auto custom-scrollbar">
          <ToolboxWorkspace />
      </div>
    </div>
  )
}
