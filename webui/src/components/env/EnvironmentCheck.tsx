import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, XCircle, Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { envApi, EnvCheckResult } from '@/lib/api'

const ENV_CHECK_KEY = 'mediacrawler_env_checked'

interface EnvironmentCheckProps {
  onCheckComplete: (success: boolean) => void
}

// 检查是否已经通过环境检测
export function isEnvChecked(): boolean {
  return localStorage.getItem(ENV_CHECK_KEY) === 'true'
}

// 清除环境检测状态
export function clearEnvCheck(): void {
  localStorage.removeItem(ENV_CHECK_KEY)
}

export function EnvironmentCheck({ onCheckComplete }: EnvironmentCheckProps) {
  const { t } = useTranslation('env')
  const [status, setStatus] = useState<'checking' | 'success' | 'error'>('checking')
  const [result, setResult] = useState<EnvCheckResult | null>(null)
  const [showDetails, setShowDetails] = useState(false)

  const checkEnvironment = async () => {
    setStatus('checking')
    setResult(null)
    try {
      const response = await envApi.check()
      setResult(response.data)
      if (response.data.success) {
        setStatus('success')
        // 存储到 localStorage
        localStorage.setItem(ENV_CHECK_KEY, 'true')
        // 成功后延迟关闭
        setTimeout(() => onCheckComplete(true), 1500)
      } else {
        setStatus('error')
      }
    } catch (error) {
      setResult({
        success: false,
        message: t('defaultError'),
        error: t('defaultErrorHint')
      })
      setStatus('error')
    }
  }

  useEffect(() => {
    checkEnvironment()
  }, [])

  const handleSkip = () => {
    localStorage.setItem(ENV_CHECK_KEY, 'true')
    onCheckComplete(false)
  }

  const handleRetry = () => {
    checkEnvironment()
  }

  return (
    <div className="fixed inset-0 bg-[#172b3d]/60 backdrop-blur-sm flex items-center justify-center z-50 px-4">
      <div className="bg-cyber-bg-secondary border border-cyber-border-default rounded-[18px] shadow-[0_24px_70px_rgba(50,105,145,0.16)] p-6 max-w-md w-full">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <span className="w-10 h-10 rounded-[12px] rounded-bl-[4px] bg-brand/15 grid place-items-center">
            <AlertTriangle className="w-5 h-5 text-warn" />
          </span>
          <h2 className="text-lg font-bold text-cyber-text-primary">
            {t('title')}
          </h2>
        </div>

        {/* Status Display */}
        <div className="bg-cyber-bg-tertiary border border-cyber-border-subtle rounded-xl p-4 mb-4">
          <div className="flex items-center gap-3">
            {status === 'checking' && (
              <>
                <Loader2 className="w-5 h-5 text-brand-strong animate-spin" />
                <span className="text-cyber-text-primary text-sm">
                  {t('scanning')}
                </span>
              </>
            )}
            {status === 'success' && (
              <>
                <CheckCircle className="w-5 h-5 text-ok" />
                <span className="text-[#3d7d60] text-sm">
                  {t('success', { message: result?.message })}
                </span>
              </>
            )}
            {status === 'error' && (
              <>
                <XCircle className="w-5 h-5 text-danger" />
                <span className="text-danger text-sm">
                  {t('error', { message: result?.message })}
                </span>
              </>
            )}
          </div>

          {/* Error Details */}
          {status === 'error' && result?.error && (
            <div className="mt-3">
              <button
                onClick={() => setShowDetails(!showDetails)}
                className="text-sm text-brand-strong hover:underline"
              >
                {showDetails ? t('hideDetails') : t('showDetails')}
              </button>
              {showDetails && (
                <pre className="mt-2 p-3 bg-[#0d1117] text-[#7ee2a8] rounded text-xs overflow-x-auto whitespace-pre-wrap border border-cyber-border-subtle">
                  {result.error}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Help Text */}
        {status === 'error' && (
          <div className="text-sm text-cyber-text-secondary mb-4 space-y-2">
            <p className="text-warn font-medium">{t('requirements')}</p>
            <ol className="list-decimal list-inside space-y-1 pl-1 text-cyber-text-muted">
              <li>{t('requirementsList.1')}</li>
              <li>{t('requirementsList.2')}</li>
              <li>{t('requirementsList.3')}</li>
            </ol>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          {status === 'error' && (
            <>
              <Button
                variant="outline"
                className="flex-1"
                onClick={handleSkip}
              >
                {t('skipCheck')}
              </Button>
              <Button
                variant="outline"
                className="flex-1 border-brand/40 text-brand-strong hover:bg-brand-soft hover:border-brand/40"
                onClick={handleRetry}
              >
                <RefreshCw className="w-4 h-4" />
                {t('retryCheck')}
              </Button>
            </>
          )}
          {status === 'checking' && (
            <Button
              variant="outline"
              className="w-full"
              onClick={handleSkip}
            >
              {t('skipCheck')}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
