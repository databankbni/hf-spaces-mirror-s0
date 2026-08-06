"use client"

import { useMemo, useState, type ReactNode } from "react"
import {
  Copy,
  ExternalLink,
  FileSearch,
  Flag,
  GitPullRequestArrow,
  MessageSquare,
} from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

interface FlagScoreButtonProps {
  modelName: string
  modelId: string
  benchmarkName: string
  benchmarkId?: string
  score: number | string
  /** URL to the published source the score was extracted from (paper, blog, leaderboard). */
  sourceUrl?: string
  /** URL to the processed record JSON in the card_backend HF dataset. */
  sourceRecordUrl?: string
  /** Optional explicit upstream record URL in evaleval/EEE_datastore (raw source of truth). */
  eeeRecordUrl?: string
}

interface DatasetLinks {
  repoSlug: string
  recordViewUrl: string | null
  recordRawUrl: string | null
  discussionsUrl: string
  newDiscussionUrl: string
}

/**
 * Given a /resolve/main/... HF dataset URL, derive the helpful sibling URLs
 * for the dataset (file viewer, discussions list, new-discussion form). Returns
 * null when the input doesn't look like a HF dataset URL.
 */
function deriveDatasetLinks(recordUrl: string | undefined, prefilledTitle: string): DatasetLinks | null {
  if (!recordUrl) return null
  const m = recordUrl.match(
    /^https:\/\/huggingface\.co\/datasets\/([^/]+\/[^/]+)\/(?:resolve|raw|blob)\/[^/]+\/(.*)$/,
  )
  if (!m) return null
  const repoSlug = m[1]
  const path = m[2]
  const datasetBase = `https://huggingface.co/datasets/${repoSlug}`
  const recordViewUrl = `${datasetBase}/blob/main/${path}`
  const recordRawUrl = `${datasetBase}/resolve/main/${path}`
  const discussionsUrl = `${datasetBase}/discussions`
  const newDiscussionUrl = `${datasetBase}/discussions/new?title=${encodeURIComponent(prefilledTitle)}`
  return { repoSlug, recordViewUrl, recordRawUrl, discussionsUrl, newDiscussionUrl }
}

/**
 * "Flag this score" — researcher affordance that, instead of capturing the
 * report ourselves, sends the user directly to the upstream HF dataset where
 * the data lives. They can then file a discussion or submit a correction PR
 * against the actual record. We also offer a copyable context snippet so the
 * issue body has all the relevant identifiers without needing to retype them.
 */
