import { useEffect } from 'react'
import { useUiDispatch, useUiState } from '../state/uiState'

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  )
}

/**
 *  /    focus the search box of the current panel (switching to Lines if it has none)
 *  Esc  clear the selected line and close popups
 *  [    show or hide the side panel
 */
export function useKeyboardShortcuts(): void {
  const { tab, sidebarOpen } = useUiState()
  const dispatch = useUiDispatch()

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === 'Escape') {
        dispatch({ type: 'clearSelection' })
        return
      }
      if (isTyping(event.target)) return

      if (event.key === '/') {
        event.preventDefault()
        if (tab !== 'lines' && tab !== 'stops') dispatch({ type: 'setTab', tab: 'lines' })
        else if (!sidebarOpen) dispatch({ type: 'setSidebarOpen', open: true })
        // Wait for the panel to render before focusing.
        requestAnimationFrame(() =>
          document.querySelector<HTMLInputElement>('[data-search-input]')?.focus(),
        )
      } else if (event.key === '[') {
        dispatch({ type: 'setSidebarOpen', open: !sidebarOpen })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [tab, sidebarOpen, dispatch])
}
