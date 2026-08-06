"use client";

import React from "react";
import { Cpu, Database, GitBranch, ArrowDown, ArrowRight, ShieldAlert, CheckCircle, Zap, HardDrive, Smartphone } from "lucide-react";

export const ArchitectureView: React.FC = () => {
  const steps = [
    {
      title: "1. User Query & Intent Router",
      desc: "FastAPI receives query and classifies intent: Static Identity, Live GitHub API, or RAG Search.",
      icon: <GitBranch className="h-5 w-5 text-amber-400" />,
    },
    {
      title: "2. Hybrid Search (ChromaDB + BM25)",
      desc: "Queries ChromaDB vector DB (semantic) & BM25 (exact keyword match) to pull top 20 chunks.",
      icon: <Database className="h-5 w-5 text-cyan-400" />,
    },
    {
      title: "3. Cohere Cross-Encoder Reranker",
      desc: "Re-ranks top 20 candidate chunks with Cohere English V3 for strict ground-truth relevance.",
      icon: <Zap className="h-5 w-5 text-purple-400" />,
    },
    {
      title: "4. Stateful Rolling Memory",
      desc: "Tracks last 8 turns and compresses old context using gpt-4o-mini every 4 turns to avoid bloat.",
      icon: <HardDrive className="h-5 w-5 text-emerald-400" />,
    },
    {
      title: "5. Telegram Phone Handoff",
      desc: "Triggers notify_arun tool when a lead or contact request arrives, alerting Arun's phone instantly.",
      icon: <Smartphone className="h-5 w-5 text-rose-400" />,
    },
  ];

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 sm:p-8 max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="rounded-3xl border border-amber-500/30 bg-gradient-to-br from-slate-900 to-slate-950 p-6 sm:p-8 shadow-2xl">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-bold text-amber-400 mb-3">
          <Cpu className="h-4 w-4" />
          ArunCore Systems Design
        </div>
        <h1 className="font-heading text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
          Zero-Hallucination Hybrid RAG & Agent Architecture
        </h1>
        <p className="mt-2 text-xs sm:text-sm text-slate-300 max-w-3xl leading-relaxed">
          ArunCore combines a stateful rolling memory, hybrid semantic + keyword retrieval, Cohere re-ranking, and real-time phone alerts to ensure complete accuracy.
        </p>
      </div>

      {/* Source of Truth Priority */}
      <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-5 space-y-3">
        <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-2">
          <ShieldAlert className="h-4 w-4" />
          Absolute Conflict Resolution Hierarchy
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3">
            <span className="font-mono text-emerald-400 font-bold">1. Live API Data (Highest)</span>
            <p className="text-[11px] text-slate-300 mt-1">Wins for real-time repository commits & live status.</p>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3">
            <span className="font-mono text-amber-400 font-bold">2. Static Identity Profile</span>
            <p className="text-[11px] text-slate-300 mt-1">Wins for core philosophy, operating rules, & identity.</p>
          </div>
          <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3">
            <span className="font-mono text-cyan-400 font-bold">3. Vector Memory (ChromaDB)</span>
            <p className="text-[11px] text-slate-300 mt-1">Used for deep historical project details & notes.</p>
          </div>
        </div>
      </div>

      {/* Pipeline Breakdown */}
      <div className="space-y-4">
        <h2 className="font-heading text-base font-bold text-white uppercase tracking-wide">
          Interactive Pipeline Breakdown
        </h2>

        <div className="space-y-3">
          {steps.map((step, idx) => (
            <div
              key={idx}
              className="flex items-start gap-4 rounded-2xl border border-white/10 bg-slate-900/70 p-4 transition-all hover:border-amber-500/30 hover:bg-slate-900"
            >
              <div className="rounded-xl border border-white/10 bg-slate-950 p-3 shrink-0">
                {step.icon}
              </div>
              <div>
                <h3 className="font-heading text-sm font-bold text-white">
                  {step.title}
                </h3>
                <p className="mt-1 text-xs text-slate-300 leading-relaxed">
                  {step.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
