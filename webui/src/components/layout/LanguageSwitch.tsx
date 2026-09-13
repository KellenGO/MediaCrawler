import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const languages = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en-US', label: 'EN' },
]

export function LanguageSwitch() {
  const { i18n } = useTranslation()

  const currentLang = languages.find(l => l.code === i18n.language) || languages[0]

  return (
    <Select value={i18n.language} onValueChange={(lang) => i18n.changeLanguage(lang)}>
      <SelectTrigger aria-label="切换语言" className="hidden sm:flex w-[52px] h-[36px] justify-center px-0 text-[11px] border-0 bg-transparent text-cyber-text-muted hover:bg-brand-soft hover:text-brand-strong transition-colors">
        <Globe className="w-3.5 h-3.5 mr-1" />
        <SelectValue>{currentLang.label}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {languages.map((lang) => (
          <SelectItem key={lang.code} value={lang.code} className="text-xs">
            {lang.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
