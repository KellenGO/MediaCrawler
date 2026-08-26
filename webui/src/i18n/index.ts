import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// 中文翻译
import zhCommon from './locales/zh-CN/common.json'
import zhLicense from './locales/zh-CN/license.json'

// 英文翻译
import enCommon from './locales/en-US/common.json'
import enLicense from './locales/en-US/license.json'

const resources = {
  'zh-CN': {
    common: zhCommon,
    license: zhLicense,
  },
  'en-US': {
    common: enCommon,
    license: enLicense,
  },
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'zh-CN',
    defaultNS: 'common',
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'mediacrawler_language',
    },
  })

export default i18n
