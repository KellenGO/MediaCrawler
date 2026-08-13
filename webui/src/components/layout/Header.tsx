import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Search, UserCog, Terminal, HelpCircle, Wifi, WifiOff, ChevronRight } from 'lucide-react'
import { ThemeToggle } from './ThemeToggle'
import { LanguageSwitch } from './LanguageSwitch'
import { useAccounts } from '@/hooks/useAccounts'
import type { AccountStatusInfo, LoginBadge } from '@/lib/accounts'
import {
  accountSummaryLabel,
  accountTone,
  consumeUnverifiedWarning,
  loginBadgeFrom,
  loginExpiryEvents,
  loginExpiryToastKey,
  markLoginExpiryNotified,
  summarizeAccounts,
  unverifiedWarningCount,
  wasLoginExpiryNotified,
  type AccountTone,
} from '@/lib/accounts'
import { PLATFORM_LABELS, PLATFORM_COLORS } from '@/types/search'

export type ViewMode = 'search' | 'console' | 'accounts'

interface HeaderProps {
  viewMode: ViewMode
  onNavigate: (mode: ViewMode) => void
  onShowDisclaimer: () => void
}

/** 平台字母标记（效果稿：红 / 抖 / 哔 / 知）。 */
const PLATFORM_LETTERS: Record<string, string> = {
  xhs: '红',
  douyin: '抖',
  bilibili: '哔',
  zhihu: '知',
}

const PLATFORM_ORDER = ['xhs', 'douyin', 'bilibili', 'zhihu'] as const

/** 轻量本地 API 健康探测（每 15s 一次）。 */
function useApiHealth(): boolean | null {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    let alive = true
    const check = () => {
      fetch('/api/health')
        .then((r) => r.json())
        .then((d) => alive && setOk(d?.status === 'ok'))
        .catch(() => alive && setOk(false))
    }
    check()
    const id = setInterval(check, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])
  return ok
}

const TONE_DOT: Record<AccountTone, string> = {
  ok: 'bg-[#4f9e79]',
  warn: 'bg-[#d69b50]',
  bad: 'bg-[#c96a6d]',
  idle: 'bg-[#98aaba]',
}

const BADGE_DOT: Record<LoginBadge['kind'], string> = {
  checking: 'bg-[#98aaba]',
  unavailable: 'bg-[#98aaba]',
  summary: 'bg-[#98aaba]',
}

function formatLastVerified(iso: string | null): string | null {
  if (!iso) return null
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return null
    return d.toLocaleString('zh-CN')
  } catch {
    return null
  }
}

