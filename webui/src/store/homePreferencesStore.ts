import { create } from 'zustand'

export type HomeMode = 'min' | 'full'

interface HomePreferencesState {
  mode: HomeMode
  history: boolean
  recent: boolean
  setMode: (mode: HomeMode) => void
  setSection: (section: 'history' | 'recent', visible: boolean) => void
}

const STORAGE_KEY = 'siye-home-preferences'

function readPreferences(): Pick<HomePreferencesState, 'mode' | 'history' | 'recent'> {
  if (typeof window === 'undefined') return { mode: 'full', history: true, recent: true }
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') as Partial<HomePreferencesState>
    return {
      mode: value.mode === 'min' ? 'min' : 'full',
      history: typeof value.history === 'boolean' ? value.history : true,
      recent: typeof value.recent === 'boolean' ? value.recent : true,
    }
  } catch {
    return { mode: 'full', history: true, recent: true }
  }
}

function writePreferences(state: Pick<HomePreferencesState, 'mode' | 'history' | 'recent'>) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Storage can be unavailable in hardened browsers; the in-memory preference still works.
  }
}

const initial = readPreferences()

export const useHomePreferencesStore = create<HomePreferencesState>((set) => ({
  ...initial,
  setMode: (mode) => set((state) => {
    const next = { ...state, mode }
    writePreferences(next)
    return { mode }
  }),
  setSection: (section, visible) => set((state) => {
    const next = { ...state, [section]: visible, ...(visible ? { mode: 'full' as const } : {}) }
    writePreferences(next)
    return { [section]: visible, ...(visible ? { mode: 'full' as const } : {}) }
  }),
}))
