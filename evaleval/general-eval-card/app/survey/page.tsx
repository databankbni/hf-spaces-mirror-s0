"use client"

import { useEffect, useMemo, useState } from "react"
import { ArrowDown, ArrowUp, Copy, Download, RotateCcw, Search, Send, X } from "lucide-react"
import fieldLibraryJson from "@/data/survey/eval-schema-fields.json"
import { Navigation } from "@/components/navigation"
import { PageHeader } from "@/components/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  SURVEY_CONFIG,
  SURVEY_SOURCE_LABELS,
  SURVEY_TOOL_URL,
  type StakeholderTag,
} from "@/lib/survey-content"
import { safeStorage } from "@/lib/safe-storage"
import { cn } from "@/lib/utils"

interface SurveyField {
  id: string
  source: string
  section: string
  field: string
  schemaPath: string
  fullPath: string
  type: string
  description: string
  required: string
}

interface SurveyState {
  participantName: string
  organization: string
  roleTitle: string
  stakeholderTag: StakeholderTag
  stakeholderGroupingNotes: string
  answers: Record<string, string>
  rankedFieldIds: string[]
  fieldRankingNotes: string
  missingFieldNotes: string
  finalNotes: string
}

const FIELD_LIBRARY = fieldLibraryJson as SurveyField[]
const STORAGE_KEY = "eval-cards-survey-v2"
const SOURCE_FILTERS = [
  { id: "all", label: "All fields" },
  { id: "autobenchmarkcard", label: SURVEY_SOURCE_LABELS.autobenchmarkcard },
  { id: "eee_eval", label: SURVEY_SOURCE_LABELS.eee_eval },
  { id: "eee_instance_level_eval", label: SURVEY_SOURCE_LABELS.eee_instance_level_eval },
] as const

function getTodayString() {
  return new Date().toISOString().slice(0, 10)
}

function createInitialState(): SurveyState {
  return {
    participantName: "",
    organization: "",
    roleTitle: "",
    stakeholderTag: "researcher",
    stakeholderGroupingNotes: "",
    answers: {},
    rankedFieldIds: [...SURVEY_CONFIG.defaultFieldIds],
    fieldRankingNotes: "",
    missingFieldNotes: "",
    finalNotes: "",
  }
}

function mergeSurveyState(value: Partial<SurveyState> | undefined): SurveyState {
  const fallback = createInitialState()
  const validFieldIds = new Set(FIELD_LIBRARY.map((field) => field.id))
  const validStakeholderTags = new Set(SURVEY_CONFIG.stakeholderTags.map((tag) => tag.id))

  return {
    ...fallback,
    ...value,
    stakeholderTag: value?.stakeholderTag && validStakeholderTags.has(value.stakeholderTag)
      ? value.stakeholderTag
      : fallback.stakeholderTag,
    answers: {
      ...fallback.answers,
      ...(value?.answers ?? {}),
    },
    rankedFieldIds: Array.isArray(value?.rankedFieldIds)
      ? value.rankedFieldIds.filter((fieldId) => validFieldIds.has(fieldId))
      : fallback.rankedFieldIds,
  }
}