function AccountPopover({
  accounts,
  onGoAccounts,
}: {
  accounts: AccountStatusInfo[] | null;
  onGoAccounts: () => void;
}) {
  const { t } = useTranslation()
  const summary = accounts ? summarizeAccounts(accounts) : null

  return (
    <div className="absolute right-0 top-[calc(100%+10px)] w-[280px] rounded-[15px] border border-cyber-border-subtle bg-cyber-bg-secondary shadow-[0_10px_30px_rgba(50,105,145,0.12)] p-4 z-30 animate-dsh-drop">
      <div className="flex items-baseline justify-between mb-1">
        <h3 className="text-[13px] font-semibold text-cyber-text-primary">{t('header.account')}</h3>
        {summary && (
          <span className="text-[11px] text-cyber-text-muted">
            {summary.verified}/{summary.total}
          </span>
        )}
      </div>
      {!accounts && (
        <p className="text-[12px] text-cyber-text-muted py-2">{t('header.accountEmpty')}</p>
      )}
      {accounts && (
        <div>
          {PLATFORM_ORDER.map((p) => {
            const acc = accounts.find((a) => a.platform === p)
            const name = PLATFORM_LABELS[p] || p
            const color = PLATFORM_COLORS[p] || '#4ca4dc'
            const lastVerified = acc ? formatLastVerified(acc.last_verified_at) : null
            if (!acc) {
              return (
                <div key={p} className="flex items-center gap-2.5 py-[7px] text-[12px] text-cyber-text-muted">
                  <span className="w-[18px] h-[18px] rounded-[5px] grid place-items-center text-[10px] font-bold text-white" style={{ backgroundColor: color }}>
                    {PLATFORM_LETTERS[p]}
                  </span>
                  <span>{name}</span>
                  <span className="ml-auto text-[11px]">{t('header.accountEmpty')}</span>
                </div>
              )
            }
            return (
              <div key={p} className="flex items-center gap-2.5 py-[7px] text-[12px] text-cyber-text-secondary">
                <span className="w-[18px] h-[18px] rounded-[5px] grid place-items-center text-[10px] font-bold text-white" style={{ backgroundColor: color }}>
                  {PLATFORM_LETTERS[p]}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span>{name}</span>
                    <span className="ml-auto flex items-center gap-1.5 text-[11px]">
                      <i className={`w-[7px] h-[7px] rounded-full ${TONE_DOT[accountTone(acc)]}`} />
                      {accountSummaryLabel(acc)}
                    </span>
                  </div>
                  {lastVerified && (
                    <div className="text-[10px] text-cyber-text-muted truncate">
                      {t('header.lastVerified')} {lastVerified}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <button
        type="button"
        onClick={onGoAccounts}
        className="mt-2.5 w-full flex items-center justify-center gap-1 rounded-[10px] border border-cyber-border-default bg-transparent px-3 py-2 text-[12px] text-cyber-text-primary hover:border-brand hover:text-brand-strong transition-colors"
      >
        {t('header.goAccounts')}
        <ChevronRight className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

export function Header({ viewMode, onNavigate, onShowDisclaimer }: HeaderProps) {
  const { t } = useTranslation()
  const apiOk = useApiHealth()
  const { accounts, loading, initialLoaded, error } = useAccounts()
  const [accountOpen, setAccountOpen] = useState(false)
  const accountRef = useRef<HTMLDivElement>(null)

  const badge: LoginBadge = loginBadgeFrom(accounts, { loading, initialLoaded, error })
  const badgeDot =
    badge.kind === 'summary'
      ? badge.tone === 'ok'
        ? 'bg-[#4fa179]'
        : badge.tone === 'warn'
          ? 'bg-[#d69b50]'
          : 'bg-[#98aaba]'
      : BADGE_DOT[badge.kind]
  const badgeText =
    badge.kind === 'checking'
      ? t('header.accountChecking')
      : badge.kind === 'unavailable'
        ? t('header.accountUnavailable')
        : `${badge.verified}/${badge.total}`

  // ── Round 14.2 提醒（登录失效 / 未登录平台）──────────────────────────
  // 去重存储是模块级（lib/accounts）：轮询与 React StrictMode 双挂载都
  // 不会重复提醒。
  const prevAccountsRef = useRef<AccountStatusInfo[] | null>(null)

  useEffect(() => {
    const prev = prevAccountsRef.current
    prevAccountsRef.current = accounts
    if (!accounts) return

    // 1) 由已验证降为 expired/login_required → 每个降级事件只提醒一次
    //    （模块级去重集合：轮询与 StrictMode 双挂载都不会重复）。
    const events = loginExpiryEvents(prev, accounts)
    for (const ev of events) {
      const key = loginExpiryToastKey(ev.platform, ev.lastVerifiedAt)
      if (wasLoginExpiryNotified(key)) continue
      markLoginExpiryNotified(key)
      toast(t('header.loginExpiredToast', { label: ev.label }), {
        action: {
          label: t('header.goAccounts'),
          onClick: () => onNavigate('accounts'),
        },
      })
    }

    // 2) 首次加载完成且存在未登录平台 → 一次性低干扰提醒
    if (initialLoaded && prev === null) {
      const n = unverifiedWarningCount(accounts)
      if (n > 0 && consumeUnverifiedWarning()) {
        toast(t('header.unverifiedWarningToast', { count: n }))
      }
    }
  }, [accounts, initialLoaded, onNavigate, t])

  // 点击外部关闭账号浮层
  useEffect(() => {
    if (!accountOpen) return
    const onClick = (e: MouseEvent) => {
      if (accountRef.current && !accountRef.current.contains(e.target as Node)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [accountOpen])

  const navItems: { key: ViewMode; label: string; icon: typeof Search }[] = [
    { key: 'search', label: t('nav.search'), icon: Search },
    { key: 'accounts', label: t('nav.accounts'), icon: UserCog },
    { key: 'console', label: t('nav.console'), icon: Terminal },
  ]

  return (
    <header className="sticky top-0 z-20 border-b border-cyber-border-subtle bg-cyber-bg-primary/85 backdrop-blur-md">
      <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6 h-[64px] flex items-center gap-6 flex-wrap">
        {/* 品牌 */}
        <div className="flex items-center gap-2.5 min-w-max select-none">
          <span className="w-[34px] h-[34px] rounded-[11px] rounded-bl-[4px] bg-brand text-white grid place-items-center text-[16px] font-bold shadow-[inset_0_0_0_1px_rgba(255,255,255,0.18)]">
            四
          </span>
          <strong className="text-[19px] font-bold tracking-[0.08em] text-cyber-text-primary">{t('brand.name')}</strong>
        </div>

        {/* 导航 */}
        <nav className="flex items-center gap-1">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => onNavigate(key)}
              className={`flex items-center gap-1.5 rounded-[9px] px-3.5 py-2 text-[13.5px] transition-colors ${
                viewMode === key
                  ? 'bg-brand-soft text-brand-strong font-semibold'
                  : 'text-cyber-text-secondary hover:text-cyber-text-primary'
              }`}
            >
              <Icon className="w-[15px] h-[15px]" />
              {label}
            </button>
          ))}
        </nav>

        {/* 右侧：本地服务 / 登录状态 / 主题 / 语言 / 帮助 */}
        <div className="ml-auto flex items-center gap-2.5">
          <span className={`hidden lg:flex items-center gap-2 text-[12.5px] ${apiOk === false ? 'text-warn' : 'text-cyber-text-secondary'}`}>
            {apiOk === false ? (
              <WifiOff className="w-3.5 h-3.5" />
            ) : (
              <Wifi className="w-3.5 h-3.5" />
            )}
            {apiOk === false ? t('header.localDown') : t('header.localOk')}
            <i className={`w-2 h-2 rounded-full ${apiOk === false ? 'bg-warn' : 'bg-[#50a67e]'}`} />
          </span>

          <div className="relative" ref={accountRef}>
            <button
              type="button"
              onClick={() => setAccountOpen((v) => !v)}
              title={badge.kind === 'summary' && badge.stale ? t('header.staleHint') : undefined}
              className={`h-[38px] flex items-center gap-2 rounded-[11px] border px-3 text-[12.5px] transition-colors ${
                accountOpen
                  ? 'border-brand bg-brand-soft text-brand-strong'
                  : 'border-cyber-border-subtle bg-cyber-bg-secondary text-cyber-text-secondary hover:border-brand/50'
              } ${badge.kind === 'summary' && badge.stale ? 'opacity-70' : ''}`}
            >
              <i className={`w-2 h-2 rounded-full ${badgeDot}`} />
              <span>{t('header.account')}</span>
              <span className="font-semibold">{badgeText}</span>
            </button>
            {accountOpen && (
              <AccountPopover
                accounts={accounts}
                onGoAccounts={() => { setAccountOpen(false); onNavigate('accounts'); }}
              />
            )}
          </div>

          <ThemeToggle />
          <LanguageSwitch />

          <button
            type="button"
            onClick={onShowDisclaimer}
            title={t('header.helpTitle')}
            className="w-[38px] h-[38px] grid place-items-center rounded-[11px] border border-cyber-border-subtle bg-cyber-bg-secondary text-cyber-text-secondary hover:border-brand/50 hover:text-brand-strong transition-colors"
          >
            <HelpCircle className="w-[17px] h-[17px]" />
          </button>
        </div>
      </div>
    </header>
  )
}
