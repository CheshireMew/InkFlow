import { useState } from 'react'
import { Plus, Trash2, LayoutGrid, Settings2, Play } from 'lucide-react'
import { executeAction } from '../../api/actionClient'
import TextInputStep from '../steps/TextInputStep'
import { Toaster } from 'sonner' // Restored locally if needed, or remove if causing issues. Removed from global App.tsx.

// --- Mock Step Component Wrapper ---
function ToolWrapper({ tool, action, onUpdate, onRun, previousData }: any) {
    // Config: Allow user to edit default config
    const [config, setConfig] = useState(tool.defaultConfig || {})
    const [showConfig, setShowConfig] = useState(false)
    const [manualInput, setManualInput] = useState('')
    
    // Sync internal config with external updates if tool defaults change (rare)
    // Actually we initialize once.

    const mockStep = {
        id: `action-${action.id}`,
        step_id: `step-${action.id}`,
        pipeline_id: 'toolbox-session',
        type: tool.type,
        label: tool.label,
        status: action.status,
        config: { ...config, ...tool.config }, 
        result: action.data,
        index: action.index || 0
    } as any

    const handleExecute = async (inputData: any) => {
        let finalInputs = { ...inputData }
        
        if (tool.type !== 'text_input') {
             // 1. Try Previous Data (Priority)
             if (previousData) {
                 const text = previousData.text || previousData.content || previousData.result || 
                              (Array.isArray(previousData) ? JSON.stringify(previousData) : null) ||
                              (typeof previousData === 'string' ? previousData : JSON.stringify(previousData))
                 
                 finalInputs['user_input'] = text
                 finalInputs['prev_output'] = previousData 
             } 
             // 2. Try Manual Input (Fallback)
             else if (manualInput.trim()) {
                 finalInputs['user_input'] = manualInput.trim()
             }
             // 3. System Fallback
             else {
                 // No input?
             }
        }

        // Merge User Config overriding Tool Config
        const finalConfig = { ...tool.config, ...config }

        onRun(tool.id, finalInputs, finalConfig)
    }

    // --- RENDERERS ---

    // 1. Input Tool
    if (tool.type === 'text_input') {
        return <TextInputStep 
            step={mockStep} 
            onExecute={handleExecute} 
            executing={action.status === 'running'} 
            isPipelineRunning={false} 
        />
    }

    // 2. LLM / Generator Tool
    if (tool.type === 'llm_generate') {
         // Determine if we have input
         const hasInput = !!previousData;
         
         return (
            <div className="space-y-4 border border-[var(--border-subtle)] p-4 rounded-xl bg-black/20 animate-in fade-in transition-all">
                {/* Header */}
                <div className="flex justify-between items-start">
                    <div>
                        <h3 className="font-semibold text-[var(--accent)] flex items-center gap-2">
                             {tool.label}
                        </h3>
                        <div className="text-xs text-[var(--text-dim)] mt-1">
                            {hasInput ? 'Linked to previous step' : 'Manual Input Mode'}
                        </div>
                    </div>
                   <button 
                        onClick={() => setShowConfig(!showConfig)}
                        className={`p-2 rounded-lg transition-colors ${showConfig ? 'bg-[var(--primary)]/20 text-[var(--primary)]' : 'hover:bg-black/20 text-[var(--text-dim)]'}`}
                    >
                        <Settings2 className="w-4 h-4" />
                   </button>
                </div>

                {/* Config Panel */}
                {showConfig && (
                    <div className="p-4 bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)] space-y-4 animate-in slide-in-from-top-2">
                        <div className="space-y-2">
                            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Prompt Template</label>
                            <textarea
                                value={config.prompt_template || tool.config.prompt_template || ''}
                                onChange={(e) => setConfig({ ...config, prompt_template: e.target.value })}
                                className="w-full h-32 bg-black/30 border border-[var(--border-subtle)] rounded-lg p-3 text-sm font-mono focus:border-[var(--primary)] focus:outline-none"
                                placeholder="{{ user_input }} will be replaced..."
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <label className="text-xs font-medium text-[var(--text-muted)]">Model</label>
                                <select 
                                    value={config.model || tool.config.model || 'deepseek-chat'}
                                    onChange={(e) => setConfig({ ...config, model: e.target.value })}
                                    className="w-full bg-black/30 border border-[var(--border-subtle)] rounded-lg p-2 text-sm focus:border-[var(--primary)] focus:outline-none"
                                >
                                    <option value="deepseek-chat">DeepSeek V3</option>
                                    <option value="deepseek-reasoner">DeepSeek R1</option>
                                    <option value="gpt-4o">GPT-4o</option>
                                </select>
                            </div>
                        </div>
                    </div>
                )}
                
                {/* Manual Input (If no previous data) */}
                {!previousData && (
                    <div className="space-y-2">
                         <label className="text-xs font-medium text-[var(--text-dim)] ml-1">Input Content</label>
                         <textarea
                            value={manualInput}
                            onChange={(e) => setManualInput(e.target.value)}
                            placeholder="Since there is no previous step, please type content here..."
                            className="w-full h-24 bg-black/20 border border-[var(--border-subtle)] rounded-xl p-3 text-sm focus:border-[var(--primary)] focus:outline-none transition-all"
                         />
                    </div>
                )}
                
                {/* Run Button */}
                <button 
                    onClick={() => handleExecute({})}
                    disabled={action.status === 'running' || (!previousData && !manualInput.trim())}
                    className="btn btn-primary w-full flex items-center justify-center gap-2 py-3 shadow-lg shadow-[var(--primary)]/10"
                >
                    {action.status === 'running' ? (
                        <>Processing...</>
                    ) : (
                        <>
                            <Play className="w-4 h-4 fill-current" />
                            Run Generator
                        </>
                    )}
                </button>

                {/* Result Area */}
                {action.data && (
                    <div className="mt-4 animate-in zoom-in-95 duration-300">
                        <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-xl overflow-hidden shadow-inner">
                             <div className="bg-black/20 px-4 py-2 text-xs font-medium text-[var(--text-dim)] border-b border-[var(--border-subtle)] flex justify-between">
                                <span>OUTPUT</span>
                                <span className={typeof action.data === 'string' && action.data.includes('Error') ? 'text-red-400' : 'text-green-400'}>
                                    {typeof action.data === 'string' && action.data.includes('Error') ? 'FAILED' : 'SUCCESS'}
                                </span>
                             </div>
                             <div className="p-4 text-sm whitespace-pre-wrap font-mono leading-relaxed max-h-96 overflow-y-auto custom-scrollbar">
                                {typeof action.data === 'string' ? action.data : JSON.stringify(action.data, null, 2)}
                             </div>
                        </div>
                    </div>
                )}
            </div>
        )
    }

    return <div>Unknown Tool Type</div>
}


