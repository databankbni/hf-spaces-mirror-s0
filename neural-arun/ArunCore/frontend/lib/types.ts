export interface ThoughtStep {
  id: string;
  timestamp: string;
  text: string;
  toolName?: string;
  args?: Record<string, any>;
}

export interface Message {
  id: string;
  sender: "user" | "twin" | "human_arun";
  name?: string;
  text: string;
  timestamp: string;
  thoughts?: string[];
  isStreaming?: boolean;
  error?: boolean;
}

export interface ProjectItem {
  id: string;
  title: string;
  name: string;
  category: "Healthcare" | "Education" | "RAG & AI" | "Agents & Tools" | "Automation & Scraping";
  description: string;
  githubUrl: string;
  techStack: string[];
  highlights: string[];
  suggestedPrompt: string;
  updatedAt: string; // ISO date string e.g. 2026-07-24T10:19:09Z
  updatedAtLabel: string; // e.g. "Updated Jul 2026"
  stars?: number;
  forks?: number;
  relativeTime?: string;
  isRecentActivity?: boolean;
}

export type ActiveTab = "chat" | "projects" | "manifesto";

export interface HandoffFormData {
  name: string;
  emailOrPhone: string;
  company?: string;
  message: string;
}
