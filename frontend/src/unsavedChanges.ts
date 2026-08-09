import { useEffect } from 'react'

const dirtyEditors = new Set<string>()

export function useUnsavedChanges(editor: string, dirty: boolean) {
  useEffect(() => {
    if (dirty) dirtyEditors.add(editor)
    else dirtyEditors.delete(editor)
    return () => { dirtyEditors.delete(editor) }
  }, [dirty, editor])

  useEffect(() => {
    const protectWindow = (event: BeforeUnloadEvent) => {
      if (!dirtyEditors.size) return
      event.preventDefault()
    }
    window.addEventListener('beforeunload', protectWindow)
    return () => window.removeEventListener('beforeunload', protectWindow)
  }, [])
}

export function confirmDiscardUnsavedChanges(): boolean {
  if (!dirtyEditors.size) return true
  if (!window.confirm('当前页面有尚未保存的修改。确定放弃并离开吗？')) return false
  dirtyEditors.clear()
  return true
}

export function markEditorSaved(editor: string) {
  dirtyEditors.delete(editor)
}
