import { Sun, Moon, Monitor } from 'lucide-react'
import { useThemeStore } from '@/store/themeStore'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type Theme = 'light' | 'dark' | 'system'

const themes: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'Auto', icon: Monitor },
]

export function ThemeToggle() {
  const { theme, setTheme } = useThemeStore()

  const currentTheme = themes.find(t => t.value === theme) || themes[0]
  const Icon = currentTheme.icon

  return (
    <Select value={theme} onValueChange={(value: Theme) => setTheme(value)}>
      <SelectTrigger className="w-[76px] h-[38px] text-xs border-cyber-border-subtle bg-cyber-bg-secondary hover:border-brand/50 transition-colors">
        <Icon className="w-3.5 h-3.5 mr-1 text-cyber-text-secondary" />
        <SelectValue>{currentTheme.label}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {themes.map(({ value, label, icon: ItemIcon }) => (
          <SelectItem key={value} value={value} className="text-xs">
            <div className="flex items-center gap-2">
              <ItemIcon className="w-3.5 h-3.5" />
              {label}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