function buildSummaryText(state: SurveyState, fieldMap: Map<string, SurveyField>) {
  const stakeholderLabel =
    SURVEY_CONFIG.stakeholderTags.find((tag) => tag.id === state.stakeholderTag)?.label ??
    state.stakeholderTag

  const lines: string[] = [
    "Evaluation Cards Survey",
    `Stakeholder tag: ${stakeholderLabel}`,
    `Date: ${getTodayString()}`,
    `Participant: ${state.participantName || "Anonymous"}`,
    `Organization: ${state.organization || "Not provided"}`,
    `Role: ${state.roleTitle || "Not provided"}`,
  ]

  if (state.stakeholderGroupingNotes.trim()) {
    lines.push(`Grouping notes: ${state.stakeholderGroupingNotes.trim()}`)
  }

  lines.push("", "Ranked schema fields:")

  if (state.rankedFieldIds.length === 0) {
    lines.push("[No ranked fields yet]")
  } else {
    state.rankedFieldIds.forEach((fieldId, index) => {
      const field = fieldMap.get(fieldId)
      if (!field) return
      lines.push(
        `${index + 1}. ${field.fullPath} (${field.type}; required: ${field.required || "unknown"})`
      )
      lines.push(`   ${field.description}`)
    })
  }

  if (state.fieldRankingNotes.trim()) {
    lines.push("", "Why these fields matter:", state.fieldRankingNotes.trim())
  }

  if (state.missingFieldNotes.trim()) {
    lines.push("", "Fields missing from the schema:", state.missingFieldNotes.trim())
  }

  SURVEY_CONFIG.sections.forEach((section) => {
    lines.push("", section.title)
    section.questions.forEach((question) => {
      lines.push(`- ${question.prompt}`)
      lines.push(`  ${state.answers[question.id]?.trim() || "[No response]"}`)
    })
  })

  if (state.finalNotes.trim()) {
    lines.push("", "Additional notes:", state.finalNotes.trim())
  }

  return lines.join("\n")
}

function slugifySegment(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
}

