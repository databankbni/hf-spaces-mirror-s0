"use client";

import React from "react";
import { X, Phone, Mail, ArrowUpRight } from "lucide-react";

// Inline WhatsApp Icon SVG
const WhatsAppIcon = () => (
  <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
    <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/>
  </svg>
);

const LinkedinIcon = () => (
  <svg className="h-5 w-5 fill-current" viewBox="0 0 24 24">
    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
  </svg>
);

interface HandoffModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSendHandoff?: (data: any) => Promise<void>;
  tutorConfig?: any;
}

export const HandoffModal: React.FC<HandoffModalProps> = ({
  isOpen,
  onClose,
  tutorConfig,
}) => {
  if (!isOpen) return null;

  const contactTitle = tutorConfig?.frontend_ui_dictionary?.contact_modal?.title || "Get in Touch";
  const contactDesc = tutorConfig?.frontend_ui_dictionary?.contact_modal?.description || (tutorConfig?.name ? `Connect directly with ${tutorConfig.name} to discuss training, consulting, or inquiries.` : "Connect directly with Arun Yadav to discuss AI software systems, consulting, or project collaborations.");
  const contactChannels = tutorConfig?.contact || tutorConfig?.frontend_ui_dictionary?.contact_modal?.channels;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 cursor-pointer"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-3xl shiny-border-card bg-[var(--bg-surface)] p-6 sm:p-8 text-[var(--text-main)] shadow-2xl cursor-default"
      >
        <button
          onClick={onClose}
          className="absolute right-5 top-5 text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors p-1"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="space-y-6">
          <div>
            <h3 className="text-2xl font-extrabold text-[var(--text-main)] tracking-tight">
              {contactTitle}
            </h3>
            <p className="text-sm text-[var(--text-muted)] mt-1.5 leading-relaxed font-medium">
              {contactDesc}
            </p>
          </div>

          {/* Direct High-Impact Contact Channels */}
          <div className="space-y-3">
            {contactChannels ? (
              Array.isArray(contactChannels) ? (
                contactChannels.map((item: any, idx: number) => (
                  <a
                    key={idx}
                    href={item.url || item.value}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={onClose}
                    className="group flex items-center justify-between rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-4 hover:border-[var(--accent-green)] hover:shadow-md transition-all"
                  >
                    <div className="flex items-center gap-3.5">
                      <div className="rounded-xl bg-[var(--accent-green)]/10 p-2.5 text-[var(--accent-green)] shrink-0">
                        <Mail className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{item.label || item.id}</div>
                        <div className="font-mono text-sm font-bold text-[var(--text-main)] mt-0.5">{item.value || item.url}</div>
                      </div>
                    </div>
                    <ArrowUpRight className="h-4 w-4 text-[var(--text-dim)] group-hover:text-[var(--accent-green)] transition-colors" />
                  </a>
                ))
              ) : (
                Object.entries(contactChannels).map(([key, val]: [string, any], idx: number) => (
                  <a
                    key={idx}
                    href={val.startsWith("http") || val.startsWith("mailto:") || val.startsWith("tel:") ? val : `mailto:${val}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={onClose}
                    className="group flex items-center justify-between rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-4 hover:border-[var(--accent-green)] hover:shadow-md transition-all"
                  >
                    <div className="flex items-center gap-3.5">
                      <div className="rounded-xl bg-[var(--accent-green)]/10 p-2.5 text-[var(--accent-green)] shrink-0">
                        <Mail className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">{key}</div>
                        <div className="font-mono text-sm font-bold text-[var(--text-main)] mt-0.5">{val}</div>
                      </div>
                    </div>
                    <ArrowUpRight className="h-4 w-4 text-[var(--text-dim)] group-hover:text-[var(--accent-green)] transition-colors" />
                  </a>
                ))
              )
            ) : (
              <>
                {/* Phone / Call */}
                <a
                  href="tel:+918881109193"
                  onClick={onClose}
                  className="group flex items-center justify-between rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-4 hover:border-[var(--accent-green)] hover:shadow-md transition-all"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="rounded-xl bg-[var(--accent-green)]/10 p-2.5 text-[var(--accent-green)] shrink-0">
                      <Phone className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Phone / Call</div>
                      <div className="font-mono text-sm font-bold text-[var(--text-main)] mt-0.5">+91 8881109193</div>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-[var(--text-dim)] group-hover:text-[var(--accent-green)] transition-colors" />
                </a>

                {/* WhatsApp */}
                <a
                  href="https://wa.me/918881109193"
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={onClose}
                  className="group flex items-center justify-between rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-4 hover:border-[var(--accent-green)] hover:shadow-md transition-all"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="rounded-xl bg-[var(--accent-green)]/10 p-2.5 text-[var(--accent-green)] shrink-0">
                      <WhatsAppIcon />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">WhatsApp Direct</div>
                      <div className="font-mono text-sm font-bold text-[var(--text-main)] mt-0.5">+91 8881109193</div>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-[var(--text-dim)] group-hover:text-[var(--accent-green)] transition-colors" />
                </a>

                {/* Email */}
                <a
                  href="mailto:neural.arun.dev@gmail.com"
                  onClick={onClose}
                  className="group flex items-center justify-between rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-4 hover:border-[var(--accent-amber)] hover:shadow-md transition-all"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="rounded-xl bg-amber-500/10 p-2.5 text-amber-600 shrink-0">
                      <Mail className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Email Address</div>
                      <div className="font-mono text-sm font-bold text-[var(--text-main)] mt-0.5">neural.arun.dev@gmail.com</div>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-[var(--text-dim)] group-hover:text-[var(--accent-amber)] transition-colors" />
                </a>

                {/* LinkedIn */}
                <a
                  href="https://linkedin.com/in/neuralarun"
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={onClose}
                  className="group flex items-center justify-between rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-main)] p-4 hover:border-[var(--accent-teal)] hover:shadow-md transition-all"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="rounded-xl bg-sky-500/10 p-2.5 text-sky-600 shrink-0">
                      <LinkedinIcon />
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">LinkedIn Profile</div>
                      <div className="font-mono text-sm font-bold text-[var(--text-main)] mt-0.5">linkedin.com/in/neuralarun</div>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-[var(--text-dim)] group-hover:text-sky-600 transition-colors" />
                </a>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
