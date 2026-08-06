"use client";

import React from "react";
import Image from "next/image";

interface ManifestoViewProps {
  tutorConfig?: any;
}

export const ManifestoView: React.FC<ManifestoViewProps> = ({ tutorConfig }) => {
  const tutorName = tutorConfig?.frontend_ui_dictionary?.about_view?.full_name || tutorConfig?.name || "Arun Yadav";
  const tutorTagline = tutorConfig?.frontend_ui_dictionary?.about_view?.tagline || tutorConfig?.role || "AI Systems Builder • Healthcare & Education";
  const tutorAvatar = tutorConfig?.client_metadata?.avatar_url || tutorConfig?.avatar || "/profile_photo.png";
  const bioParagraphs = tutorConfig?.frontend_ui_dictionary?.about_view?.bio_paragraphs || (tutorConfig?.about_text ? [tutorConfig.about_text] : null);
  const closingCallout = tutorConfig?.frontend_ui_dictionary?.about_view?.closing_callout || tutorConfig?.cta_text;

  return (
    <div className="h-full overflow-y-auto px-4 py-8 sm:px-12 pb-24 sm:pb-12 bg-[var(--bg-main)] text-[var(--text-main)]">
      <div className="mx-auto max-w-3xl space-y-6 animate-fade-slide">
        
        {/* Header Photo & Title */}
        <div className="shiny-header-box rounded-2xl p-6 bg-[var(--bg-card)] flex flex-col sm:flex-row items-center sm:items-start gap-6">
          <div className="relative h-28 w-28 sm:h-32 sm:w-32 overflow-hidden rounded-full border-4 border-[var(--accent-green)] shadow-xl shrink-0">
            <Image
              src={tutorAvatar}
              alt={tutorName}
              width={128}
              height={128}
              className="h-full w-full object-cover"
              priority
            />
          </div>

          <div className="space-y-2 text-center sm:text-left min-w-0 flex-1">
            <h1 className="font-heading text-3xl sm:text-4xl font-extrabold text-[var(--text-main)] tracking-tight">
              {tutorName}
            </h1>
            <p className="text-base sm:text-lg font-bold text-[var(--accent-green)]">
              {tutorTagline}
            </p>
          </div>
        </div>

        {/* Bio Paragraphs */}
        <div className="shiny-border-card rounded-2xl p-6 bg-[var(--bg-card)] space-y-5 text-sm sm:text-base text-[var(--text-muted)] font-medium leading-relaxed">
          {bioParagraphs ? (
            bioParagraphs.map((para: string, idx: number) => (
              <p key={idx}>{para}</p>
            ))
          ) : (
            <>
              <p>
                I am <strong className="text-[var(--text-main)] font-bold">Arun Yadav</strong>, an AI Systems Builder engineering trust, production-grade software. I specialize in designing systems that combine AI, robust backend architecture, and domain expertise to solve high-stakes problems in <strong className="text-[var(--accent-green)] font-bold">Healthcare and Education</strong>.
              </p>

              <p>
                Over the past few years, I’ve built complete, production-ready systems — from zero-hallucination RAG engines to clinical AI tutors and automated workflow pipelines. Some of my key highlighted projects include <strong className="text-[var(--text-main)] font-bold">ArunCore</strong> (a hybrid RAG engine combining ChromaDB vector search, BM25 keyword matching, and Cohere reranking), <strong className="text-[var(--text-main)] font-bold">NEET Medical Bot</strong> (an AI practice & diagnostic ecosystem for medical entrance exams with 10,000+ NCERT questions, spaced repetition, and solution breakdowns), <strong className="text-[var(--text-main)] font-bold">MedCoach</strong> (a reasoning AI tutor and diagnostic workflow assistant built with guardrails & execution traces), and <strong className="text-[var(--text-main)] font-bold">AI Note / Legal RAG</strong> (automated structured note generation and Indian legal document retrieval pipelines).
              </p>

              <p>
                My engineering approach is simple: I always understand the domain deeply and analyze user friction before writing a single line of code. In healthcare and education, AI must be verifiable, so I build systems with strict guardrails and human oversight. Most importantly, I focus on finishing and shipping clean, deployed software that delivers real business leverage.
              </p>
            </>
          )}

          <div className="pt-4 border-t border-[var(--border-subtle)]">
            <p className="text-sm sm:text-base font-semibold text-[var(--accent-green)]">
              {closingCallout ? closingCallout : "Looking for an AI Systems Architect to build custom software for your team or agency? Let’s talk! Feel free to chat with my AI Digital Twin here on this site, or click Consult Arun to connect directly."}
            </p>
          </div>
        </div>

      </div>
    </div>
  );
};
