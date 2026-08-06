"use client";

import React from "react";
import Image from "next/image";
import { Sparkles, RefreshCw, Layers, ShieldCheck, HeartPulse, Scale, Briefcase, Bot, FolderGit2, User, PhoneCall, ChevronRight, MessageSquare, Compass } from "lucide-react";
import { ActiveTab } from "../lib/types";

// Inline Brand SVGs for bulletproof icon rendering
const GithubIcon = () => (
  <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
  </svg>
);

const LinkedinIcon = () => (
  <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24">
    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
  </svg>
);

const TwitterIcon = () => (
  <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
);

interface SidebarProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  openHandoffModal: () => void;
  onSelectPrompt: (prompt: string) => void;
  onResetSession: () => void;
  messageCount: number;
  tutorConfig?: any;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  openHandoffModal,
  onSelectPrompt,
  onResetSession,
  messageCount,
  tutorConfig,
}) => {
  const tutorName = tutorConfig?.frontend_ui_dictionary?.sidebar?.profile_card?.name || tutorConfig?.name || "Arun Yadav";
  const tutorTitle = tutorConfig?.frontend_ui_dictionary?.sidebar?.profile_card?.title || tutorConfig?.role || "AI Systems Architect • Healthcare & Education";
  const tutorSubBadge = tutorConfig?.frontend_ui_dictionary?.sidebar?.profile_card?.sub_badge || "Stateful RAG • Zero-Hallucination";
  const tutorAvatar = tutorConfig?.client_metadata?.avatar_url || tutorConfig?.avatar || "/profile_photo.png";
  const projectsTabTitle = tutorConfig?.frontend_ui_dictionary?.sidebar?.navigation?.items?.[1]?.label || tutorConfig?.projects_tab_label || "Projects";
  const projectsTabDesc = projectsTabTitle.includes("Courses") ? "Featured Courses & Syllabi" : "22+ Production Systems";
  
  const ctaTitle = tutorConfig?.frontend_ui_dictionary?.sidebar?.contact_button?.title || tutorConfig?.cta_text || "Contact & Consult";
  const ctaSubtitle = tutorConfig?.frontend_ui_dictionary?.sidebar?.contact_button?.subtitle || (tutorConfig?.name ? `Connect directly with ${tutorConfig.name}` : "Hire Arun for Custom AI Systems");

  const customQuickPrompts = tutorConfig?.sidebar_questions || tutorConfig?.suggested_questions;

  const navItems = [
    {
      id: "chat" as ActiveTab,
      label: "AI Assistant",
      icon: <Bot className="h-4 w-4" />,
      description: "Interactive 3-Way Digital Twin",
    },
    {
      id: "projects" as ActiveTab,
      label: projectsTabTitle,
      icon: <FolderGit2 className="h-4 w-4" />,
      description: projectsTabDesc,
    },
    {
      id: "manifesto" as ActiveTab,
      label: "About & Manifesto",
      icon: <User className="h-4 w-4" />,
      description: "Engineering Principles & Bio",
    },
  ];

  const defaultQuickPrompts = [
    {
      text: "How do you build trusted AI software for healthcare?",
      icon: <HeartPulse className="h-3.5 w-3.5 text-rose-500 shrink-0" />,
      category: "Healthcare",
    },
    {
      text: "Explain your zero-hallucination hybrid RAG architecture.",
      icon: <Layers className="h-3.5 w-3.5 text-amber-500 shrink-0" />,
      category: "RAG Architecture",
    },
    {
      text: "Tell me about the Indian Legal RAG System.",
      icon: <Scale className="h-3.5 w-3.5 text-indigo-500 shrink-0" />,
      category: "Legal AI",
    },
    {
      text: "How can I hire or consult with Arun for a project?",
      icon: <Briefcase className="h-3.5 w-3.5 text-emerald-500 shrink-0" />,
      category: "Collaboration",
    },
  ];

  return (
    <aside className="hidden lg:flex w-80 shrink-0 h-full flex-col gap-4 overflow-y-auto p-4 pb-20 border-r border-[var(--border-subtle)] bg-[var(--bg-sidebar)] text-[var(--text-main)] transition-colors duration-200 shadow-sm custom-scrollbar">
      
      {/* Profile Header & Welcome Card */}
      <div className="relative flex flex-col gap-3 rounded-2xl shiny-border-card bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="relative shrink-0">
            <div className="h-12 w-12 overflow-hidden rounded-full border-2 border-[var(--accent-green)]/40 bg-slate-100 dark:bg-slate-800 shadow-sm">
              <Image
                src={tutorAvatar}
                alt={tutorName}
                width={48}
                height={48}
                className="h-full w-full object-cover"
                priority
              />
            </div>
            <span className="absolute bottom-0 right-0 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[var(--accent-green)] ring-2 ring-[var(--bg-card)]">
              <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
            </span>
          </div>

          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-extrabold text-[var(--text-main)] tracking-tight truncate leading-tight">
              {tutorName}
            </h2>
            <p className="text-xs font-semibold text-[var(--accent-green)] leading-tight mt-0.5">
              {tutorTitle}
            </p>
            <p className="text-[11px] text-[var(--text-dim)] mt-1 flex items-center gap-1 leading-none">
              <ShieldCheck className="h-3 w-3 text-[var(--accent-green)] shrink-0" />
              {tutorSubBadge}
            </p>
          </div>
        </div>

        {/* Social Links */}
        <div className="flex flex-wrap items-center justify-between gap-1.5 border-t border-[var(--border-subtle)] pt-2.5">
          {tutorConfig && tutorConfig.socials ? (
            tutorConfig.socials.map((s: any, idx: number) => {
              const key = (s.icon_key || s.icon || s.id || "").toLowerCase();
              const emoji = s.symbol_emoji || s.symbol || (key === "udemy" ? "🎓" : key === "website" ? "🌐" : key === "linkedin" ? "💼" : key === "x" ? "𝕏" : key === "github" ? "🐙" : "🔗");

              return (
                <a
                  key={idx}
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-[11px] font-semibold text-[var(--text-dim)] hover:text-[var(--accent-green)] transition-colors"
                >
                  {key === "github" ? (
                    <GithubIcon />
                  ) : key === "linkedin" ? (
                    <LinkedinIcon />
                  ) : key === "x" || key === "twitter" ? (
                    <TwitterIcon />
                  ) : (
                    <span className="text-xs">{emoji}</span>
                  )}
                  <span>{s.name || s.label}</span>
                </a>
              );
            })
          ) : (
            <>
              <a
                href="https://github.com/neural-arun"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[11px] font-semibold text-[var(--text-dim)] hover:text-[var(--accent-green)] transition-colors"
              >
                <GithubIcon />
                <span>GitHub</span>
              </a>

              <a
                href="https://linkedin.com/in/neuralarun"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[11px] font-semibold text-[var(--text-dim)] hover:text-[var(--accent-green)] transition-colors"
              >
                <LinkedinIcon />
                <span>LinkedIn</span>
              </a>

              <a
                href="https://x.com/Neural_Arun"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[11px] font-semibold text-[var(--text-dim)] hover:text-[var(--accent-green)] transition-colors"
              >
                <TwitterIcon />
                <span>X / Twitter</span>
              </a>
            </>
          )}
        </div>
      </div>

      {/* Laptop Sidebar Navigation Section */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-dim)] px-2">
          Navigation
        </span>

        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center justify-between p-3 rounded-xl font-medium text-xs transition-all text-left group ${
                isActive
                  ? "bg-[var(--accent-green)]/15 border-2 border-[var(--accent-green)]/60 text-[var(--accent-green)] font-bold shadow-sm"
                  : "border border-transparent hover:border-[var(--border-subtle)] hover:bg-[var(--bg-card)] text-[var(--text-main)]"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className={`p-2 rounded-lg ${isActive ? "bg-[var(--accent-green)] text-white" : "bg-[var(--bg-card)] text-[var(--text-dim)] group-hover:text-[var(--accent-green)]"}`}>
                  {item.icon}
                </span>
                <div>
                  <p className="font-extrabold leading-tight text-xs">{item.label}</p>
                  <p className="text-[10px] text-[var(--text-dim)] font-normal">{item.description}</p>
                </div>
              </div>
              <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isActive ? "text-[var(--accent-green)] translate-x-0.5" : "text-[var(--text-dim)] opacity-40 group-hover:opacity-100"}`} />
            </button>
          );
        })}

        {/* Contact Handoff Trigger Button */}
        <button
          onClick={openHandoffModal}
          className="mt-1 flex items-center justify-between p-3 rounded-xl font-bold text-xs bg-[var(--accent-green)] hover:bg-[var(--accent-green-hover)] text-white shadow-md transition-all active:scale-98"
        >
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-lg bg-black/20 text-white">
              <PhoneCall className="h-4 w-4" />
            </span>
            <div className="text-left">
              <p className="font-extrabold text-xs">{ctaTitle}</p>
              <p className="text-[10px] text-white opacity-90 font-normal">{ctaSubtitle}</p>
            </div>
          </div>
          <ChevronRight className="h-3.5 w-3.5 opacity-80" />
        </button>
      </div>

      {/* Compact Quick Questions Section */}
      <div className="flex flex-col gap-2 pt-3 border-t border-[var(--border-subtle)]">
        <div className="flex items-center justify-between px-1">
          <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-dim)] flex items-center gap-1.5">
            <Compass className="h-3.5 w-3.5 text-[var(--accent-green)]" />
            Quick Questions
          </span>
          {messageCount > 0 && (
            <button
              onClick={onResetSession}
              className="flex items-center gap-1 text-[11px] text-[var(--text-dim)] hover:text-[var(--accent-green)] transition-colors font-medium"
              title="Reset conversation session"
            >
              <RefreshCw className="h-3 w-3" />
              <span>Reset</span>
            </button>
          )}
        </div>

        <div className="flex flex-col gap-2">
          {(customQuickPrompts
            ? customQuickPrompts.map((q: string, idx: number) => ({
                text: q,
                icon: idx === 0 ? <HeartPulse className="h-3.5 w-3.5 text-rose-500 shrink-0" /> : idx === 1 ? <Layers className="h-3.5 w-3.5 text-amber-500 shrink-0" /> : idx === 2 ? <Scale className="h-3.5 w-3.5 text-indigo-500 shrink-0" /> : <Briefcase className="h-3.5 w-3.5 text-emerald-500 shrink-0" />,
                badgeColor: idx === 0 ? "text-rose-500" : idx === 1 ? "text-amber-500" : idx === 2 ? "text-indigo-500" : "text-emerald-500",
                category: "Question " + (idx + 1),
              }))
            : [
                {
                  text: defaultQuickPrompts[0].text,
                  icon: <HeartPulse className="h-3.5 w-3.5 text-rose-500 shrink-0" />,
                  badgeColor: "text-rose-500",
                  category: defaultQuickPrompts[0].category,
                },
                {
                  text: defaultQuickPrompts[1].text,
                  icon: <Layers className="h-3.5 w-3.5 text-amber-500 shrink-0" />,
                  badgeColor: "text-amber-500",
                  category: defaultQuickPrompts[1].category,
                },
                {
                  text: defaultQuickPrompts[2].text,
                  icon: <Scale className="h-3.5 w-3.5 text-indigo-500 shrink-0" />,
                  badgeColor: "text-indigo-500",
                  category: defaultQuickPrompts[2].category,
                },
                {
                  text: defaultQuickPrompts[3].text,
                  icon: <Briefcase className="h-3.5 w-3.5 text-emerald-500 shrink-0" />,
                  badgeColor: "text-emerald-500",
                  category: defaultQuickPrompts[3].category,
                },
              ]
          ).map((item: any, idx: number) => (
            <button
              key={idx}
              onClick={() => {
                setActiveTab("chat");
                onSelectPrompt(item.text);
              }}
              className="group flex items-start gap-2.5 text-left p-2.5 rounded-xl shiny-border-card bg-[var(--bg-card)] hover:bg-[var(--bg-surface-hover)] transition-all text-xs text-[var(--text-main)] font-medium leading-snug shadow-xs cursor-pointer"
            >
              {item.icon}
              <div className="flex-1 min-w-0">
                <span className={`block text-[10px] font-extrabold uppercase tracking-wider mb-0.5 ${item.badgeColor || 'text-[var(--accent-green)]'}`}>
                  {item.category}
                </span>
                <span className="group-hover:text-[var(--text-main)] transition-colors">
                  "{item.text}"
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
};
