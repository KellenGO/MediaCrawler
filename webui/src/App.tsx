import { Suspense, lazy, useState } from 'react'
import { Toaster } from 'sonner'
import { Header, type ViewMode } from '@/components/layout/Header'
import { AuthorFooter } from '@/components/layout/AuthorFooter'
import { EnvironmentCheck, isEnvChecked } from '@/components/env/EnvironmentCheck'
import { LicenseDisclaimer, isLicenseAccepted } from '@/components/license/LicenseDisclaimer'
import { SearchPage } from '@/components/search/SearchPage'

// Phase 5.2: 非搜索页按需加载（页面级 lazy，不手工拆 manualChunks）。
// 搜索主页面保持同步加载，首屏不引入账号页/控制台 chunk。
const AccountsPage = lazy(() =>
  import('@/components/accounts/AccountsPage').then((m) => ({ default: m.AccountsPage }))
)
const ConsoleView = lazy(() => import('@/components/console/ConsoleView'))

/** 浅蓝色 Suspense 占位（不闪屏）。 */
function PageLoading() {
  return (
    <div className="pt-16 flex justify-center">
      <div className="inline-block animate-dsh-spin rounded-full h-8 w-8 border-2 border-sky-300 border-t-transparent" />
    </div>
  )
}

function App() {
  // Initialize by checking localStorage if license has been accepted
  const [licenseAccepted, setLicenseAccepted] = useState(() => isLicenseAccepted())
  // Initialize by checking localStorage if env check has passed
  const [envChecked, setEnvChecked] = useState(() => isEnvChecked())
  // State for showing disclaimer manually
  const [showDisclaimer, setShowDisclaimer] = useState(false)
  // View mode toggle
  const [viewMode, setViewMode] = useState<ViewMode>('search')

  const handleEnvCheckComplete = () => {
    setEnvChecked(true)
  }

  const handleLicenseAccept = () => {
    setLicenseAccepted(true)
    setShowDisclaimer(false)
  }

  const handleShowDisclaimer = () => {
    setShowDisclaimer(true)
  }

  return (
    <div className="min-h-screen flex flex-col relative">
      {/* License Disclaimer Modal - Shows first or when triggered */}
      {(!licenseAccepted || showDisclaimer) && (
        <LicenseDisclaimer onAccept={handleLicenseAccept} />
      )}

      {/* Environment Check Modal - Shows after license accepted */}
      {licenseAccepted && !showDisclaimer && !envChecked && (
        <EnvironmentCheck onCheckComplete={handleEnvCheckComplete} />
      )}

      {/* 顶部栏：品牌 / 导航 / 本地服务 / 账号状态 / 主题 / 语言 / 帮助 */}
      {licenseAccepted && !showDisclaimer && envChecked && (
        <Header viewMode={viewMode} onNavigate={setViewMode} onShowDisclaimer={handleShowDisclaimer} />
      )}

      {/* Main Area */}
      <main className="flex-1 w-full">
        {licenseAccepted && !showDisclaimer && envChecked && (
          <div className="mx-auto w-full max-w-[1200px] px-4 sm:px-6">
            <Suspense fallback={<PageLoading />}>
              {viewMode === 'search' ? (
                <SearchPage onNavigateConsole={() => setViewMode('console')} onNavigateAccounts={() => setViewMode('accounts')} />
              ) : viewMode === 'accounts' ? (
                <AccountsPage onNavigateSearch={() => setViewMode('search')} />
              ) : (
                <ConsoleView />
              )}
            </Suspense>
          </div>
        )}
      </main>

      {/* 低调页脚：随页面内容滚动，不遮挡结果 */}
      {licenseAccepted && !showDisclaimer && envChecked && (
        <AuthorFooter onShowDisclaimer={handleShowDisclaimer} />
      )}

      {/* Toast notifications - Theme-aware style */}
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'glass-panel text-cyber-text-primary',
          style: {
            borderRadius: '12px',
          },
        }}
      />
    </div>
  )
}

export default App
