import type React from "react"
import type { Metadata } from "next"
import "./globals.css"
import { AudienceModeProvider } from "@/components/audience-mode-provider"
import { BackendRefreshListener } from "@/components/backend-refresh-listener"
import { OrgMetadataProvider } from "@/components/org-metadata-provider"
import { QuickStartProvider } from "@/components/quick-start"
import { SiteFooter } from "@/components/site-footer"
import { ThemeProvider } from "@/components/theme-provider"
import { getOrganizationsData } from "@/lib/data-backend"

const SITE_URL = "https://evalcards.evalevalai.com"
const SITE_NAME = "Evaluation Cards"
const SITE_TITLE = "Evaluation Cards — a reporting layer for AI evaluations"
const SITE_DESCRIPTION =
  "A public collection of reported model–benchmark results, organized under a five-level rollout hierarchy and four interpretive signals: reproducibility, completeness, provenance, and comparability."

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: "%s · Evaluation Cards",
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: [
    "AI evaluation",
    "benchmark",
    "model card",
    "reproducibility",
    "EvalEval",
    "Hugging Face",
    "LLM benchmarks",
    "evaluation cards",
  ],
  authors: [{ name: "EvalEval Coalition", url: "https://evalevalai.com" }],
  creator: "EvalEval Coalition",
  publisher: "EvalEval Coalition",
  icons: {
    icon: "https://evalevalai.com/assets/img/logo-square.png",
    shortcut: "https://evalevalai.com/assets/img/logo-square.png",
    apple: "https://evalevalai.com/assets/img/logo-square.png",
  },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    creator: "@huggingface",
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  // Per-org registry metadata (homepage url, logo, stable canonical id) for the
  // whole app. Small + cached; degrades to {} when the snapshot lacks the
  // organizations sidecar. Drives rename-stable evaluator URLs (slug = id).
  const orgMetadata = await getOrganizationsData().catch(() => ({}))
  return (
    <html lang="en" className="antialiased" suppressHydrationWarning>
      <body className="font-sans">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <AudienceModeProvider>
            <OrgMetadataProvider value={orgMetadata}>
              <QuickStartProvider>
                <BackendRefreshListener />
                {children}
                <SiteFooter />
              </QuickStartProvider>
            </OrgMetadataProvider>
          </AudienceModeProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
