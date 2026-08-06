"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7860";

const SUGGESTED_QUESTIONS = [
  "Why do users struggle to discover new music?",
  "What are the most common frustrations with recommendations?",
  "What causes users to repeat-listen?",
  "Which user segments face discovery challenges?",
  "What unmet needs emerge consistently?",
  "What listening behaviors are users trying to achieve?",
];

const SOURCE_BREAKDOWN = [
  { name: "Play Store", key: "play_store", count: 366, color: "#1db954" },
  { name: "Spotify Community", key: "spotify_community", count: 86, color: "#5865f2" },
  { name: "App Store", key: "app_store", count: 90, color: "#007aff" },
  { name: "Trustpilot", key: "trustpilot", count: 37, color: "#00b67a" },
  { name: "YouTube", key: "youtube", count: 16, color: "#ff0000" },
  { name: "Reddit", key: "reddit", count: 11, color: "#ff6314" },
];

const SOURCE_COLORS: Record<string, string> = {
  play_store: "#1db954",
  reddit: "#ff6314",
  spotify_community: "#5865f2",
  trustpilot: "#00b67a",
  youtube: "#ff0000",
  app_store: "#007aff",
};

type Tab = "chat" | "themes";

type Source = {
  source: string;
  date: string;
  text: string;
  url?: string | null;
  score: number;
};

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; sources: Source[] };

type Theme = {
  theme_name: string;
  count: number;
  top_quotes: { text: string; source: string; date: string }[];
};

function SpotifyLogo() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 fill-spotify-black" aria-hidden>
      <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z" />
    </svg>
  );
}

