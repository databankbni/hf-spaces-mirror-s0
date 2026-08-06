"use client";

import React, { useState } from "react";
import { Activity, Database, Cpu, Send, ShieldCheck, Copy, Check, MessageCircle, Zap, HardDrive, Terminal } from "lucide-react";

interface TelemetryPanelProps {
  sessionId: string;
  turnCount: number;
  openHandoffModal: () => void;
  backendOnline: boolean;
}

export const TelemetryPanel: React.FC<TelemetryPanelProps> = ({
  sessionId,
  turnCount,
  openHandoffModal,
  backendOnline,
}) => {
  const [copiedSession, setCopiedSession] = useState(false);

  const copySessionId = () => {
    navigator.clipboard.writeText(sessionId);
    setCopiedSession(true);
    setTimeout(() => setCopiedSession(false), 2000);
  };

  return (
    <aside className="flex flex-col gap-4 overflow-y-auto p-4 text-slate-300">
      {/* Session Telemetry Header */}
      <div className="rounded-2xl border border-amber-500/20 bg-slate-900/80 p-4 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-amber-400 animate-pulse" />
            <h3 className="text-xs font-bold tracking-wide text-white uppercase">
              Engine Telemetry
            </h3>
          </div>
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
            backendOnline ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
          }`}>
            {backendOnline ? "CONNECTED" : "OFFLINE"}
          </span>
        </div>

        {/* Session Meta Specs */}
        <div className="mt-3.5 space-y-2.5 font-mono text-xs">
          <div className="flex items-center justify-between rounded-lg bg-slate-950 p-2 border border-white/5">
            <span className="text-slate-400">Session ID:</span>
            <div className="flex items-center gap-1 text-slate-200">
              <span className="truncate max-w-[110px]">{sessionId}</span>
              <button
                onClick={copySessionId}
                className="text-slate-400 hover:text-amber-400 transition-colors"
                title="Copy Session ID"
              >
                {copiedSession ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg bg-slate-950 p-2 border border-white/5">
            <span className="text-slate-400">Conversation Turns:</span>
            <span className="font-semibold text-amber-400">{turnCount} / 8</span>
          </div>

          <div className="flex items-center justify-between rounded-lg bg-slate-950 p-2 border border-white/5">
            <span className="text-slate-400">Memory Compression:</span>
            <span className="text-emerald-400 font-semibold">Active (gpt-4o-mini)</span>
          </div>
        </div>
      </div>

      {/* System Stack Architecture Badges */}
      <div className="rounded-2xl border border-white/5 bg-slate-900/60 p-4 space-y-3">
        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5 text-amber-400" />
          ArunCore Pipeline Stack
        </h4>

        <div className="space-y-2 text-xs">
          <div className="flex items-start gap-2.5 rounded-xl bg-slate-950/80 p-2.5 border border-white/5">
            <Database className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-slate-100">Hybrid Retrieval</div>
              <div className="text-[11px] text-slate-400">ChromaDB Semantic Vector + BM25 Lexical Keyword Match</div>
            </div>
          </div>

          <div className="flex items-start gap-2.5 rounded-xl bg-slate-950/80 p-2.5 border border-white/5">
            <Zap className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-slate-100">Cohere Reranker V3</div>
              <div className="text-[11px] text-slate-400">Cross-Encoder contextual re-ranking of top 20 candidate chunks</div>
            </div>
          </div>

          <div className="flex items-start gap-2.5 rounded-xl bg-slate-950/80 p-2.5 border border-white/5">
            <MessageCircle className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-slate-100">Telegram Handoff</div>
              <div className="text-[11px] text-slate-400">Direct lead alert escalation directly to Arun's personal device</div>
            </div>
          </div>
        </div>
      </div>

      {/* Lead Handoff Banner */}
      <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/10 to-slate-900 p-4 text-center">
        <h4 className="text-sm font-bold text-white">Want to connect with Arun?</h4>
        <p className="mt-1 text-xs text-slate-300 leading-relaxed">
          Drop your message and Arun's Digital Twin will alert him on Telegram instantly.
        </p>

        <button
          onClick={openHandoffModal}
          className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 px-4 py-2 text-xs font-bold text-black shadow-md transition-all hover:scale-[1.02] active:scale-95"
        >
          <Send className="h-3.5 w-3.5" />
          <span>Send Message to Phone</span>
        </button>
      </div>
    </aside>
  );
};
