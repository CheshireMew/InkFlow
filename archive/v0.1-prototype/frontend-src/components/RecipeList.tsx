import { Twitter, Megaphone, BookOpen, FileText, Pencil, Languages, Sparkles } from 'lucide-react'

interface Recipe {
  id: string
  name: string
  category: string
  description: string
  step_count?: number
  tags?: string[]
}

interface RecipeListProps {
  recipes: Recipe[]
  onSelect: (recipeId: string) => void
  onToolbox?: () => void
}

const categoryIcons: Record<string, React.ReactNode> = {
  social: <Twitter className="w-5 h-5" />,
  marketing: <Megaphone className="w-5 h-5" />,
  learning: <BookOpen className="w-5 h-5" />,
  long_form: <FileText className="w-5 h-5" />,
  tools: <Languages className="w-5 h-5" />, // 新增图标
  other: <Pencil className="w-5 h-5" />
}

const categoryLabels: Record<string, string> = {
  social: '社交媒体',
  marketing: '营销推广',
  learning: '学习笔记',
  long_form: '长文章',
  tools: '实用工具', // 新增标签
  other: '其他'
}

export default function RecipeList({ recipes, onSelect, onToolbox }: RecipeListProps) {
  // Group by category
  const grouped = recipes.reduce((acc, recipe) => {
    const cat = recipe.category || 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(recipe)
    return acc
  }, {} as Record<string, Recipe[]>)

  if (recipes.length === 0) {
    return (
      <div className="text-center py-20 opacity-50">
        <div className="text-6xl mb-4 grayscale">📭</div>
        <h2 className="text-xl text-[var(--text-muted)]">暂无可用配方</h2>
        <p className="text-sm text-[var(--text-dim)] mt-2">
          请确保后端服务正在运行
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-12">
      <div className="text-center mb-12 relative">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 bg-[var(--primary)] rounded-full blur-[80px] opacity-20 pointer-events-none" />
        <h2 className="text-4xl font-bold mb-3 tracking-tight text-white">选择创作模版</h2>
        <p className="text-[var(--text-muted)] text-lg max-w-lg mx-auto">
          让 AI 成为你的灵感催化剂，从这里开始你的创作之旅
        </p>
      </div>

      {/* Toolbox Card - Special Entry */}
      {onToolbox && (
        <div className="mb-8">
          <button
            onClick={onToolbox}
            className="w-full glass-panel text-left p-6 rounded-2xl group transition-all duration-300 hover:scale-[1.01] hover:bg-gradient-to-r hover:from-indigo-500/10 hover:to-purple-500/10 relative overflow-hidden border-2 border-dashed border-indigo-500/30 hover:border-indigo-500/60"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-indigo-500/5 to-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="relative z-10 flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <div className="flex-1">
                <h4 className="text-lg font-semibold text-white group-hover:text-indigo-400 transition-colors flex items-center gap-2">
                  🧪 自由组合工坊
                  <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-[10px] font-medium text-indigo-400 border border-indigo-500/30">
                    NEW
                  </span>
                </h4>
                <p className="text-sm text-[var(--text-muted)] mt-1">
                  随心所欲地组合工具：输入 → 生成 → 翻译 → 扩写，打造你自己的工作流
                </p>
              </div>
            </div>
          </button>
        </div>
      )}

      {Object.entries(grouped).map(([category, categoryRecipes]) => (
        <div key={category} className="animate-float" style={{ animationDuration: '0s' }}>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-dim)] mb-6 flex items-center gap-2 pl-1">
            <span className="text-[var(--primary)]">
              {categoryIcons[category]}
            </span>
            {categoryLabels[category] || category}
          </h3>
          
          <div className="grid gap-6 md:grid-cols-2">
            {categoryRecipes.map(recipe => (
              <button
                key={recipe.id}
                onClick={() => onSelect(recipe.id)}
                className="glass-panel text-left p-6 rounded-2xl group transition-all duration-300 hover:scale-[1.02] hover:bg-[var(--bg-card-hover)] relative overflow-hidden"
              >
                {/* Hover Glow */}
                <div className="absolute inset-0 bg-gradient-to-r from-[var(--primary-glow)] to-transparent opacity-0 group-hover:opacity-10 transition-opacity duration-500" />
                
                <div className="relative z-10">
                  <div className="flex justify-between items-start mb-3">
                    <h4 className="text-lg font-semibold text-white group-hover:text-[var(--primary)] transition-colors">
                      {recipe.name}
                    </h4>
                    <span className="text-xs font-medium text-[var(--text-dim)] bg-white/5 px-2.5 py-1 rounded-full border border-white/5">
                      {recipe.step_count || 4} 步骤
                    </span>
                  </div>
                  
                  {recipe.description && (
                    <p className="text-sm text-[var(--text-muted)] leading-relaxed mb-4">
                      {recipe.description}
                    </p>
                  )}
                  
                  <div className="flex flex-wrap gap-2">
                    {recipe.tags && recipe.tags.slice(0, 3).map(tag => (
                      <span
                        key={tag}
                        className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-[var(--primary)]/10 text-[var(--primary)] border border-[var(--primary)]/20"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
