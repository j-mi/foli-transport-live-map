import { useCallback } from 'react'
import { useMediaQuery, useUiDispatch } from '../state/uiState'

export const NARROW_SCREEN = '(max-width: 720px)'

/** On phones the sidebar is a bottom sheet over the map; lower it after the user picks a place. */
export function useRevealMap(): () => void {
  const dispatch = useUiDispatch()
  const narrow = useMediaQuery(NARROW_SCREEN)
  return useCallback(() => {
    if (narrow) dispatch({ type: 'setSidebarOpen', open: false })
  }, [narrow, dispatch])
}
