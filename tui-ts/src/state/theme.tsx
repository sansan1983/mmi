import React, { createContext, useContext } from 'react'
import { tokyoNight, type Theme } from '../theme/tokyo-night.js'

const ThemeContext = createContext<Theme>(tokyoNight)

export function ThemeProvider({ theme, children }: { theme: Theme; children: React.ReactNode }) {
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>
}

export function useTheme(): Theme {
  return useContext(ThemeContext)
}
