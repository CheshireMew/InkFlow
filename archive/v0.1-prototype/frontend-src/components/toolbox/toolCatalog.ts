import type { ToolDefinition } from './types'

export const AVAILABLE_TOOLS: ToolDefinition[] = [
  {
    id: 'input',
    type: 'text_input',
    label: '📝 基础输入 (Input)',
    config: { placeholder: '在此输入原始内容...' },
  },
  {
    id: 'tweet_gen',
    type: 'llm_generate',
    label: '🐦 推文生成 (Tweet)',
    config: {
      model: 'deepseek-chat',
      output_format: 'json',
      prompt_template: '请根据用户的输入生成 5 条风格迥异的 Twitter 推文。\n\n用户输入：{{ user_input }}\n\n请严格以 JSON 数组格式输出，每个元素包含 "label"（风格）和 "content"（正文）。\n示例：\n[{"label": "幽默", "content": "..."}]',
    },
  },
  {
    id: 'translator',
    type: 'llm_generate',
    label: '🌏 中英翻译 (Translate)',
    config: {
      model: 'deepseek-chat',
      prompt_template: '请将以下内容翻译成流畅的中文（如果是中文则翻成英文）：\n\n{{ user_input }}\n\n直接输出翻译结果。',
    },
  },
  {
    id: 'expander',
    type: 'llm_generate',
    label: '✍️ 文章扩写 (Expand)',
    config: {
      model: 'deepseek-chat',
      prompt_template: '请将以下简短内容扩写不低于 300 字的短文，保持语气自然：\n\n{{ user_input }}',
    },
  },
]

export function getToolDefinition(toolId: string) {
  return AVAILABLE_TOOLS.find((tool) => tool.id === toolId) || AVAILABLE_TOOLS[0]
}
