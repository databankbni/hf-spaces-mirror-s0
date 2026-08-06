"use client";

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Image from "next/image";
import { Message } from "../lib/types";
import { Send, Copy, Check, ChevronDown, ChevronRight, Sparkles, Terminal, PhoneCall, ArrowRight, Activity, Cpu, Volume2, Square, Loader2, Mic, MicOff, RotateCcw, Briefcase, HeartPulse, Layers, Scale } from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || (typeof window !== "undefined" && window.location.hostname !== "localhost" ? "https://neural-arun-aruncore.hf.space" : "http://localhost:8000");

interface ChatPanelProps {
  messages: Message[];
  onSendMessage: (text: string) => void;
  isStreaming: boolean;
  onResetSession: () => void;
  activePrompt: string;
  setActivePrompt: (prompt: string) => void;
  openHandoffModal: () => void;
  isAdminMode?: boolean;
  onSendAdminMessage?: (text: string) => void;
  tutorConfig?: any;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  onSendMessage,
  isStreaming,
  onResetSession,
  activePrompt,
  setActivePrompt,
  openHandoffModal,
  isAdminMode,
  onSendAdminMessage,
  tutorConfig,
}) => {
  const [inputText, setInputText] = useState("");
  const [adminInputText, setAdminInputText] = useState("");
  const [expandedThoughts, setExpandedThoughts] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null);
  const [isLoadingAudio, setIsLoadingAudio] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);

  const tutorName = tutorConfig?.frontend_ui_dictionary?.chat_panel?.hero_card?.assistant_title || tutorConfig?.title || "Arun's AI Assistant";
  const tutorRole = tutorConfig?.frontend_ui_dictionary?.chat_panel?.hero_card?.role_subtitle || tutorConfig?.subtitle || tutorConfig?.role || "AI Systems Architect • Healthcare & Education";
  const tutorAvatar = tutorConfig?.client_metadata?.avatar_url || tutorConfig?.avatar || "/profile_photo.png";
  const tutorWelcome = tutorConfig?.frontend_ui_dictionary?.chat_panel?.hero_card?.welcome_paragraph || tutorConfig?.welcome_message || "Hi! I'm Arun's AI Assistant. I can walk you through his production systems, architecture decisions, healthcare & education AI builds, or help you get in direct touch with him. Plus, the real Arun monitors this channel live and can jump in to converse with you directly!";
  const tutorCta = tutorConfig?.frontend_ui_dictionary?.chat_panel?.hero_card?.cta_button_text || tutorConfig?.cta_text || "Consult Arun";
  const inputPlaceholder = tutorConfig?.frontend_ui_dictionary?.chat_panel?.input_bar?.placeholder || (tutorConfig?.name ? `Ask ${tutorConfig.name}'s AI Assistant...` : "Ask Arun's AI Assistant...");
  const customQuestions = tutorConfig?.frontend_ui_dictionary?.chat_panel?.suggested_questions_section?.chips?.map((c: any) => c.query) || tutorConfig?.suggested_questions;

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recognitionRef = useRef<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Focus text input on initial page load / mount
  useEffect(() => {
    const timer = setTimeout(() => {
      textareaRef.current?.focus();
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  // Re-focus text input whenever AI finishes streaming a response
  useEffect(() => {
    if (!isStreaming) {
      textareaRef.current?.focus();
    }
  }, [isStreaming]);

  useEffect(() => {
    if (activePrompt) {
      setInputText(activePrompt);
      setActivePrompt("");
      textareaRef.current?.focus();
    }
  }, [activePrompt, setActivePrompt]);

  // Clean up audio & speech recognition on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {}
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!inputText.trim() || isStreaming) return;
    if (isListening && recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {}
      setIsListening(false);
    }
    onSendMessage(inputText.trim());
    setInputText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.focus();
    }
  };

  const copyToClipboard = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const baseTextRef = useRef<string>("");

  // Speech-To-Text (STT) Microphone Handler
  const handleToggleListening = () => {
    if (typeof window === "undefined") return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in your browser. Please try Chrome or Edge.");
      return;
    }

    if (isListening) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {}
      }
      setIsListening(false);
      return;
    }

    try {
      baseTextRef.current = inputText.trim();
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onresult = (event: any) => {
        let currentSpeech = "";
        for (let i = 0; i < event.results.length; i++) {
          currentSpeech += event.results[i][0].transcript;
        }

        const base = baseTextRef.current;
        const newText = base ? `${base} ${currentSpeech.trim()}` : currentSpeech.trim();
        setInputText(newText);

        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
          textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
        }
      };

      recognition.onerror = (event: any) => {
        if (event.error !== "no-speech" && event.error !== "aborted") {
          console.warn("Speech recognition notice:", event.error);
        }
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
      setIsListening(true);
    } catch (e) {
      console.error("Failed to start speech recognition:", e);
      setIsListening(false);
    }
  };

  // Text-To-Speech (TTS) Voice Synthesis
  const handleToggleSpeech = async (msgId: string, text: string) => {
    if (playingMessageId === msgId) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
      setPlayingMessageId(null);
      setIsLoadingAudio(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    setIsLoadingAudio(msgId);

    const cleanText = text
      .replace(/[*_#`~\[\]()]/g, " ")
      .replace(/https?:\/\/\S+/g, "")
      .replace(/\n+/g, ". ")
      .trim();

    if (!cleanText) {
      setIsLoadingAudio(null);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: cleanText, voice: "alloy" }),
      });

      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);

        const audio = new Audio(url);
        audioRef.current = audio;

        audio.onended = () => {
          setPlayingMessageId(null);
          setIsLoadingAudio(null);
        };
        audio.onerror = () => {
          fallbackBrowserSpeech(msgId, cleanText);
        };

        setIsLoadingAudio(null);
        setPlayingMessageId(msgId);
        await audio.play();
        return;
      }
    } catch (e) {
      console.warn("Neural TTS endpoint fallback:", e);
    }

    fallbackBrowserSpeech(msgId, cleanText);
  };

  const fallbackBrowserSpeech = (msgId: string, cleanText: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setIsLoadingAudio(null);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 0.95;
    utterance.pitch = 1.05;

    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(
      (v) =>
        v.name.includes("Google") ||
        v.name.includes("Natural") ||
        v.name.includes("Samantha") ||
        v.name.includes("Daniel") ||
        v.lang.startsWith("en")
    );
    if (naturalVoice) utterance.voice = naturalVoice;

    utterance.onend = () => {
      setPlayingMessageId(null);
      setIsLoadingAudio(null);
    };
    utterance.onerror = () => {
      setPlayingMessageId(null);
      setIsLoadingAudio(null);
    };

    setIsLoadingAudio(null);
    setPlayingMessageId(msgId);
    window.speechSynthesis.speak(utterance);
  };

  const starterPrompts = [
    {
      title: "Healthcare Systems & Automation",
      query: "How can your AI systems automate clinical workflows and reduce operational costs?",
    },
    {
      title: "Zero-Hallucination RAG Architecture",
      query: "How do you build zero-hallucination RAG engines for trusted knowledge search?",
    },
    {
      title: "Recent Work & Live Repositories",
      query: "What has Arun been working on recently? Fetch his latest GitHub activity and commits!",
    },
    {
      title: "Consulting & Project Collaboration",
      query: "How can our team hire or consult with Arun to build custom AI software?",
    },
  ];

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-[var(--bg-main)]">
      {/* 1. Main Scrollable Content (Landing Card + Suggested Questions or Messages) */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 pb-44 lg:pb-32">
        {messages.length === 0 ? (
          /* Landing Hero Card + Suggested Questions */
          <div className="mx-auto max-w-4xl w-full flex flex-col gap-4 sm:gap-5 animate-fade-slide">
            
            {/* AI Twin Card (Placed immediately below header) */}
            {/* Header Identity Card */}
            <div className="shiny-border-card rounded-2xl sm:rounded-3xl bg-[var(--bg-surface)] p-4 sm:p-5 backdrop-blur-md shadow-xs space-y-3 shrink-0">
              <div className="flex flex-row items-center justify-between gap-3">
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="relative h-13 w-13 sm:h-16 sm:w-16 overflow-hidden rounded-full border-2 border-[var(--accent-green)] bg-slate-800 shrink-0 shadow-md">
                    <Image
                      src={tutorAvatar}
                      alt={tutorName}
                      width={64}
                      height={64}
                      className="h-full w-full object-cover"
                      priority
                    />
                  </div>

                  <div className="space-y-0.5 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h1 className="font-heading text-base sm:text-xl font-extrabold text-[var(--text-main)] tracking-tight">
                        {tutorName}
                      </h1>
                      <span className="rounded-full border border-[var(--accent-green)] bg-[var(--accent-green)]/10 px-2 py-0.5 font-mono text-[10px] sm:text-[11px] font-bold text-[var(--accent-green)] flex items-center gap-1 shadow-xs shrink-0">
                        <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent-green)] animate-pulse" />
                        <span>Online</span>
                      </span>
                    </div>

                    <p className="text-xs sm:text-sm font-bold text-[var(--accent-green)] leading-tight truncate">
                      {tutorRole}
                    </p>
                  </div>
                </div>

                <button
                  onClick={openHandoffModal}
                  className="flex items-center justify-center gap-1.5 rounded-xl bg-[var(--accent-green)] hover:bg-[var(--accent-green-hover)] px-3.5 py-2 text-xs sm:text-sm font-bold text-white shadow-sm transition-all shrink-0 active:scale-95"
                >
                  <Briefcase className="h-4 w-4" />
                  <span className="hidden sm:inline">{tutorCta}</span>
                  <span className="sm:hidden">Consult</span>
                </button>
              </div>

              <div className="border-t border-[var(--border-subtle)] pt-2.5">
                <p className="text-xs sm:text-sm text-[var(--text-muted)] font-medium leading-normal">
                  {tutorWelcome}
                </p>
              </div>
            </div>

            {/* Suggested Questions Section */}
            <div className="space-y-2 shrink-0">
              <div className="flex items-center justify-between px-1">
                <span className="text-xs font-bold uppercase tracking-wider text-[var(--text-dim)] flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5 text-[var(--accent-green)]" />
                  <span>Suggested Questions</span>
                </span>
              </div>

              {/* ChatGPT Style Chips Grid */}
              <div className="grid grid-cols-2 gap-2.5">
                {(customQuestions
                  ? customQuestions.map((q: string, idx: number) => ({
                      icon: idx === 0 ? <HeartPulse className="h-4 w-4 text-rose-500 shrink-0" /> : idx === 1 ? <Layers className="h-4 w-4 text-amber-500 shrink-0" /> : idx === 2 ? <Scale className="h-4 w-4 text-indigo-500 shrink-0" /> : <Briefcase className="h-4 w-4 text-emerald-500 shrink-0" />,
                      badgeClass: idx === 0 ? "badge-coral" : idx === 1 ? "badge-amber" : idx === 2 ? "badge-indigo" : "badge-emerald",
                      label: q.length > 32 ? q.substring(0, 30) + "..." : q,
                      query: q,
                    }))
                  : [
                      {
                        icon: <HeartPulse className="h-4 w-4 text-rose-500 shrink-0" />,
                        badgeClass: "badge-coral",
                        label: "Healthcare AI",
                        query: starterPrompts[0].query,
                      },
                      {
                        icon: <Layers className="h-4 w-4 text-amber-500 shrink-0" />,
                        badgeClass: "badge-amber",
                        label: "Zero-Hallucination RAG",
                        query: starterPrompts[1].query,
                      },
                      {
                        icon: <Scale className="h-4 w-4 text-indigo-500 shrink-0" />,
                        badgeClass: "badge-indigo",
                        label: "Legal AI",
                        query: starterPrompts[2].query,
                      },
                      {
                        icon: <Briefcase className="h-4 w-4 text-emerald-500 shrink-0" />,
                        badgeClass: "badge-emerald",
                        label: "Consult with Arun",
                        query: starterPrompts[3].query,
                      },
                    ]
                ).map((item: any, idx: number) => (
                  <button
                    key={idx}
                    onClick={() => onSendMessage(item.query)}
                    className={`text-left flex items-center gap-2.5 rounded-2xl ${item.badgeClass || 'shiny-border-card bg-[var(--bg-surface)]'} px-3.5 py-3 transition-all hover:scale-[1.02] active:scale-[0.98] shadow-xs cursor-pointer`}
                  >
                    {item.icon}
                    <span className="text-xs sm:text-sm font-bold truncate flex-1">
                      {item.label}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 opacity-60 group-hover:opacity-100 transition-opacity shrink-0" />
                  </button>
                ))}
              </div>
            </div>

          </div>
        ) : (
          /* Active Conversation View Messages */
          <div className="mx-auto max-w-4xl space-y-5">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col gap-1.5 ${
                  msg.sender === "user" ? "items-end" : "items-start"
                }`}
              >
                <div
                  className={`max-w-[95%] sm:max-w-[88%] rounded-2xl px-5 py-4 text-sm sm:text-base ${
                    msg.sender === "user"
                      ? "bg-[var(--bg-surface-hover)] text-[var(--text-main)] font-medium border border-[var(--border-subtle)] shadow-md"
                      : msg.sender === "human_arun"
                      ? "border-2 border-emerald-500/60 bg-emerald-950/20 text-[var(--text-main)] shadow-xl"
                      : "border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-main)] shadow-lg"
                  }`}
                >
                  {/* Sender & Real-Time Stream Status Bar */}
                  <div className="flex items-center justify-between gap-4 mb-2.5 pb-1.5 border-b border-[var(--border-subtle)] text-xs text-[var(--text-muted)]">
                    <span className="font-semibold text-[var(--accent-green)] flex items-center gap-2">
                      {msg.sender === "user" ? (
                        "You"
                      ) : msg.sender === "human_arun" ? (
                        <span className="flex items-center gap-2 text-emerald-400 font-extrabold">
                          <span>👨‍💻 Arun Yadav</span>
                          <span className="rounded-full border border-emerald-500/50 bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] font-extrabold text-emerald-400 animate-pulse">
                            VERIFIED HUMAN 🟢
                          </span>
                        </span>
                      ) : (
                        <>
                          <span>Arun's AI Assistant</span>
                          {msg.isStreaming && (
                            <span className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-600 animate-pulse">
                              <Activity className="h-3 w-3 animate-spin" />
                              <span>STREAMING RESPONSE BUFFER</span>
                            </span>
                          )}
                        </>
                      )}
                    </span>
                    <span className="font-mono text-[11px] text-[var(--text-dim)]">
                      {msg.timestamp}
                    </span>
                  </div>

                  {/* Reasoning steps trace */}
                  {msg.sender === "twin" && msg.thoughts && msg.thoughts.length > 0 && (
                    <div className="mb-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-3 space-y-2">
                      <button
                        onClick={() =>
                          setExpandedThoughts((prev) => ({
                            ...prev,
                            [msg.id]: !prev[msg.id],
                          }))
                        }
                        className="flex items-center gap-2 font-mono text-xs text-[var(--accent-amber)] hover:text-[var(--accent-green)] transition-colors w-full"
                      >
                        <Cpu className="h-3.5 w-3.5 text-amber-500 animate-pulse" />
                        <span className="font-bold">Engine Execution Trace ({msg.thoughts.length} steps)</span>
                        {expandedThoughts[msg.id] ? (
                          <ChevronDown className="h-3.5 w-3.5 ml-auto" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 ml-auto" />
                        )}
                      </button>

                      {(expandedThoughts[msg.id] || msg.isStreaming) && (
                        <div className="space-y-1 font-mono text-xs text-[var(--text-muted)] border-t border-[var(--border-subtle)] pt-2">
                          {msg.thoughts.map((th, idx) => (
                            <div key={idx} className="flex items-center gap-2">
                              <span className="text-[var(--accent-amber)] font-bold">[{idx + 1}]</span>
                              <span>{th}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Real-time Streaming Content */}
                  {msg.sender === "user" ? (
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                  ) : (
                    <div className="prose-professional relative">
                      {msg.isStreaming && !msg.text ? (
                        <div className="py-2 text-xs font-mono text-[var(--accent-green)] flex items-center gap-2.5">
                          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-ping" />
                          <span>Retrieving vector embeddings & initializing token buffer...</span>
                        </div>
                      ) : (
                        <>
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({ node, ...props }) => (
                                <a
                                  {...props}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-emerald-600 dark:text-emerald-400 font-bold underline hover:opacity-80 transition-opacity"
                                />
                              ),
                            }}
                          >
                            {msg.text}
                          </ReactMarkdown>
                          {msg.isStreaming && (
                            <span className="inline-block h-4 w-2 bg-[var(--accent-green)] animate-pulse ml-1 align-middle rounded-xs" />
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {/* Action Bar: High Quality Speech & Copy Button */}
                  {msg.sender === "twin" && msg.text && !msg.isStreaming && (
                    <div className="mt-3 flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] pt-2">
                      <button
                        onClick={() => handleToggleSpeech(msg.id, msg.text)}
                        disabled={isLoadingAudio === msg.id}
                        className={`flex items-center gap-1.5 text-xs font-bold transition-colors ${
                          playingMessageId === msg.id
                            ? "text-rose-500 animate-pulse"
                            : "text-[var(--accent-green)] hover:opacity-80"
                        }`}
                        title={playingMessageId === msg.id ? "Stop voice playback" : "Listen in HD neural voice"}
                      >
                        {isLoadingAudio === msg.id ? (
                          <>
                            <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--accent-green)]" />
                            <span>Loading Voice...</span>
                          </>
                        ) : playingMessageId === msg.id ? (
                          <>
                            <Square className="h-3.5 w-3.5 fill-current text-rose-500" />
                            <span>Stop Voice</span>
                          </>
                        ) : (
                          <>
                            <Volume2 className="h-3.5 w-3.5" />
                            <span>Listen (HD Voice)</span>
                          </>
                        )}
                      </button>

                      <span className="text-[var(--border-subtle)]">|</span>

                      <button
                        onClick={() => copyToClipboard(msg.id, msg.text)}
                        className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors font-medium"
                        title="Copy Response"
                      >
                        {copiedId === msg.id ? (
                          <>
                            <Check className="h-3.5 w-3.5 text-emerald-500" />
                            <span className="text-emerald-500 font-semibold">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="h-3.5 w-3.5" />
                            <span>Copy Text</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* 2. Permanently Fixed Bottom Chat Input Bar (Docked above bottom navigation on mobile, aligned to main panel on desktop) */}
      <div className="fixed bottom-[54px] lg:bottom-0 left-0 lg:left-80 right-0 z-40 bg-[var(--bg-main)]/95 backdrop-blur-xl border-t border-[var(--border-subtle)] px-3 py-2.5 sm:px-6 sm:py-3 shadow-2xl transition-all duration-200">
        <div className="mx-auto max-w-4xl w-full space-y-1.5">
          {isListening && (
            <div className="flex items-center justify-center gap-2 rounded-xl bg-rose-500/10 border border-rose-500/30 py-1 text-xs font-mono font-bold text-rose-600 animate-pulse">
              <span className="h-2 w-2 rounded-full bg-rose-500 animate-ping" />
              <span>Listening to your voice... Speak now!</span>
            </div>
          )}

          <div className="input-box-container relative flex items-center px-4 py-2 min-h-[56px] rounded-2xl border border-[var(--input-border)] bg-[var(--input-bg)] shadow-xs">
            <textarea
              ref={textareaRef}
              value={inputText}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={isListening ? "Listening..." : "Ask Arun's AI Assistant..."}
              rows={1}
              className="flex-1 resize-none bg-transparent py-1 text-xs sm:text-base text-[var(--text-main)] placeholder-[var(--text-dim)] font-medium focus:outline-none max-h-24 min-h-[36px]"
            />

            {/* Microphone STT Button */}
            <button
              onClick={handleToggleListening}
              className={`ml-1.5 flex h-9 w-9 items-center justify-center rounded-xl font-bold transition-all shadow-xs shrink-0 touch-manipulation ${
                isListening
                  ? "bg-rose-500 text-white animate-pulse"
                  : "bg-[var(--bg-surface-hover)] border border-[var(--border-subtle)] text-[var(--text-main)] hover:border-emerald-500"
              }`}
              title={isListening ? "Stop listening" : "Click to speak (Voice to text)"}
            >
              {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4 text-[var(--text-dim)]" />}
            </button>

            {/* Send Message Button */}
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || isStreaming}
              className="ml-1.5 flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition-all active:scale-95 disabled:opacity-30 shadow-xs shrink-0 touch-manipulation"
              title="Send Message"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>

          {messages.length > 0 && (
            <div className="flex items-center justify-between text-[11px] text-[var(--text-dim)] font-medium px-1">
              <span>Press Enter to send or use 🎙️ Mic</span>
              <button onClick={onResetSession} className="hover:text-[var(--accent-amber)] transition-colors">
                Clear conversation
              </button>
            </div>
          )}

          {isAdminMode && (
            <div className="mt-2 border-t-2 border-emerald-500/60 bg-emerald-950/30 p-2 sm:p-2.5 shrink-0 rounded-2xl shadow-xl space-y-1.5">
              <div className="mx-auto max-w-4xl flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                <div className="flex items-center gap-2 flex-1 rounded-xl border-2 border-emerald-500/50 bg-[var(--bg-surface)] px-3.5 py-1.5 shadow-md">
                  <span className="font-mono text-xs font-extrabold text-emerald-400 shrink-0">👨‍💻 REAL ARUN:</span>
                  <input
                    type="text"
                    value={adminInputText}
                    onChange={(e) => setAdminInputText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && adminInputText.trim()) {
                        onSendAdminMessage?.(adminInputText);
                        setAdminInputText("");
                      }
                    }}
                    placeholder="Type live response or command (/answer, /release)..."
                    className="flex-1 bg-transparent py-1.5 text-xs sm:text-sm text-[var(--text-main)] placeholder-[var(--text-dim)] font-semibold focus:outline-none"
                  />
                </div>
                <button
                  onClick={() => {
                    if (adminInputText.trim()) {
                      onSendAdminMessage?.(adminInputText);
                      setAdminInputText("");
                    }
                  }}
                  className="rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 text-xs sm:text-sm shadow-lg transition-all active:scale-95 shrink-0 flex items-center justify-center gap-2"
                >
                  <span>SEND AS REAL ARUN</span>
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="mx-auto max-w-4xl flex items-center justify-end gap-2 text-[11px] font-mono">
                <button
                  onClick={() => onSendAdminMessage?.("/answer")}
                  className="rounded-lg border border-emerald-500/50 bg-emerald-900/40 hover:bg-emerald-800/60 px-2 py-0.5 text-emerald-300 font-bold transition-all flex items-center gap-1 shadow-sm active:scale-95"
                  title="Trigger AI Twin to answer reading the 3-way transcript"
                >
                  <Cpu className="h-3 w-3 text-emerald-400" />
                  <span>🤖 Trigger AI Answer (/answer)</span>
                </button>

                <button
                  onClick={() => onSendAdminMessage?.("/release")}
                  className="rounded-lg border border-amber-500/50 bg-amber-950/40 hover:bg-amber-900/60 px-2 py-0.5 text-amber-300 font-bold transition-all flex items-center gap-1 shadow-sm active:scale-95"
                  title="Hand control back to AI Twin auto-responses"
                >
                  <RotateCcw className="h-3 w-3 text-amber-400" />
                  <span>🔄 Hand Back to AI (/release)</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
