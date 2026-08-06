import { useEffect, useState } from 'react'
import WebApp from '@twa-dev/sdk'

/**
 * Detects if the app is running inside Telegram Mini App and exposes a
 * narrow wrapper around @twa-dev/sdk for theming & lifecycle.
 *
 * Returns:
 *   - isTelegram: boolean — true if WebApp.initData is non-empty
 *   - tg: the SDK object (null on plain web)
 *   - colorScheme: 'dark' | 'light'
 *   - themeParams: object with telegram-provided theme colors
 *   - platform: string ('ios' | 'android' | 'web' | etc.)
 *   - ready(): call once SDK data is consumed
 *   - expand(): expand the Web App viewport
 */
export function useTelegram() {
  const [info, setInfo] = useState(() => {
    const isTelegram =
      typeof window !== 'undefined' &&
      Boolean(WebApp?.initData) &&
      WebApp.initData.length > 0

    if (!isTelegram) {
      return {
        isTelegram: false,
        tg: null,
        colorScheme: 'dark',
        themeParams: {},
        platform: 'web',
      }
    }

    return {
      isTelegram: true,
      tg: WebApp,
      colorScheme: WebApp.colorScheme || 'dark',
      themeParams: WebApp.themeParams || {},
      platform: WebApp.platform || 'unknown',
    }
  })

  useEffect(() => {
    if (!info.isTelegram) return
    try {
      WebApp.ready()
      WebApp.expand()
    } catch {
      /* ignore — SDK may not be present in some environments */
    }
  }, [info.isTelegram])

  return {
    ...info,
    ready: () => info.tg?.ready?.(),
    expand: () => info.tg?.expand?.(),
  }
}