export default function SurveyPage() {
  const [surveyState, setSurveyState] = useState<SurveyState>(createInitialState)
  const [fieldQuery, setFieldQuery] = useState("")
  const [sourceFilter, setSourceFilter] = useState<(typeof SOURCE_FILTERS)[number]["id"]>("all")
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle")
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "submitted" | "error">("idle")

  useEffect(() => {
    const storedValue = safeStorage().getItem(STORAGE_KEY)
    if (!storedValue) return

    try {
      const parsed = JSON.parse(storedValue) as Partial<SurveyState>
      setSurveyState(mergeSurveyState(parsed))
    } catch (error) {
      console.error("Failed to restore survey state", error)
    }
  }, [])

  useEffect(() => {
    safeStorage().setItem(STORAGE_KEY, JSON.stringify(surveyState))
  }, [surveyState])

  useEffect(() => {
    if (copyState === "idle") return
    const timeout = window.setTimeout(() => setCopyState("idle"), 2000)
    return () => window.clearTimeout(timeout)
  }, [copyState])

  const fieldMap = useMemo(
    () => new Map(FIELD_LIBRARY.map((field) => [field.id, field])),
    []
  )

  const selectedFieldSet = useMemo(
    () => new Set(surveyState.rankedFieldIds),
    [surveyState.rankedFieldIds]
  )

  const suggestedFields = useMemo(
    () =>
      SURVEY_CONFIG.defaultFieldIds
        .map((fieldId) => fieldMap.get(fieldId))
        .filter((field): field is SurveyField => Boolean(field)),
    [fieldMap]
  )

  const filteredAvailableFields = useMemo(() => {
    const query = fieldQuery.trim().toLowerCase()

    return FIELD_LIBRARY.filter((field) => {
      if (selectedFieldSet.has(field.id)) {
        return false
      }

      if (sourceFilter !== "all" && field.source !== sourceFilter) {
        return false
      }

      if (!query) {
        return true
      }

      return [
        field.fullPath,
        field.schemaPath,
        field.description,
        field.type,
        field.required,
        SURVEY_SOURCE_LABELS[field.source] ?? field.source,
      ].some((value) => value.toLowerCase().includes(query))
    }).slice(0, 18)
  }, [fieldQuery, selectedFieldSet, sourceFilter])

  const summaryText = useMemo(
    () => buildSummaryText(surveyState, fieldMap),
    [surveyState, fieldMap]
  )

  const setAnswer = (questionId: string, value: string) => {
    setSurveyState((current) => ({
      ...current,
      answers: {
        ...current.answers,
        [questionId]: value,
      },
    }))
  }

  const addRankedField = (fieldId: string) => {
    setSurveyState((current) => {
      if (current.rankedFieldIds.includes(fieldId)) {
        return current
      }

      return {
        ...current,
        rankedFieldIds: [...current.rankedFieldIds, fieldId],
      }
    })
  }

  const removeRankedField = (fieldId: string) => {
    setSurveyState((current) => ({
      ...current,
      rankedFieldIds: current.rankedFieldIds.filter((id) => id !== fieldId),
    }))
  }

  const moveRankedField = (fieldId: string, direction: -1 | 1) => {
    setSurveyState((current) => {
      const index = current.rankedFieldIds.indexOf(fieldId)
      const nextIndex = index + direction

      if (index === -1 || nextIndex < 0 || nextIndex >= current.rankedFieldIds.length) {
        return current
      }

      const reordered = [...current.rankedFieldIds]
      const [field] = reordered.splice(index, 1)
      reordered.splice(nextIndex, 0, field)

      return {
        ...current,
        rankedFieldIds: reordered,
      }
    })
  }

  const resetSurvey = () => {
    setSurveyState(createInitialState())
    setFieldQuery("")
    setCopyState("idle")
  }

  const copySummary = async () => {
    try {
      await navigator.clipboard.writeText(summaryText)
      setCopyState("copied")
    } catch (error) {
      console.error("Failed to copy survey summary", error)
      setCopyState("error")
    }
  }

  const downloadSummary = () => {
    const participantSlug = slugifySegment(surveyState.participantName) || "participant"
    const dateSlug = getTodayString()
    const filename = `eval-cards-survey-${participantSlug}-${dateSlug}.md`
    const blob = new Blob([summaryText], { type: "text/markdown;charset=utf-8" })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  }

  const submitSurvey = async () => {
    setSubmitState("submitting")
    try {
      const res = await fetch("/api/survey-submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...surveyState,
          submittedAt: new Date().toISOString(),
          date: getTodayString(),
          summaryText,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        console.error("Survey submission failed:", data)
        setSubmitState("error")
        alert("Survey submission failed. Please try again.")
        return
      }
      setSubmitState("submitted")
      alert("Thank you! Your survey response has been submitted successfully.")
    } catch (err) {
      console.error("Survey submission error:", err)
      setSubmitState("error")
      alert("Survey submission failed due to a network error. Please try again.")
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <Navigation />
      <PageHeader
        eyebrow="Survey"
        title={SURVEY_CONFIG.title}
        description="Tell us what is confusing, missing, or hard to compare. This page collects concrete feedback you can write into the form below."
        metaItems={[
          { label: "Schema fields", value: FIELD_LIBRARY.length.toString() },
          { label: "Ranked now", value: surveyState.rankedFieldIds.length.toString() },
          {
            label: "Stakeholder tag",
            value:
              SURVEY_CONFIG.stakeholderTags.find((tag) => tag.id === surveyState.stakeholderTag)?.label ??
              surveyState.stakeholderTag,
          },
        ]}
      />

      <main className="container mx-auto px-4 py-8 pb-24">
        <section className="mb-8 space-y-4">
          <div className="rounded-[1.5rem] border border-border/70 bg-muted/10 p-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Before You Start
            </div>
            <div className="space-y-3 text-sm leading-6 text-muted-foreground">
              <p>{SURVEY_CONFIG.audienceSummary}</p>
              <p>{SURVEY_CONFIG.goalsSummary}</p>
              <p>
                Use the stakeholder tag only as a grouping aid for later analysis. The useful part is your concrete feedback, not the label.
              </p>
            </div>
          </div>

          <div className="rounded-[1.5rem] border border-sky-200/70 bg-sky-50/80 p-5 text-sky-950 dark:border-sky-900/60 dark:bg-sky-950/20 dark:text-sky-100">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-700 dark:text-sky-300">
              What We Want From You
            </div>
            <p className="text-sm leading-6">{SURVEY_CONFIG.usabilityPrompt}</p>
            <p className="mt-3 text-sm leading-6 text-sky-800/85 dark:text-sky-200/85">
              Please explore{" "}
              <a
                href={SURVEY_TOOL_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium underline decoration-sky-400/70 underline-offset-4"
              >
                the current prototype
              </a>{" "}
              and then write your notes below, one section at a time.
            </p>
          </div>
        </section>

        <section className="mb-6 space-y-6">
          <div className="rounded-[1.5rem] border border-border/70 bg-background p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge variant="outline">Public survey</Badge>
              <Badge variant="secondary">Group later</Badge>
            </div>
            <h2 className="text-xl font-bold tracking-tight">{SURVEY_CONFIG.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Fill this in like an interview worksheet: answer the core questions, rank the fields that matter, and leave direct notes on what should change.
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-border/70 bg-muted/10 p-5">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              About You
            </div>
            <p className="mb-4 text-sm text-muted-foreground">
              All fields are optional. Responses are saved anonymously if left blank.
            </p>
            <div className="grid gap-4">
              <label className="block">
                <span className="mb-2 block text-sm"><span className="font-medium">Name</span> <span className="text-muted-foreground">(optional)</span></span>
                <Input
                  value={surveyState.participantName}
                  onChange={(event) =>
                    setSurveyState((current) => ({
                      ...current,
                      participantName: event.target.value,
                    }))
                  }
                  placeholder="Anonymous"
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm"><span className="font-medium">Organization</span> <span className="text-muted-foreground">(optional)</span></span>
                <Input
                  value={surveyState.organization}
                  onChange={(event) =>
                    setSurveyState((current) => ({
                      ...current,
                      organization: event.target.value,
                    }))
                  }
                  placeholder="Org or team"
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm"><span className="font-medium">Role</span> <span className="text-muted-foreground">(optional)</span></span>
                <Input
                  value={surveyState.roleTitle}
                  onChange={(event) =>
                    setSurveyState((current) => ({
                      ...current,
                      roleTitle: event.target.value,
                    }))
                  }
                  placeholder="Role title"
                />
              </label>
            </div>
          </div>
        </section>

        <section className="mb-8 rounded-[1.5rem] border border-border/70 bg-background p-5">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Grouping Tag
              </div>
              <h3 className="mt-1 text-xl font-bold tracking-tight">Tag for later analysis</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Pick the closest fit for grouping purposes.
              </p>
            </div>
            <Badge variant="outline">Optional segmentation layer</Badge>
          </div>

          <div className="flex flex-wrap gap-2">
            {SURVEY_CONFIG.stakeholderTags.map((tag) => (
              <button
                key={tag.id}
                type="button"
                onClick={() =>
                  setSurveyState((current) => ({
                    ...current,
                    stakeholderTag: tag.id,
                  }))
                }
                className={cn(
                  "rounded-full border px-3 py-1.5 text-sm transition-colors",
                  surveyState.stakeholderTag === tag.id
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border/70 bg-background hover:border-primary/50 hover:text-foreground"
                )}
              >
                {tag.label}
              </button>
            ))}
          </div>

          <label className="mt-4 block space-y-2">
            <span className="text-sm font-medium">Grouping notes</span>
            <Textarea
              rows={2}
              value={surveyState.stakeholderGroupingNotes}
              onChange={(event) =>
                setSurveyState((current) => ({
                  ...current,
                  stakeholderGroupingNotes: event.target.value,
                }))
              }
              placeholder="Capture nuance like mixed responsibilities, public-interest role, or why the tag was chosen."
            />
          </label>
        </section>

        <section className="space-y-6">
          {SURVEY_CONFIG.sections.map((section, sectionIndex) => (
            <div
              key={section.id}
              className="rounded-[1.5rem] border border-border/70 bg-background p-5"
            >
              <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                    Section {sectionIndex + 1}
                  </div>
                  <h3 className="mt-1 text-xl font-bold tracking-tight">{section.title}</h3>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                    {section.description}
                  </p>
                </div>
                <Badge variant="outline">{section.questions.length} prompts</Badge>
              </div>

              <div className="grid gap-4">
                {section.questions.map((question, questionIndex) => (
                  <label
                    key={question.id}
                    className="rounded-[1.25rem] border border-border/70 bg-muted/10 p-4"
                  >
                    <div className="mb-2 flex items-start gap-3">
                      <span className="mt-0.5 inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-primary/10 px-2 text-xs font-semibold text-primary">
                        {questionIndex + 1}
                      </span>
                      <span className="text-sm font-medium leading-6">{question.prompt}</span>
                    </div>
                    <Textarea
                      rows={3}
                      value={surveyState.answers[question.id] ?? ""}
                      onChange={(event) => setAnswer(question.id, event.target.value)}
                      placeholder={question.placeholder ?? "Short answer"}
                    />
                  </label>
                ))}
              </div>
            </div>
          ))}
        </section>

        <section className="mt-6 grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[1.5rem] border border-border/70 bg-background p-5">
            <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                  Relative Ranking
                </div>
                <h3 className="mt-1 text-xl font-bold tracking-tight">
                  Most useful schema fields
                </h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Ask which fields matter most to the participant, then rank them from most useful to least useful within the shortlist.
                </p>
              </div>
              <Badge variant="outline">{surveyState.rankedFieldIds.length} ranked</Badge>
            </div>

            {surveyState.rankedFieldIds.length === 0 ? (
              <div className="rounded-[1.25rem] border border-dashed border-border/80 bg-muted/10 px-4 py-6 text-sm text-muted-foreground">
                No fields ranked yet. Add fields from the library or start with one of the suggested fields below.
              </div>
            ) : (
              <div className="space-y-3">
                {surveyState.rankedFieldIds.map((fieldId, index) => {
                  const field = fieldMap.get(fieldId)
                  if (!field) return null

                  return (
                    <div
                      key={field.id}
                      className="rounded-[1.25rem] border border-border/70 bg-muted/10 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <span className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                              {index + 1}
                            </span>
                            <Badge variant="outline">
                              {SURVEY_SOURCE_LABELS[field.source] ?? field.source}
                            </Badge>
                            <Badge variant="secondary">{field.required || "optional"}</Badge>
                          </div>
                          <div className="break-words font-semibold">{field.schemaPath}</div>
                          <div className="mt-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                            {field.type}
                          </div>
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            {field.description}
                          </p>
                        </div>

                        <div className="flex shrink-0 items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => moveRankedField(field.id, -1)}
                            disabled={index === 0}
                            aria-label={`Move ${field.schemaPath} up`}
                          >
                            <ArrowUp className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => moveRankedField(field.id, 1)}
                            disabled={index === surveyState.rankedFieldIds.length - 1}
                            aria-label={`Move ${field.schemaPath} down`}
                          >
                            <ArrowDown className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => removeRankedField(field.id)}
                            aria-label={`Remove ${field.schemaPath}`}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            <div className="mt-5 space-y-4">
              <label className="space-y-2">
                <span className="text-sm font-medium">
                  Why are these fields the most useful?
                </span>
                <Textarea
                  rows={3}
                  value={surveyState.fieldRankingNotes}
                  onChange={(event) =>
                    setSurveyState((current) => ({
                      ...current,
                      fieldRankingNotes: event.target.value,
                    }))
                  }
                  placeholder="Capture the rationale behind the ranking."
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium">
                  Are there missing fields you wish existed?
                </span>
                <Textarea
                  rows={3}
                  value={surveyState.missingFieldNotes}
                  onChange={(event) =>
                    setSurveyState((current) => ({
                      ...current,
                      missingFieldNotes: event.target.value,
                    }))
                  }
                  placeholder="List missing or under-specified fields."
                />
              </label>
            </div>
          </div>

          <div className="rounded-[1.5rem] border border-border/70 bg-muted/10 p-5">
            <div className="mb-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
                Field Library
              </div>
              <h3 className="mt-1 text-xl font-bold tracking-tight">Search and add fields</h3>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Start from the suggested fields below or search the full CSV-derived schema library.
              </p>
            </div>

            <div className="mb-4 flex flex-wrap gap-2">
              {suggestedFields.map((field) => (
                <button
                  key={field.id}
                  type="button"
                  onClick={() => addRankedField(field.id)}
                  disabled={selectedFieldSet.has(field.id)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-sm transition-colors",
                    selectedFieldSet.has(field.id)
                      ? "cursor-not-allowed border-border/60 bg-background text-muted-foreground"
                      : "border-border/70 bg-background hover:border-primary/50 hover:text-foreground"
                  )}
                >
                  {field.schemaPath}
                </button>
              ))}
            </div>

            <div className="space-y-4">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={fieldQuery}
                  onChange={(event) => setFieldQuery(event.target.value)}
                  placeholder="Search by field name, description, or schema path"
                  className="pl-9"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                {SOURCE_FILTERS.map((filter) => (
                  <button
                    key={filter.id}
                    type="button"
                    onClick={() => setSourceFilter(filter.id)}
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-sm transition-colors",
                      sourceFilter === filter.id
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border/70 bg-background hover:border-primary/50 hover:text-foreground"
                    )}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>

              <div className="space-y-3">
                {filteredAvailableFields.map((field) => (
                  <div
                    key={field.id}
                    className="rounded-[1.25rem] border border-border/70 bg-background p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <Badge variant="outline">
                            {SURVEY_SOURCE_LABELS[field.source] ?? field.source}
                          </Badge>
                          <Badge variant="secondary">{field.required || "optional"}</Badge>
                        </div>
                        <div className="break-words font-semibold">{field.schemaPath}</div>
                        <div className="mt-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                          {field.type}
                        </div>
                        <p className="mt-2 text-sm leading-6 text-muted-foreground">
                          {field.description}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => addRankedField(field.id)}
                        className="shrink-0"
                      >
                        Add
                      </Button>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-sm text-muted-foreground">
                Showing up to 18 unranked matches at a time.
              </p>
            </div>
          </div>
        </section>

        <section className="mt-6 rounded-[1.5rem] border border-border/70 bg-background p-5">
          <div className="mb-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Additional Notes
          </div>
          <label className="space-y-2">
            <span className="text-sm font-medium">
              Anything else you want us to know about model evaluations and how they relate to this role?
            </span>
            <Textarea
              rows={4}
              value={surveyState.finalNotes}
              onChange={(event) =>
                setSurveyState((current) => ({
                  ...current,
                  finalNotes: event.target.value,
                }))
              }
              placeholder="Capture anything outside the structured prompts."
            />
          </label>
        </section>
      </main>

      {/* Floating action bar */}
      <div className="fixed bottom-0 inset-x-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="container mx-auto flex items-center justify-end gap-3 px-4 py-3">
          <Button variant="ghost" size="sm" className="gap-2" onClick={resetSurvey}>
            <RotateCcw className="h-4 w-4" />
            Reset
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={downloadSummary}>
            <Download className="h-4 w-4" />
            Download
          </Button>
          <Button variant="outline" size="sm" className="gap-2" onClick={copySummary}>
            <Copy className="h-4 w-4" />
            {copyState === "copied"
              ? "Copied"
              : copyState === "error"
                ? "Copy failed"
                : "Copy to clipboard"}
          </Button>
          <Button
            size="sm"
            className="gap-2"
            onClick={submitSurvey}
            disabled={submitState === "submitting" || submitState === "submitted"}
          >
            <Send className="h-4 w-4" />
            {submitState === "submitting"
              ? "Submitting..."
              : submitState === "submitted"
                ? "Submitted"
                : submitState === "error"
                  ? "Retry Submit"
                  : "Submit"}
          </Button>
        </div>
      </div>
    </div>
  )
}