export function FlagScoreButton({
  modelName,
  modelId,
  benchmarkName,
  benchmarkId,
  score,
  sourceUrl,
  sourceRecordUrl,
  eeeRecordUrl,
}: FlagScoreButtonProps) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState<"context" | null>(null)

  const prefilledTitle = `Possible issue: ${modelName} on ${benchmarkName} (score ${score})`

  const cardBackendLinks = useMemo(
    () => deriveDatasetLinks(sourceRecordUrl, prefilledTitle),
    [sourceRecordUrl, prefilledTitle],
  )
  const eeeLinks = useMemo(
    () => deriveDatasetLinks(eeeRecordUrl, prefilledTitle),
    [eeeRecordUrl, prefilledTitle],
  )

  // Prefer the EEE upstream as the "correction venue" when known — that's
  // where raw evaluation records live. Fall back to card_backend (the
  // pipeline output) when EEE isn't directly addressable for this row.
  const correctionLinks = eeeLinks ?? cardBackendLinks

  const contextSnippet = [
    `Model: ${modelName} (${modelId})`,
    `Benchmark: ${benchmarkName}${benchmarkId ? ` (${benchmarkId})` : ""}`,
    `Reported score: ${score}`,
    sourceUrl ? `Original source URL: ${sourceUrl}` : null,
    sourceRecordUrl ? `Pipeline record: ${sourceRecordUrl}` : null,
    eeeRecordUrl ? `EEE upstream record: ${eeeRecordUrl}` : null,
  ]
    .filter(Boolean)
    .join("\n")

  const handleCopyContext = async () => {
    try {
      await navigator.clipboard.writeText(contextSnippet)
      setCopied("context")
      setTimeout(() => setCopied(null), 1800)
    } catch {
      // Clipboard might be blocked; ignore — the user can still select text manually.
    }
  }

  return (
    <>
      <button
        type="button"
        className="btn-ec outline inline-flex items-center gap-1.5"
        style={{ fontSize: 11, padding: "4px 10px" }}
        onClick={() => setOpen(true)}
      >
        <Flag className="h-3 w-3" />
        Flag this score
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Flag this score</DialogTitle>
            <DialogDescription>
              Take this report directly to the dataset where the record lives. You can file a
              discussion or open a correction PR against the actual file.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div
              style={{
                padding: "10px 12px",
                border: "1px solid var(--border-soft)",
                background: "var(--bg-warm)",
                fontSize: 12,
              }}
            >
              <div
                className="font-mono uppercase"
                style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--fg-subtle)" }}
              >
                Flagging
              </div>
              <div className="mt-1" style={{ color: "var(--fg)" }}>
                <span className="font-semibold">{modelName}</span>{" "}
                <span style={{ color: "var(--fg-muted)" }}>on</span>{" "}
                <span className="font-semibold">{benchmarkName}</span>
              </div>
              <div
                className="font-mono tabular-nums"
                style={{ color: "var(--fg-muted)", fontSize: 12 }}
              >
                Score: {score}
              </div>
            </div>

            <div className="space-y-2">
              {correctionLinks?.recordViewUrl && (
                <FlagAction
                  href={correctionLinks.recordViewUrl}
                  icon={<FileSearch className="h-4 w-4" style={{ color: "var(--fg-muted)" }} />}
                  title="View the underlying record"
                  detail={
                    <>
                      Opens the JSON file on{" "}
                      <span className="font-mono">{correctionLinks.repoSlug}</span>
                    </>
                  }
                />
              )}

              {correctionLinks && (
                <FlagAction
                  href={correctionLinks.newDiscussionUrl}
                  icon={<MessageSquare className="h-4 w-4" style={{ color: "var(--fg-muted)" }} />}
                  title="Open a discussion"
                  detail="Pre-filled title; paste the context snippet into the body."
                />
              )}

              {correctionLinks && (
                <FlagAction
                  href={correctionLinks.discussionsUrl}
                  icon={<GitPullRequestArrow className="h-4 w-4" style={{ color: "var(--fg-muted)" }} />}
                  title="Browse existing discussions"
                  detail="Check whether someone already filed a similar correction."
                />
              )}

              {!correctionLinks && (
                <div
                  className="text-[12px]"
                  style={{
                    padding: "10px 12px",
                    border: "1px dashed var(--accent)",
                    background: "var(--bg-warm)",
                    color: "var(--accent)",
                    lineHeight: 1.6,
                  }}
                >
                  No upstream record URL is recorded for this row, so we can't link directly to
                  the dataset. Copy the context below and file an issue at{" "}
                  <a
                    className="underline-offset-4 hover:underline"
                    href="https://huggingface.co/datasets/evaleval/EEE_datastore/discussions"
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--accent)" }}
                  >
                    evaleval/EEE_datastore/discussions
                  </a>
                  .
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label
                  className="font-mono uppercase"
                  style={{ fontSize: 10, letterSpacing: "0.14em", color: "var(--fg-subtle)" }}
                >
                  Context to paste into the issue
                </label>
                <button
                  type="button"
                  onClick={handleCopyContext}
                  className="inline-flex items-center gap-1.5 font-mono uppercase underline-offset-4 hover:underline"
                  style={{ fontSize: 10, letterSpacing: "0.12em", color: "var(--accent)" }}
                >
                  <Copy className="h-3 w-3" />
                  {copied === "context" ? "Copied" : "Copy"}
                </button>
              </div>
              <pre
                className="max-h-40 overflow-auto whitespace-pre-wrap break-all"
                style={{
                  padding: 12,
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  lineHeight: 1.5,
                  border: "1px solid var(--border-soft)",
                  background: "var(--bg)",
                  color: "var(--fg-muted)",
                }}
              >
                {contextSnippet}
              </pre>
            </div>

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="font-mono uppercase underline-offset-4 hover:underline"
                style={{ fontSize: 11, letterSpacing: "0.12em", color: "var(--fg-muted)" }}
              >
                Close
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

function FlagAction({
  href,
  icon,
  title,
  detail,
}: {
  href: string
  icon: ReactNode
  title: string
  detail: ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="flex items-center justify-between transition-colors hover:bg-[color:var(--bg-warm)]"
      style={{
        padding: "10px 12px",
        border: "1px solid var(--border-soft)",
        background: "var(--bg)",
        textDecoration: "none",
        color: "var(--fg)",
      }}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="shrink-0">{icon}</span>
        <div className="min-w-0">
          <div className="font-semibold text-[13px]" style={{ color: "var(--fg)" }}>{title}</div>
          <div className="text-[11px]" style={{ color: "var(--fg-muted)", lineHeight: 1.5 }}>
            {detail}
          </div>
        </div>
      </div>
      <ExternalLink className="h-3.5 w-3.5 shrink-0" style={{ color: "var(--fg-muted)" }} />
    </a>
  )
}