// --- Main Workspace ---

const AVAILABLE_TOOLS = [
    { 
        id: 'input', 
        type: 'text_input', 
        label: '📝 基础输入 (Input)', 
        config: { placeholder: '在此输入原始内容...' } 
    },
    { 
        id: 'tweet_gen', 
        type: 'llm_generate', 
        label: '🐦 推文生成 (Tweet)', 
        config: { 
            model: 'deepseek-chat',
            output_format: 'json',
            prompt_template: '请根据用户的输入生成 5 条风格迥异的 Twitter 推文。\n\n用户输入：{{ user_input }}\n\n请严格以 JSON 数组格式输出，每个元素包含 "label"（风格）和 "content"（正文）。\n示例：\n[{"label": "幽默", "content": "..."}]'
        } 
    },
    {
        id: 'translator',
        type: 'llm_generate', 
        label: '🌏 中英翻译 (Translate)',
        config: {
             model: 'deepseek-chat',
             prompt_template: '请将以下内容翻译成流畅的中文（如果是中文则翻成英文）：\n\n{{ user_input }}\n\n直接输出翻译结果。'
        }
    },
    {
        id: 'expander',
        type: 'llm_generate',
        label: '✍️ 文章扩写 (Expand)',
        config: {
            model: 'deepseek-chat',
            prompt_template: '请将以下简短内容扩写不低于 300 字的短文，保持语气自然：\n\n{{ user_input }}'
        }
    }
]

