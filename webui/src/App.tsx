import { useState } from 'react'
import { Toaster } from 'sonner'
import { Search, Terminal, UserCog } from 'lucide-react'
import { Sidebar } from '@/components/layout/Sidebar'
import { MainContent } from '@/components/layout/MainContent'
import { AuthorFooter } from '@/components/layout/AuthorFooter'
import { CrawlerConfigPanel } from '@/components/config/CrawlerConfigPanel'
import { EnvironmentCheck, isEnvChecked } from '@/components/env/EnvironmentCheck'
import { LicenseDisclaimer, isLicenseAccepted } from '@/components/license/LicenseDisclaimer'
import { SearchPage } from '@/components/search/SearchPage'
import { AccountsPage } from '@/components/accounts/AccountsPage'

type ViewMode = 'search' | 'console' | 'accounts'

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
    <div className="flex flex-col h-screen cyber-grid overflow-hidden relative">
      {/* License Disclaimer Modal - Shows first or when triggered */}
      {(!licenseAccepted || showDisclaimer) && (
        <LicenseDisclaimer onAccept={handleLicenseAccept} />
      )}

      {/* Environment Check Modal - Shows after license accepted */}
      {licenseAccepted && !showDisclaimer && !envChecked && (
        <EnvironmentCheck onCheckComplete={handleEnvCheckComplete} />
      )}

      {/* Header Bar */}
      <Sidebar onShowDisclaimer={handleShowDisclaimer} />

      {/* View Mode Toggle */}
      {licenseAccepted && !showDisclaimer && envChecked && (
        <div className="flex justify-center gap-2 py-2 flex-shrink-0 border-b border-cyber-border-subtle">
          <button
            onClick={() => setViewMode('search')}
            className={`flex items-center gap-1.5 px-4 py-1 rounded-lg text-xs font-mono transition-all ${
              viewMode === 'search'
                ? 'bg-cyber-neon-cyan/10 text-cyber-neon-cyan border border-cyber-neon-cyan/50'
                : 'text-cyber-text-muted hover:text-cyber-text-primary'
            }`}
          >
            <Search className="w-3.5 h-3.5" />
            聚合搜索
          </button>
          <button
            onClick={() => setViewMode('console')}
            className={`flex items-center gap-1.5 px-4 py-1 rounded-lg text-xs font-mono transition-all ${
              viewMode === 'console'
                ? 'bg-cyber-neon-cyan/10 text-cyber-neon-cyan border border-cyber-neon-cyan/50'
                : 'text-cyber-text-muted hover:text-cyber-text-primary'
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            爬虫控制台
          </button>
          <button
            onClick={() => setViewMode('accounts')}
            className={`flex items-center gap-1.5 px-4 py-1 rounded-lg text-xs font-mono transition-all ${
              viewMode === 'accounts'
                ? 'bg-cyber-neon-cyan/10 text-cyber-neon-cyan border border-cyber-neon-cyan/50'
                : 'text-cyber-text-muted hover:text-cyber-text-primary'
            }`}
          >
            <UserCog className="w-3.5 h-3.5" />
            账号设置
          </button>
        </div>
      )}

      {/* Main Area */}
      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        {viewMode === 'search' ? (
          <SearchPage onNavigateConsole={() => setViewMode('console')} onNavigateAccounts={() => setViewMode('accounts')} />
        ) : viewMode === 'accounts' ? (
          <AccountsPage onNavigateSearch={() => setViewMode('search')} />
        ) : (
          <>
            {/* Config Panel - Primary Action Area (Always Expanded) */}
            <div className="flex-shrink-0 p-4 pb-2">
              <CrawlerConfigPanel />
            </div>

            {/* Console - Collapsible Terminal */}
            <div className="flex-1 px-4 pb-4 overflow-hidden">
              <MainContent />
            </div>
          </>
        )}
      </div>

      {/* Author Footer */}
      <AuthorFooter />

      {/* Toast notifications - Theme-aware style */}
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'glass-panel font-mono text-cyber-text-primary',
          style: {
            fontFamily: 'JetBrains Mono, monospace',
          },
        }}
      />
    </div>
  )
}

export default App
