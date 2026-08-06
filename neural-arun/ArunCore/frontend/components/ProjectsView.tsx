"use client";

import React, { useState, useEffect } from "react";
import { PROJECTS_DATA } from "../lib/projectsData";
import { ProjectItem, ActiveTab } from "../lib/types";
import { ExternalLink, Search, Sparkles, ArrowRight, Star, GitFork, Activity, Flame, RefreshCw } from "lucide-react";

const GithubIcon = () => (
  <svg className="h-4 w-4 fill-current" viewBox="0 0 24 24">
    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
  </svg>
);

interface ProjectsViewProps {
  onSelectPrompt: (prompt: string) => void;
  setActiveTab: (tab: ActiveTab) => void;
  tutorConfig?: any;
}

function formatRelativeTime(dateString: string): { label: string; isRecent: boolean } {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return { label: "Recently updated", isRecent: false };
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffHours < 1) return { label: "Pushed < 1h ago", isRecent: true };
    if (diffHours < 24) return { label: `Pushed ${diffHours}h ago`, isRecent: true };
    if (diffDays === 1) return { label: "Pushed yesterday", isRecent: true };
    if (diffDays <= 7) return { label: `Pushed ${diffDays}d ago`, isRecent: true };
    if (diffDays < 30) return { label: `Pushed ${diffDays}d ago`, isRecent: false };
    const months = Math.floor(diffDays / 30);
    if (months === 1) return { label: "Pushed 1m ago", isRecent: false };
    if (months < 12) return { label: `Pushed ${months}m ago`, isRecent: false };
    return { label: `Pushed ${Math.floor(months / 12)}y ago`, isRecent: false };
  } catch {
    return { label: "Recently updated", isRecent: false };
  }
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({
  onSelectPrompt,
  setActiveTab,
  tutorConfig,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sortBy, setSortBy] = useState<"recent" | "stars">("recent");
  const [projects, setProjects] = useState<ProjectItem[]>(PROJECTS_DATA);
  const [isSyncing, setIsSyncing] = useState<boolean>(true);
  const [lastSyncedTime, setLastSyncedTime] = useState<string>("");

  const categories = ["All", "Healthcare", "Education", "RAG & AI", "Agents & Tools", "Automation & Scraping"];

  // Live GitHub Repository Sync
  useEffect(() => {
    let isMounted = true;
    async function syncGitHubRepos() {
      setIsSyncing(true);
      try {
        const res = await fetch("https://api.github.com/users/neural-arun/repos?sort=pushed&direction=desc&per_page=100");
        if (!res.ok) throw new Error(`GitHub API HTTP ${res.status}`);
        const githubRepos: any[] = await res.json();

        if (!isMounted) return;

        // Map GitHub repo details onto local projects & discover unlisted repos
        const repoMap = new Map<string, any>();
        githubRepos.forEach((r) => {
          repoMap.set(r.name.toLowerCase(), r);
        });

        const updatedList: ProjectItem[] = PROJECTS_DATA.map((proj) => {
          const matchingRepo = repoMap.get(proj.name.toLowerCase()) || repoMap.get(proj.id.toLowerCase());
          if (matchingRepo) {
            const pushedDate = matchingRepo.pushed_at || matchingRepo.updated_at || proj.updatedAt;
            const { label, isRecent } = formatRelativeTime(pushedDate);
            return {
              ...proj,
              updatedAt: pushedDate,
              updatedAtLabel: label,
              relativeTime: label,
              isRecentActivity: isRecent,
              stars: matchingRepo.stargazers_count ?? 0,
              forks: matchingRepo.forks_count ?? 0,
            };
          } else {
            const { label, isRecent } = formatRelativeTime(proj.updatedAt);
            return {
              ...proj,
              relativeTime: label,
              isRecentActivity: isRecent,
            };
          }
        });

        // Check for public repos not in static dataset and add them automatically
        const knownNames = new Set(PROJECTS_DATA.map((p) => p.name.toLowerCase()));
        githubRepos.forEach((r) => {
          if (!knownNames.has(r.name.toLowerCase()) && !r.fork && !r.private) {
            const { label, isRecent } = formatRelativeTime(r.pushed_at || r.updated_at);
            updatedList.push({
              id: r.name,
              name: r.name,
              title: r.name.replace(/[-_]/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
              category: "Agents & Tools",
              description: r.description || "Public software repository by Arun Yadav.",
              githubUrl: r.html_url,
              techStack: [r.language || "Python", "GitHub"],
              highlights: [`Live repository from github.com/neural-arun/${r.name}`],
              suggestedPrompt: `Tell me about the ${r.name} project on GitHub!`,
              updatedAt: r.pushed_at || r.updated_at,
              updatedAtLabel: label,
              relativeTime: label,
              isRecentActivity: isRecent,
              stars: r.stargazers_count ?? 0,
              forks: r.forks_count ?? 0,
            });
          }
        });

        setProjects(updatedList);
        setLastSyncedTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      } catch (err) {
        console.warn("GitHub live sync fallback to static dataset:", err);
        // Calculate relative times for static data
        setProjects(
          PROJECTS_DATA.map((proj) => {
            const { label, isRecent } = formatRelativeTime(proj.updatedAt);
            return { ...proj, relativeTime: label, isRecentActivity: isRecent };
          })
        );
      } finally {
        if (isMounted) setIsSyncing(false);
      }
    }

    syncGitHubRepos();
    return () => {
      isMounted = false;
    };
  }, []);

  // Filter and Sort Projects
  const processedProjects = projects
    .filter((project) => {
      const matchesCategory = selectedCategory === "All" || project.category === selectedCategory;
      const matchesSearch =
        project.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        project.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        project.techStack.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchesCategory && matchesSearch;
    })
    .sort((a, b) => {
      if (sortBy === "stars") {
        return (b.stars || 0) - (a.stars || 0);
      }
      // Default: Sort by latest commit date descending (most recent first!)
      const dateA = new Date(a.updatedAt).getTime() || 0;
      const dateB = new Date(b.updatedAt).getTime() || 0;
      return dateB - dateA;
    });

  const handleCardClick = (githubUrl: string) => {
    window.open(githubUrl, "_blank", "noopener,noreferrer");
  };

  const handleAskTwin = (e: React.MouseEvent, title: string, repoName: string) => {
    e.stopPropagation();
    const prompt = `Can you give me a comprehensive summary of the ${title} project (${repoName}) based on its repository README and technical architecture?`;
    onSelectPrompt(prompt);
    setActiveTab("chat");
  };
  const coursesList = tutorConfig?.courses || [];

  if (tutorConfig && coursesList.length > 0) {
    const pageTitle = tutorConfig?.frontend_ui_dictionary?.projects_view?.header_title || tutorConfig?.title || "Courses & Masterclasses";
    const pageSubtitle = tutorConfig?.frontend_ui_dictionary?.projects_view?.header_subtitle || "Browse flagship curriculum, course outcomes, and enrollment options.";

    return (
      <div className="h-full overflow-y-auto px-4 py-8 sm:px-12 pb-24 sm:pb-12 bg-[var(--bg-main)] text-[var(--text-main)]">
        <div className="mx-auto max-w-5xl space-y-6 animate-fade-slide">
          {/* Header */}
          <div className="shiny-header-box rounded-2xl p-5 sm:p-6 bg-[var(--bg-card)] space-y-2">
            <h1 className="font-heading text-2xl sm:text-4xl font-extrabold text-[var(--text-main)] tracking-tight">
              {pageTitle}
            </h1>
            <p className="text-sm sm:text-base font-semibold text-[var(--accent-green)]">
              {pageSubtitle}
            </p>
          </div>

          {/* Courses Cards Grid */}
          <div className="grid grid-cols-1 gap-6">
            {coursesList.map((course: any, idx: number) => (
              <div
                key={course.id || idx}
                className="shiny-border-card rounded-2xl bg-[var(--bg-card)] p-5 sm:p-6 shadow-sm hover:shadow-md transition-all space-y-4"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-4">
                  <div>
                    <h2 className="font-heading text-xl sm:text-2xl font-extrabold text-[var(--text-main)]">
                      {course.title}
                    </h2>
                    <p className="text-xs sm:text-sm font-semibold text-[var(--accent-green)] mt-0.5">
                      {course.subtitle}
                    </p>
                  </div>
                  {course.price && (
                    <span className="self-start sm:self-center badge-cobalt px-3.5 py-1 rounded-full font-mono text-xs sm:text-sm font-bold shadow-xs">
                      {course.price}
                    </span>
                  )}
                </div>

                <p className="text-xs sm:text-sm text-[var(--text-muted)] leading-relaxed">
                  {course.description}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  {course.target_audience && (
                    <div className="badge-amber rounded-xl p-3.5 text-xs shadow-xs">
                      <span className="font-extrabold block mb-1">🎯 Target Audience:</span>
                      <span className="font-medium">{course.target_audience}</span>
                    </div>
                  )}
                  {course.outcomes && (
                    <div className="badge-emerald rounded-xl p-3.5 text-xs shadow-xs">
                      <span className="font-extrabold block mb-1">🚀 Key Outcomes:</span>
                      <span className="font-medium">{course.outcomes}</span>
                    </div>
                  )}
                </div>

                {course.link && (
                  <div className="pt-3 flex justify-end">
                    <a
                      href={course.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-xl bg-[var(--accent-green)] hover:bg-[var(--accent-green-hover)] px-4 py-2 text-xs sm:text-sm font-bold text-white shadow-sm transition-all active:scale-95"
                    >
                      <span>Enroll / View Course</span>
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-6 sm:py-8 sm:px-8 pb-20 sm:pb-8">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header with Live Sync Status */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-[var(--border-subtle)] pb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-[var(--text-main)] tracking-tight">
              Projects & Engineering Repositories
            </h1>
            <p className="text-sm sm:text-base text-[var(--text-muted)] mt-1.5 font-medium">
              Click any project card to view its live GitHub repository, or ask my AI Twin for a summary.
            </p>
          </div>

          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-3 h-4 w-4 text-[var(--text-dim)]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search stack or project..."
              className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] py-2.5 pl-9 pr-4 text-xs sm:text-sm text-[var(--text-main)] placeholder-[var(--text-dim)] focus:border-[var(--border-accent)] focus:outline-none"
            />
          </div>
        </div>

        {/* Sort & Category Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Category Pills */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`rounded-lg px-3.5 py-1.5 text-xs sm:text-sm font-semibold transition-all whitespace-nowrap ${
                  selectedCategory === cat
                    ? "bg-[var(--accent-teal)] text-white shadow-sm"
                    : "bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-surface-hover)]"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Sort Selector */}
          <div className="flex items-center gap-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-1 shrink-0">
            <button
              onClick={() => setSortBy("recent")}
              className={`flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                sortBy === "recent"
                  ? "bg-[var(--bg-surface-hover)] text-[var(--accent-green)] font-bold shadow-xs"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
              }`}
            >
              <Flame className="h-3.5 w-3.5" />
              <span>Latest Commits</span>
            </button>
            <button
              onClick={() => setSortBy("stars")}
              className={`flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition-all ${
                sortBy === "stars"
                  ? "bg-[var(--bg-surface-hover)] text-[var(--accent-amber)] font-bold shadow-xs"
                  : "text-[var(--text-muted)] hover:text-[var(--text-main)]"
              }`}
            >
              <Star className="h-3.5 w-3.5" />
              <span>Stars</span>
            </button>
          </div>
        </div>

        {/* Project Cards */}
        <div className="space-y-5">
          {processedProjects.map((proj) => (
            <div
              key={proj.id}
              onClick={() => handleCardClick(proj.githubUrl)}
              className="group cursor-pointer rounded-2xl shiny-border-card bg-[var(--bg-surface)] p-6 transition-all hover:bg-[var(--bg-surface-hover)] hover:shadow-xl"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-main)] px-2.5 py-0.5 font-mono text-xs font-semibold text-[var(--accent-amber)]">
                      {proj.category}
                    </span>

                    {/* Dynamic Commit Activity Badge */}
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-0.5 font-mono text-xs font-semibold transition-all ${
                        proj.isRecentActivity
                          ? "bg-[var(--accent-green)]/15 border border-[var(--accent-green)]/30 text-[var(--accent-green)]"
                          : "bg-[var(--bg-main)] border border-[var(--border-subtle)] text-[var(--text-muted)]"
                      }`}
                    >
                      {proj.isRecentActivity ? (
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--accent-green)] opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-[var(--accent-green)]"></span>
                        </span>
                      ) : (
                        <Activity className="h-3 w-3 text-[var(--text-dim)]" />
                      )}
                      <span>{proj.relativeTime || proj.updatedAtLabel}</span>
                    </span>
                  </div>

                  {/* Title */}
                  <h3 className="font-heading text-xl sm:text-2xl font-bold text-[var(--text-main)] group-hover:text-[var(--accent-green)] transition-colors">
                    {proj.title}
                  </h3>
                </div>

                {/* GitHub Specs & External Link */}
                <div className="flex items-center gap-3 text-xs font-semibold text-[var(--text-muted)] group-hover:text-[var(--text-main)] transition-colors shrink-0">
                  {typeof proj.stars === "number" && proj.stars > 0 && (
                    <span className="flex items-center gap-1 text-[var(--accent-amber)]">
                      <Star className="h-3.5 w-3.5 fill-current" />
                      <span>{proj.stars}</span>
                    </span>
                  )}
                  {typeof proj.forks === "number" && proj.forks > 0 && (
                    <span className="flex items-center gap-1 text-[var(--text-muted)]">
                      <GitFork className="h-3.5 w-3.5" />
                      <span>{proj.forks}</span>
                    </span>
                  )}
                  <div className="flex items-center gap-1.5">
                    <GithubIcon />
                    <span className="font-mono">{proj.name}</span>
                    <ExternalLink className="h-3.5 w-3.5 ml-0.5" />
                  </div>
                </div>
              </div>

              {/* Description */}
              <p className="mt-3 text-sm sm:text-base text-[var(--text-muted)] leading-relaxed font-normal">
                {proj.description}
              </p>

              {/* Highlights */}
              <div className="mt-3.5 space-y-1">
                {proj.highlights.map((hl, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-xs sm:text-sm text-[var(--text-muted)]">
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent-green)] shrink-0" />
                    <span>{hl}</span>
                  </div>
                ))}
              </div>

              {/* Footer Tech Badges & Ask Twin Button */}
              <div className="mt-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-t border-[var(--border-subtle)] pt-4">
                <div className="flex flex-wrap gap-1.5">
                  {proj.techStack.map((tech, tIdx) => (
                    <span
                      key={tIdx}
                      className="rounded-md bg-[var(--bg-main)] px-2.5 py-1 font-mono text-xs text-[var(--text-muted)] border border-[var(--border-subtle)]"
                    >
                      {tech}
                    </span>
                  ))}
                </div>

                {/* Ask Twin Summary Action */}
                <button
                  onClick={(e) => handleAskTwin(e, proj.title, proj.name)}
                  className="flex items-center gap-1.5 rounded-xl border border-[var(--border-accent)] bg-[var(--bg-surface-hover)] px-3.5 py-2 text-xs sm:text-sm font-bold text-[var(--accent-green)] transition-all hover:bg-[var(--accent-green)] hover:text-white shrink-0"
                  title="Ask Twin for a summary based on README"
                >
                  <Sparkles className="h-4 w-4" />
                  <span>Ask Assistant for Summary</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
