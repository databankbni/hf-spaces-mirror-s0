export type StakeholderTag = "researcher" | "policymaker" | "both" | "other"

export interface SurveyQuestion {
  id: string
  prompt: string
  placeholder?: string
}

export interface SurveySection {
  id: string
  title: string
  description: string
  questions: SurveyQuestion[]
}

export interface SurveyConfig {
  title: string
  audienceSummary: string
  goalsSummary: string
  usabilityPrompt: string
  defaultFieldIds: string[]
  stakeholderTags: Array<{
    id: StakeholderTag
    label: string
  }>
  sections: SurveySection[]
}

export const SURVEY_TOOL_URL = "https://evaleval-general-eval-card.hf.space/"

export const SURVEY_SOURCE_LABELS: Record<string, string> = {
  autobenchmarkcard: "Eval metadata",
  eee_eval: "Aggregate level",
  eee_instance_level_eval: "Instance level",
}

const shortAnswer = "Short answer"

export const SURVEY_CONFIG: SurveyConfig = {
  title: "Shared Stakeholder Survey",
  audienceSummary:
    "A survey for people who work with model evaluations, whether they identify more as eval researchers, policymakers, or span both contexts.",
  goalsSummary:
    "Responses are grouped afterward using the stakeholder tag and role notes. The goal is to capture what people need from evaluations, what makes them trust the evidence, and which schema fields matter most.",
  usabilityPrompt:
    "We're evaluating the interface, not you. Feel free to share as much or as little as you like.",
  stakeholderTags: [
    { id: "researcher", label: "Eval Researcher" },
    { id: "policymaker", label: "Policymaker" },
    { id: "both", label: "Both / mixed role" },
    { id: "other", label: "Other" },
  ],
  defaultFieldIds: [
    "eee_eval:source_metadata.evaluator_relationship",
    "eee_eval:source_metadata.source_organization_name",
    "eee_eval:retrieved_timestamp",
    "eee_eval:eval_library.name",
    "eee_eval:eval_library.version",
    "eee_eval:evaluation_results.generation_config",
    "eee_eval:detailed_evaluation_results.file_path",
    "autobenchmarkcard:benchmark_details.overview",
    "autobenchmarkcard:purpose_and_intended_users.limitations",
    "autobenchmarkcard:methodology.metrics",
    "autobenchmarkcard:methodology.validation",
    "autobenchmarkcard:methodology.interpretation",
    "autobenchmarkcard:ethical_and_legal_considerations.compliance_with_regulations",
    "autobenchmarkcard:possible_risks.category",
  ],
  sections: [
    {
      id: "introduction",
      title: "Introduction",
      description: "Start by describing your role, workflow, and who relies on your evaluation work.",
      questions: [
        {
          id: "role_scope",
          prompt:
            "Can you briefly describe your role and whether or how model evaluation fits into that role?",
          placeholder: shortAnswer,
        },
        {
          id: "workflow_frequency",
          prompt:
            "How often do you conduct, review, or interpret evaluations, and roughly how much of that work is generating results versus interpreting or reporting them?",
          placeholder: shortAnswer,
        },
        {
          id: "downstream_stakeholders",
          prompt:
            "Who relies on this information downstream, and how do evaluation results get used?",
          placeholder: shortAnswer,
        },
      ],
    },
    {
      id: "goals",
      title: "Goals, Needs & Decision-Making",
      description: "What are you trying to learn from evaluations, and what makes them genuinely useful?",
      questions: [
        {
          id: "core_decisions",
          prompt:
            "When you look at evaluation results, what are you typically trying to determine, decide, or communicate?",
          placeholder: shortAnswer,
        },
        {
          id: "good_eval",
          prompt: "What does a good evaluation look like to you?",
          placeholder: shortAnswer,
        },
        {
          id: "must_have_information",
          prompt:
            "What information needs to be present for an evaluation to be useful and trustworthy in your context, including the minimum metadata, provenance, or methodological detail you would require?",
          placeholder: shortAnswer,
        },
        {
          id: "quality_judgment",
          prompt:
            "How do you judge evaluation quality, credibility, comparability, or truthfulness today, and do you ever need to evaluate the evaluation itself?",
          placeholder: shortAnswer,
        },
        {
          id: "missing_information",
          prompt:
            "What information is usually missing or hardest to access when you review evaluations, and what should be most visible or easiest to compare across models?",
          placeholder: shortAnswer,
        },
        {
          id: "resource_constraints",
          prompt:
            "What resource, time, or expertise constraints shape how you review evaluation evidence?",
          placeholder: shortAnswer,
        },
        {
          id: "ideal_tool",
          prompt:
            "If you had a magic wand to design the ideal tool, what questions should it answer and what would success look like?",
          placeholder: shortAnswer,
        },
      ],
    },
    {
      id: "pain_points",
      title: "Pain Points",
      description: "Capture what makes current evaluation work slow, frustrating, or hard to trust.",
      questions: [
        {
          id: "main_frustration",
          prompt:
            "What's most frustrating about evaluating models today, especially when comparing models across formats, metric definitions, reproducibility, interpretation, or something else?",
          placeholder: shortAnswer,
        },
        {
          id: "reporting_artifacts",
          prompt:
            "What has been beneficial about existing reporting formats such as model cards, and what pain points remain?",
          placeholder: shortAnswer,
        },
      ],
    },
    {
      id: "usability",
      title: "Usability Testing",
      description: "Share your feedback after exploring the Eval Cards tool.",
      questions: [
        {
          id: "tool_rating",
          prompt: "Does the current tool meet your needs? Give it a 1-10 rating and explain briefly.",
          placeholder: shortAnswer,
        },
        {
          id: "workflow_comparison",
          prompt: "How does this compare to how you currently review evaluations?",
          placeholder: shortAnswer,
        },
        {
          id: "feature_feedback",
          prompt: "What felt most useful, least useful, or most unclear, and why?",
          placeholder: shortAnswer,
        },
        {
          id: "tool_changes",
          prompt: "How would you change the tool overall to make it more useful for your work?",
          placeholder: shortAnswer,
        },
        {
          id: "final_prompt",
          prompt: "Anything else you want us to know, or something we should have asked but didn't?",
          placeholder: shortAnswer,
        },
      ],
    },
  ],
}
