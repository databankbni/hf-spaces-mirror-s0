"use client"

import Link from "next/link"
import { ImageIcon } from "lucide-react"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"

import { cn } from "@/lib/utils"

/**
 * Renders a pre-processed tutorial markdown string (see lib/tutorials.ts) with
 * the site's design tokens. Handles two source-specific concerns:
 *  - relative `*.md` / `../about` links are rewritten to in-app routes;
 *  - `placeholder:<file>` image sources render as styled "screenshot coming"
 *    callouts instead of broken images.
 */
export function TutorialMarkdown({ source }: { source: string }) {
  return (
    <div className="tutorial-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        // Preserve our internal `placeholder:` scheme for missing screenshots;
        // react-markdown would otherwise sanitize the URL away.
        urlTransform={(url) =>
          url.startsWith("placeholder:") ? url : defaultUrlTransform(url)
        }
        components={{
          a: ({ href, children }) => {
            const target = resolveHref(String(href ?? ""))
            if (target.external) {
              return (
                <a href={target.href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              )
            }
            return <Link href={target.href}>{children}</Link>
          },
          img: ({ src, alt }) => {
            const value = String(src ?? "")
            if (value.startsWith("placeholder:")) {
              return <ScreenshotPlaceholder file={value.slice("placeholder:".length)} note={alt} />
            }
            return (
              <figure className="tut-figure">
                <span className="tut-figure-frame block">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={value} alt={alt ?? ""} loading="lazy" />
                </span>
                {alt ? <figcaption>{alt}</figcaption> : null}
              </figure>
            )
          },
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  )
}

function resolveHref(href: string): { href: string; external: boolean } {
  if (/^https?:\/\//.test(href) || href.startsWith("mailto:")) {
    return { href, external: true }
  }
  if (href.startsWith("#")) {
    return { href, external: false }
  }
  // Relative links between guides, e.g. "quickstart.md" → "/help/quickstart".
  if (href.endsWith(".md")) {
    const base = href.replace(/^.*\//, "").replace(/\.md$/, "")
    return { href: `/help/${base}`, external: false }
  }
  // Relative escapes to the app root, e.g. "../about" → "/about".
  if (href.startsWith("../") || href.startsWith("./")) {
    const cleaned = href.replace(/^(\.\.\/|\.\/)+/, "")
    return { href: `/${cleaned}`, external: false }
  }
  return { href, external: false }
}

function ScreenshotPlaceholder({ file, note }: { file: string; note?: string }) {
  return (
    <div
      className={cn(
        "my-6 flex gap-3 border border-dashed border-[color:var(--border-strong)]",
        "bg-[color:var(--bg-subtle)] p-4 text-[color:var(--fg-muted)]"
      )}
    >
      <ImageIcon className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--fg-subtle)]" aria-hidden />
      <div className="min-w-0">
        <div className="kicker mb-1">Screenshot coming</div>
        <code className="font-mono text-[12px] text-[color:var(--fg)]">{file}</code>
        {note ? <p className="m-0 mt-1.5 text-[13px] leading-[1.6]">{note}</p> : null}
      </div>
    </div>
  )
}