export default function ToolboxWorkspace() {
    const [actions, setActions] = useState<any[]>([
        { id: 1, toolId: 'input', status: 'idle', data: null }
    ])

    const addAction = (toolId: string) => {
        setActions(prev => [
            ...prev,
            { id: Date.now(), toolId, status: 'idle', data: null }
        ])
    }
    
    const removeAction = (id: number) => {
         setActions(prev => prev.filter(a => a.id !== id))
    }

    const handleRun = async (actionId: number, toolId: string, inputs: any, config: any) => {
        setActions(prev => prev.map(a => a.id === actionId ? { ...a, status: 'running' } : a))
        const toolDef = AVAILABLE_TOOLS.find(t => t.id === toolId)
        
        // Call API
        const result = await executeAction(toolDef?.type || 'unknown', inputs, config) // Pass validated config
        
        setActions(prev => prev.map(a => a.id === actionId ? { 
            ...a, 
            status: result.success ? 'completed' : 'failed',
            data: result.data || result.error
        } : a))
    }

    return (
        <div className="max-w-3xl mx-auto p-4 space-y-8 pb-32">
             <div className="flex items-center gap-3 mb-8">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[var(--primary)] to-[var(--accent)] flex items-center justify-center text-white shadow-lg shadow-[var(--primary)]/20">
                    <LayoutGrid className="w-5 h-5" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Toolbox Playground</h1>
                    <p className="text-[var(--text-dim)]">Dynamic Action Composition</p>
                </div>
            </div>

            <div className="space-y-6">
                {actions.map((action, index) => {
                    const tool = AVAILABLE_TOOLS.find(t => t.id === action.toolId) || AVAILABLE_TOOLS[0]
                    const prevAction = index > 0 ? actions[index - 1] : null
                    
                    return (
                        <div key={action.id} className="relative pl-8 group">
                            {/* Connector Line */}
                            {index < actions.length - 1 && (
                                <div className="absolute left-[15px] top-10 bottom-[-24px] w-[2px] bg-[var(--border-subtle)] group-hover:bg-[var(--primary)] transition-colors" />
                            )}
                            {/* Dot */}
                            <div className={`absolute left-0 top-6 w-8 h-8 rounded-full border-4 border-[var(--bg-main)] flex items-center justify-center transition-all ${
                                action.status === 'completed' ? 'bg-[var(--accent)] text-white' : 'bg-[var(--bg-card)] text-[var(--text-muted)]'
                            }`}>
                                <span className="text-xs font-bold">{index + 1}</span>
                            </div>

                            <div className="relative bg-[var(--bg-panel)] border border-[var(--border-base)] rounded-2xl p-6 shadow-sm hover:shadow-md transition-all hover:border-[var(--border-hover)]">
                                {/* Header */}
                                <div className="flex justify-between items-start mb-4">
                                    <div className="flex items-center gap-2">
                                        <select 
                                            value={action.toolId}
                                            onChange={(e) => {
                                                const newTool = e.target.value
                                                setActions(prev => prev.map(a => a.id === action.id ? { ...a, toolId: newTool, data: null, status: 'idle' } : a))
                                            }}
                                            className="bg-transparent font-semibold text-[var(--text-main)] focus:outline-none cursor-pointer hover:text-[var(--primary)] transition-colors"
                                        >
                                            {AVAILABLE_TOOLS.map(t => (
                                                <option key={t.id} value={t.id} className="bg-[var(--bg-card)]">{t.label}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <button onClick={() => removeAction(action.id)} className="text-[var(--text-dim)] hover:text-[var(--error)] transition-colors p-2 hover:bg-black/10 rounded-lg">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>

                                {/* Body */}
                                <ToolWrapper 
                                    tool={tool} 
                                    action={action} 
                                    previousData={prevAction?.data}
                                    onRun={(tid: string, inputs: any, cfg: any) => handleRun(action.id, tid, inputs, cfg)}
                                />
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* Add Button */}
            <div className="flex justify-center pt-4">
                 <div className="flex gap-2 bg-[var(--bg-panel)] p-2 rounded-xl border border-[var(--border-subtle)] shadow-lg">
                    {AVAILABLE_TOOLS.map(t => (
                        <button 
                            key={t.id}
                            onClick={() => addAction(t.id)}
                            className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-[var(--bg-hover)] text-sm font-medium transition-colors"
                        >
                            <Plus className="w-4 h-4" />
                            {t.label}
                        </button>
                    ))}
                 </div>
            </div>
        </div>
    )
}
