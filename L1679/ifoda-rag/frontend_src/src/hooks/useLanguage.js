import { useTranslation } from 'react-i18next'
import { useCallback } from 'react'

const SUPPORTED = ['ru', 'en', 'uz']
const LABELS = { ru: 'RU', en: 'EN', uz: 'UZ' }

/**
 * Wrapper around useTranslation that also exposes a cycleLanguage() helper
 * to rotate between supported languages (used by the TopBar language chip).
 */
export function useLanguage() {
  const { i18n } = useTranslation()

  const cycleLanguage = useCallback(() => {
    const idx = SUPPORTED.indexOf(i18n.language)
    const next = SUPPORTED[(idx + 1) % SUPPORTED.length]
    i18n.changeLanguage(next)
  }, [i18n])

  const setLanguage = useCallback(
    (lng) => {
      if (SUPPORTED.includes(lng)) i18n.changeLanguage(lng)
    },
    [i18n]
  )

  return {
    language: i18n.language,
    label: LABELS[i18n.language] || i18n.language?.toUpperCase() || 'RU',
    supported: SUPPORTED,
    labels: LABELS,
    cycleLanguage,
    setLanguage,
  }
}