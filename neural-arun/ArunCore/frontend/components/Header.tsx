"use client";

import React, { useState } from "react";
import Image from "next/image";
import { ActiveTab } from "../lib/types";
import { MessageSquare, FolderGit2, UserCheck, PhoneCall, Moon, Sun, Menu, X } from "lucide-react";

const GithubIcon = () => (
  <svg className="h-4 w-4 fill-current" viewBox="0 0 24 24">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
  </svg>
);

const LinkedinIcon = () => (
  <svg className="h-4 w-4 fill-current" viewBox="0 0 24 24">
    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
  </svg>
);

const XIcon = () => (
  <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 24 24">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

const UdemyIcon = () => (
  <svg className="h-4 w-4 fill-current" viewBox="0 0 24 24">
    <path d="M12 0L1.5 6v12L12 24l10.5-6V6L12 0zm0 3.33L19.5 7.5 12 11.67 4.5 7.5 12 3.33zM3.75 9.33l7.5 4.17v7.17l-7.5-4.29V9.33zm16.5 7.05l-7.5 4.29v-7.17l7.5-4.17v7.05z" />
  </svg>
);

const GlobeIcon = () => (
  <svg className="h-4 w-4 fill-current" viewBox="0 0 24 24">
    <path d="M12 2a10 10 0 1 0 10 10A10.011 10.011 0 0 0 12 2zm6.93 6h-2.95a15.65 15.65 0 0 0-1.38-3.56A8.03 8.03 0 0 1 18.93 8zM12 4.07c.83 1.2 1.5 2.59 1.91 3.93h-3.82c.41-1.34 1.08-2.73 1.91-3.93zM4.26 14a7.82 7.82 0 0 1 0-4h3.38a17.6 17.6 0 0 0 0 4zm.81 2h2.95a15.65 15.65 0 0 0 1.38 3.56A8.03 8.03 0 0 1 5.07 16zm2.95-8H5.07a8.03 8.03 0 0 1 4.51-3.56A15.65 15.65 0 0 0 8.02 8zM12 19.93c-.83-1.2-1.5-2.59-1.91-3.93h3.82c-.41 1.34-1.08 2.73-1.91 3.93zM14.36 14H9.64a15.6 15.6 0 0 1 0-4h4.72a15.6 15.6 0 0 1 0 4zm1.62 5.56A15.65 15.65 0 0 0 17.36 16h2.95a8.03 8.03 0 0 1-4.33 3.56zM16.36 14a17.6 17.6 0 0 0 0-4h3.38a7.82 7.82 0 0 1 0 4z" />
  </svg>
);

interface HeaderProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  openHandoffModal: () => void;
  theme: "dark" | "light";
  toggleTheme: () => void;
  tutorConfig?: any;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  openHandoffModal,
  theme,
  toggleTheme,
  tutorConfig,
}) => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const tutorName = tutorConfig?.frontend_ui_dictionary?.header?.profile_name || tutorConfig?.name || "Arun Yadav";
  const tutorRole = tutorConfig?.frontend_ui_dictionary?.header?.profile_badge || tutorConfig?.role || "AI Assistant";
  const tutorAvatar = tutorConfig?.client_metadata?.avatar_url || tutorConfig?.avatar || "/profile_photo.png";
  const projectsTabLabel = tutorConfig?.frontend_ui_dictionary?.header?.nav_tabs?.projects?.label || tutorConfig?.projects_tab_label || "Projects";
  const aboutTabLabel = tutorConfig?.frontend_ui_dictionary?.header?.nav_tabs?.about?.label || tutorConfig?.about_tab_label || "About";

  const ctaButtonText = tutorConfig?.frontend_ui_dictionary?.header?.cta_button?.text || tutorConfig?.cta_text || "Contact";
  const headerSocials = tutorConfig?.frontend_ui_dictionary?.header?.social_links || tutorConfig?.socials;

  return (
    <header className="sticky top-0 z-40 border-b-2 border-[var(--border-accent)] bg-[var(--bg-main)]/95 backdrop-blur-md transition-colors duration-200 shadow-xs">
      <div className="mx-auto flex h-13 sm:h-16 max-w-7xl items-center justify-between px-3 sm:px-8">
        
        {/* Left Profile Identity */}
        <div className="flex items-center gap-3">
          <div className="relative h-10 w-10 overflow-hidden rounded-full border border-[var(--border-accent)] bg-slate-800 shadow-sm shrink-0">
            <Image
              src={tutorAvatar}
              alt={tutorName}
              width={40}
              height={40}
              className="h-full w-full object-cover"
              priority
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-heading text-base font-extrabold text-[var(--text-main)] tracking-tight">
                {tutorName}
              </span>
              <span className="rounded-full border border-[var(--border-accent)] bg-[var(--bg-surface)] px-2 py-0.5 font-mono text-[10px] font-semibold text-[var(--accent-green)]">
                {tutorRole}
              </span>
            </div>
          </div>
        </div>

        {/* Desktop Central Navigation Tabs */}
        <nav className="hidden md:flex items-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-1 shadow-xs">
          <button
            onClick={() => setActiveTab("chat")}
            className={`flex items-center gap-2 rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
              activeTab === "chat"
                ? "bg-[var(--accent-green)] text-white shadow-xs"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-surface-hover)]"
            }`}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            <span>AI Assistant</span>
          </button>

          <button
            onClick={() => setActiveTab("projects")}
            className={`flex items-center gap-2 rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
              activeTab === "projects"
                ? "bg-[var(--accent-green)] text-white shadow-xs"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-surface-hover)]"
            }`}
          >
            <FolderGit2 className="h-3.5 w-3.5" />
            <span>{projectsTabLabel}</span>
          </button>

          <button
            onClick={() => setActiveTab("manifesto")}
            className={`flex items-center gap-2 rounded-lg px-4 py-1.5 text-xs font-bold transition-all ${
              activeTab === "manifesto"
                ? "bg-[var(--accent-green)] text-white shadow-xs"
                : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-surface-hover)]"
            }`}
          >
            <UserCheck className="h-3.5 w-3.5" />
            <span>{aboutTabLabel}</span>
          </button>
        </nav>

        {/* Right Social Links, Theme Toggle & Contact Button */}
        <div className="hidden md:flex items-center gap-2.5">
          <div className="flex items-center gap-1 border-r border-[var(--border-subtle)] pr-2.5 text-[var(--text-muted)]">
            {headerSocials ? (
              headerSocials.map((s: any, idx: number) => {
                const key = (s.icon_key || s.icon || s.id || "").toLowerCase();
                return (
                  <a
                    key={idx}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-2 hover:text-[var(--accent-green)] transition-colors"
                    title={s.label || s.name || key}
                  >
                    {key === "github" ? (
                      <GithubIcon />
                    ) : key === "linkedin" ? (
                      <LinkedinIcon />
                    ) : key === "x" || key === "twitter" ? (
                      <XIcon />
                    ) : key === "udemy" ? (
                      <UdemyIcon />
                    ) : key === "website" || key === "globe" ? (
                      <GlobeIcon />
                    ) : (
                      <span className="text-sm font-bold">{s.symbol_emoji || "🔗"}</span>
                    )}
                  </a>
                );
              })
            ) : (
              <>
                <a
                  href="https://github.com/neural-arun"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 hover:text-[var(--accent-green)] transition-colors"
                  title="GitHub"
                >
                  <GithubIcon />
                </a>
                <a
                  href="https://linkedin.com/in/neuralarun"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 hover:text-[var(--accent-green)] transition-colors"
                  title="LinkedIn"
                >
                  <LinkedinIcon />
                </a>
                <a
                  href="https://x.com/neural_arun"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-2 hover:text-[var(--accent-green)] transition-colors"
                  title="X / Twitter"
                >
                  <XIcon />
                </a>
              </>
            )}
          </div>

          <button
            onClick={toggleTheme}
            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2 text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors"
            title="Toggle Light / Dark Mode"
          >
            {theme === "dark" ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-600" />}
          </button>

          <button
            onClick={openHandoffModal}
            className="flex items-center gap-1.5 rounded-xl border border-[var(--border-accent)] bg-[var(--bg-surface)] px-3.5 py-1.5 text-xs font-bold text-[var(--text-main)] hover:bg-[var(--accent-green)] hover:text-white transition-all shadow-xs"
          >
            <PhoneCall className="h-3.5 w-3.5 text-[var(--accent-green)] group-hover:text-white" />
            <span>{ctaButtonText}</span>
          </button>
        </div>

        {/* Mobile Menu Button */}
        <div className="flex md:hidden items-center gap-2">
          <button
            onClick={toggleTheme}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2 text-[var(--text-muted)]"
          >
            {theme === "dark" ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4" />}
          </button>

          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2 text-[var(--text-main)]"
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-3 space-y-2">
          <div className="flex flex-col gap-1.5">
            <button
              onClick={() => { setActiveTab("chat"); setMobileMenuOpen(false); }}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${
                activeTab === "chat" ? "bg-[var(--accent-green)] text-white" : "text-[var(--text-muted)]"
              }`}
            >
              <MessageSquare className="h-4 w-4" />
              <span>AI Assistant</span>
            </button>

            <button
              onClick={() => { setActiveTab("projects"); setMobileMenuOpen(false); }}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${
                activeTab === "projects" ? "bg-[var(--accent-green)] text-white" : "text-[var(--text-muted)]"
              }`}
            >
              <FolderGit2 className="h-4 w-4" />
              <span>Projects</span>
            </button>

            <button
              onClick={() => { setActiveTab("manifesto"); setMobileMenuOpen(false); }}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${
                activeTab === "manifesto" ? "bg-[var(--accent-green)] text-white" : "text-[var(--text-muted)]"
              }`}
            >
              <UserCheck className="h-4 w-4" />
              <span>About</span>
            </button>

            <button
              onClick={() => { openHandoffModal(); setMobileMenuOpen(false); }}
              className="flex items-center justify-center gap-2 rounded-lg bg-[var(--accent-green)] py-2 text-xs font-bold text-white mt-2"
            >
              <PhoneCall className="h-4 w-4" />
              <span>Contact Arun</span>
            </button>
          </div>
        </div>
      )}
    </header>
  );
};