function sourceLabel(source: string) {
  return source.replace(/_/g, " ");
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 rounded-xl bg-spotify-card px-4 py-3 w-fit">
      <span className="h-2 w-2 rounded-full bg-spotify-green animate-bounce-dot" />
      <span className="h-2 w-2 rounded-full bg-spotify-green animate-bounce-dot animate-bounce-dot-delay-1" />
      <span className="h-2 w-2 rounded-full bg-spotify-green animate-bounce-dot animate-bounce-dot-delay-2" />
    </div>
  );
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retrievedSources, setRetrievedSources] = useState<Source[]>([]);

  const [themes, setThemes] = useState<Theme[]>([]);
  const [themesLoading, setThemesLoading] = useState(false);
  const [themesError, setThemesError] = useState<string | null>(null);
  const [themesLoaded, setThemesLoaded] = useState(false);

  const fetchThemes = useCallback(async () => {
    if (themesLoaded) return;
    setThemesLoading(true);
    setThemesError(null);
    try {
      const res = await fetch(`${API_URL}/themes`);
      if (!res.ok) throw new Error(`Failed to load themes (${res.status})`);
      const data: Theme[] = await res.json();
      setThemes(data);
      setThemesLoaded(true);
    } catch (err) {
      setThemesError(err instanceof Error ? err.message : "Failed to load themes");
    } finally {
      setThemesLoading(false);
    }
  }, [themesLoaded]);

  useEffect(() => {
    if (activeTab === "themes") {
      fetchThemes();
    }
  }, [activeTab, fetchThemes]);

  const handleSubmit = async (e?: FormEvent, questionOverride?: string) => {
    e?.preventDefault();
    const question = (questionOverride ?? input).trim();
    if (!question || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, k: 5 }),
      });
      if (!res.ok) throw new Error(`Query failed (${res.status})`);
      const data: { answer: string; sources: Source[] } = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, sources: data.sources },
      ]);
      setRetrievedSources(data.sources);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${msg}`, sources: [] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-spotify-black">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-spotify-green bg-spotify-black px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-spotify-green">
            <SpotifyLogo />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-spotify-text">
              Spotify Review Discovery Engine
            </h1>
            <p className="text-sm text-spotify-muted">
              2,054 reviews · 606 relevant · 6 sources
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("chat")}
            className={`rounded-full px-5 py-2 text-sm font-medium transition-colors ${
              activeTab === "chat"
                ? "bg-spotify-green text-spotify-black"
                : "border border-spotify-border text-spotify-muted hover:text-spotify-text"
            }`}
          >
            Chat
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("themes")}
            className={`rounded-full px-5 py-2 text-sm font-medium transition-colors ${
              activeTab === "themes"
                ? "bg-spotify-green text-spotify-black"
                : "border border-spotify-border text-spotify-muted hover:text-spotify-text"
            }`}
          >
            Theme Analysis
          </button>
        </div>
      </header>

      {/* Chat tab */}
      {activeTab === "chat" && (
        <div className="flex flex-1 overflow-hidden">
          {/* Left panel — 70% */}
          <div className="flex w-[70%] flex-col border-r border-spotify-border">
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.length === 0 && !loading && (
                <div className="flex h-full min-h-[300px] flex-col items-center justify-center text-spotify-muted">
                  <span className="mb-3 text-4xl">🎵</span>
                  <p>Ask anything about Spotify user feedback</p>
                </div>
              )}

              {messages.map((msg, i) =>
                msg.role === "user" ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-spotify-green px-4 py-3 text-sm text-spotify-black">
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex justify-start">
                    <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-spotify-card px-4 py-3">
                      <p className="text-sm leading-relaxed text-spotify-text whitespace-pre-wrap">
                        {msg.content}
                      </p>
                      {msg.sources.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {msg.sources.map((src, j) => (
                            <span
                              key={j}
                              className="rounded-full px-2.5 py-0.5 text-xs font-medium text-white"
                              style={{
                                backgroundColor:
                                  SOURCE_COLORS[src.source] || "#555555",
                              }}
                            >
                              {sourceLabel(src.source)} · {src.date} ·{" "}
                              {src.score.toFixed(2)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ),
              )}

              {loading && (
                <div className="flex justify-start">
                  <TypingIndicator />
                </div>
              )}
            </div>

            {/* Suggested questions + input */}
            <div className="border-t border-spotify-border p-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => setInput(q)}
                    className="rounded-full border border-spotify-green bg-transparent px-3 py-1.5 text-xs text-spotify-text transition-colors hover:bg-spotify-green/10"
                  >
                    {q}
                  </button>
                ))}
              </div>
              {error && (
                <p className="text-xs text-red-400">{error}</p>
              )}
              <form onSubmit={(e) => handleSubmit(e)} className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask a question about Spotify reviews..."
                  className="flex-1 rounded-lg border border-spotify-border bg-spotify-panel px-4 py-2.5 text-sm text-spotify-text placeholder:text-spotify-muted focus:border-spotify-green focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="rounded-lg bg-spotify-green px-6 py-2.5 text-sm font-semibold text-spotify-black transition-opacity disabled:opacity-50"
                >
                  Send
                </button>
              </form>
            </div>
          </div>

          {/* Right sidebar — 30% */}
          <aside className="w-[30%] overflow-y-auto bg-spotify-panel p-5 space-y-6">
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Total reviews", value: "2,054" },
                { label: "Relevant records", value: "606" },
                { label: "Relevance rate", value: "29.5%" },
                { label: "Date range", value: "4 mo" },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="rounded-lg border border-spotify-border bg-spotify-card p-3"
                >
                  <p className="text-xl font-bold text-spotify-text">{stat.value}</p>
                  <p className="text-xs text-spotify-muted">{stat.label}</p>
                </div>
              ))}
            </div>

            <div>
              <h3 className="mb-3 text-sm font-semibold text-spotify-text">
                Sources retrieved
              </h3>
              {retrievedSources.length === 0 ? (
                <p className="text-xs text-spotify-muted">
                  Submit a query to see which sources were used.
                </p>
              ) : (
                <div className="space-y-2">
                  {retrievedSources.map((src, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg border border-spotify-border bg-spotify-card px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-full"
                          style={{
                            backgroundColor:
                              SOURCE_COLORS[src.source] || "#555",
                          }}
                        />
                        <span className="text-xs text-spotify-text">
                          {sourceLabel(src.source)}
                        </span>
                      </div>
                      <span className="text-xs font-mono text-spotify-green">
                        {src.score.toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <h3 className="mb-3 text-sm font-semibold text-spotify-text">
                Source breakdown
              </h3>
              <div className="space-y-2">
                {SOURCE_BREAKDOWN.map((src) => (
                  <div
                    key={src.key}
                    className="flex items-center justify-between rounded-lg border border-spotify-border bg-spotify-card px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: src.color }}
                      />
                      <span className="text-xs text-spotify-text">{src.name}</span>
                    </div>
                    <span className="text-xs text-spotify-muted">{src.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      )}

      {/* Theme Analysis tab */}
      {activeTab === "themes" && (
        <div className="flex-1 overflow-y-auto p-6">
          {themesLoading && (
            <div className="flex items-center justify-center py-20">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-spotify-green border-t-transparent" />
            </div>
          )}

          {themesError && (
            <p className="text-center text-red-400 py-10">{themesError}</p>
          )}

          {!themesLoading && !themesError && themes.length > 0 && (
            <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
              {themes.map((theme) => (
                <div
                  key={theme.theme_name}
                  className="rounded-lg border border-spotify-border bg-spotify-card p-4"
                  style={{ borderLeft: "3px solid #1db954" }}
                >
                  <h3 className="font-bold text-spotify-text leading-snug">
                    {theme.theme_name}
                  </h3>
                  <p className="mt-1 text-sm text-spotify-green">
                    {theme.count} reviews
                  </p>
                  <div className="mt-4 space-y-3">
                    {theme.top_quotes.map((quote, i) => (
                      <div
                        key={i}
                        className="rounded-md bg-spotify-panel p-3"
                      >
                        <p className="text-xs leading-relaxed text-spotify-text line-clamp-4">
                          &ldquo;{quote.text}&rdquo;
                        </p>
                        <p className="mt-2 text-xs text-spotify-muted">
                          {sourceLabel(quote.source)} · {quote.date}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
