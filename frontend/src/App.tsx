import { useState, useEffect } from 'react'
import { Rocket, Trash2 } from 'lucide-react'
import RecipeList from './components/RecipeList'
import Pipeline from './components/Pipeline'
import ToolboxWorkspace from './components/toolbox/Workspace'

interface Recipe {
  id: string
  name: string
  category: string
  description: string
  step_count?: number
  tags?: string[]
}

type AppMode = 'recipes' | 'pipeline' | 'toolbox'

function App() {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [activeRecipeId, setActiveRecipeId] = useState<string | null>(() => {
    // Force reset on major updates
    const APP_VERSION = '3.1.0'
    if (localStorage.getItem('inkflow_version') !== APP_VERSION) {
        console.log("✨ InkFlow Upgraded: Clearing local cache")
        localStorage.clear()
        localStorage.setItem('inkflow_version', APP_VERSION)
        return null
    }
    return localStorage.getItem('inkflow_active_recipe')
  })
  const [mode, setMode] = useState<AppMode>(() => (
    localStorage.getItem('inkflow_active_recipe') ? 'pipeline' : 'recipes'
  ))

  useEffect(() => {
    fetch('/api/recipes/')
      .then(res => res.json())
      .then(data => setRecipes(data))
      .catch(err => console.error("Failed to fetch recipes:", err))
  }, [])

  const handleSelectRecipe = (recipeId: string) => {
    // No longer creates pipeline on backend - just store recipe ID
    setActiveRecipeId(recipeId)
    localStorage.setItem('inkflow_active_recipe', recipeId)
    setMode('pipeline')
  }

  const handleToolbox = () => {
    setMode('toolbox')
  }

  const handleReset = () => {
    setActiveRecipeId(null)
    localStorage.removeItem('inkflow_active_recipe')
    setMode('recipes')
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 font-sans selection:bg-indigo-500/30">
        {/* Header */}
        <header className="border-b border-neutral-800 bg-neutral-900/50 backdrop-blur-md sticky top-0 z-50">
          <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                <Rocket className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-neutral-400">
                InkFlow
              </h1>
              <span className="px-2 py-0.5 rounded-full bg-neutral-800 text-[10px] font-mono text-neutral-400 border border-neutral-700">
                v3.1.0
              </span>
            </div>

            {mode !== 'recipes' && (
              <button 
                onClick={handleReset}
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-neutral-400 hover:text-red-400 hover:bg-red-400/10 rounded-md transition-colors"
              >
                <Trash2 className="w-4 h-4" />
                <span>返回首页</span>
              </button>
            )}
          </div>
        </header>

        {/* Main Content */}
        <main className="max-w-5xl mx-auto px-6 py-8">
          {mode === 'recipes' && (
            <RecipeList recipes={recipes} onSelect={handleSelectRecipe} onToolbox={handleToolbox} />
          )}
          {mode === 'pipeline' && activeRecipeId && (
            <Pipeline 
                recipeId={activeRecipeId} 
                onComplete={handleReset} 
            />
          )}
          {mode === 'toolbox' && (
            <ToolboxWorkspace />
          )}
        </main>
    </div>
  )
}

export default App
