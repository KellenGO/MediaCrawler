import { useTranslation } from 'react-i18next'
import { ShieldAlert, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'

const LICENSE_KEY = 'mediacrawler_license_accepted'

// 检查是否已经接受协议
export function isLicenseAccepted(): boolean {
  return localStorage.getItem(LICENSE_KEY) === 'true'
}

// 清除协议接受状态
export function clearLicenseAccepted(): void {
  localStorage.removeItem(LICENSE_KEY)
}

interface LicenseDisclaimerProps {
  onAccept: () => void
}

export function LicenseDisclaimer({ onAccept }: LicenseDisclaimerProps) {
  const { t } = useTranslation('license')

  const handleConfirm = () => {
    localStorage.setItem(LICENSE_KEY, 'true')
    onAccept()
  }

  const handleDecline = () => {
    // 尝试关闭当前标签页（不会关闭整个浏览器，只关闭当前tab）
    try {
      // 方式1: 直接关闭当前标签页
      window.close()

      // 方式2: 将当前标签页导航到空白页
      setTimeout(() => {
        window.location.href = 'about:blank'
      }, 100)
    } catch {
      // 忽略错误
    }

    // 如果无法关闭（浏览器安全限制），显示拒绝访问页面
    setTimeout(() => {
      document.body.innerHTML = `
        <div style="
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          background: #0d1117;
          color: #f85149;
          font-family: 'JetBrains Mono', monospace;
          text-align: center;
          padding: 20px;
        ">
          <div style="font-size: 48px; margin-bottom: 20px;">⛔</div>
          <div style="font-size: 24px; font-weight: bold; margin-bottom: 10px;">访问已拒绝</div>
          <div style="font-size: 14px; color: #8b949e;">您未同意使用条款，请关闭此标签页</div>
        </div>
      `
    }, 200)
  }

  return (
    <div className="fixed inset-0 bg-[#172b3d]/60 backdrop-blur-sm flex items-center justify-center z-[100] overflow-y-auto py-8 px-4">
      <div className="bg-cyber-bg-secondary border border-cyber-border-default rounded-[18px] shadow-[0_24px_70px_rgba(50,105,145,0.16)] p-6 sm:p-8 max-w-2xl w-full relative">
        {/* Header */}
        <div className="flex items-center justify-center gap-3 mb-4">
          <span className="w-11 h-11 rounded-[13px] rounded-bl-[5px] bg-brand/15 grid place-items-center">
            <ShieldAlert className="w-6 h-6 text-brand-strong" />
          </span>
          <h2 className="text-xl font-bold text-cyber-text-primary">
            {t('title')}
          </h2>
        </div>

        {/* Warning subtitle */}
        <div className="text-center mb-5">
          <span className="text-[13.5px] text-warn font-medium">
            {t('warning')}
          </span>
        </div>

        {/* Content box */}
        <div className="bg-cyber-bg-tertiary border border-cyber-border-subtle rounded-xl p-4 mb-5">
          <ul className="space-y-2.5 text-[13.5px]">
            <li className="flex items-start gap-2.5">
              <span className="text-brand-strong font-bold flex-shrink-0">1.</span>
              <span className="text-cyber-text-primary">{t('content.line1')}</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-brand-strong font-bold flex-shrink-0">2.</span>
              <span className="text-cyber-text-primary">{t('content.line2')}</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-brand-strong font-bold flex-shrink-0">3.</span>
              <span className="text-cyber-text-primary">{t('content.line3')}</span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-brand-strong font-bold flex-shrink-0">4.</span>
              <span className="text-cyber-text-primary">{t('content.line4')}</span>
            </li>
          </ul>
        </div>

        {/* License Link */}
        <div className="flex justify-center mb-6">
          <a
            href="https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-brand-strong hover:underline text-sm"
          >
            <ExternalLink className="w-4 h-4" />
            {t('license')}
          </a>
        </div>

        {/* Action buttons */}
        <div className="flex gap-3">
          <Button
            onClick={handleDecline}
            variant="outline"
            className="flex-1 border-danger/50 text-danger hover:bg-danger-soft hover:border-danger/50"
          >
            {t('decline')}
          </Button>
          <Button
            onClick={handleConfirm}
            className="flex-1 bg-brand text-white font-bold hover:bg-brand-strong"
          >
            {t('confirm')}
          </Button>
        </div>
      </div>
    </div>
  )
}
