"use client";

import React from "react";
import { ActiveTab } from "../lib/types";
import { Bot, FolderGit2, User, PhoneCall } from "lucide-react";

interface MobileBottomNavProps {
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;
  openHandoffModal: () => void;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab,
  setActiveTab,
  openHandoffModal,
}) => {
  const tabs = [
    {
      id: "chat" as ActiveTab,
      label: "AI Assistant",
      icon: <Bot className="h-5 w-5" />,
    },
    {
      id: "projects" as ActiveTab,
      label: "Projects",
      icon: <FolderGit2 className="h-5 w-5" />,
    },
    {
      id: "manifesto" as ActiveTab,
      label: "About",
      icon: <User className="h-5 w-5" />,
    },
  ];

  return (
    <div className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-[var(--bg-sidebar)]/95 backdrop-blur-xl border-t-2 border-[var(--border-accent)] px-2 py-1.5 shadow-2xl transition-colors duration-200">
      <div className="flex items-center justify-around max-w-md mx-auto">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex flex-col items-center justify-center py-1 px-3 rounded-xl transition-all touch-manipulation min-w-[64px] ${
                isActive
                  ? "bg-[var(--accent-green)]/20 text-[var(--accent-green)] font-extrabold scale-105 border border-[var(--border-accent)]/40"
                  : "text-[var(--text-dim)] hover:text-[var(--text-main)] font-medium"
              }`}
            >
              <div className={isActive ? "text-[var(--accent-green)]" : ""}>
                {tab.icon}
              </div>
              <span className="text-[10px] tracking-tight leading-tight mt-0.5 font-bold">
                {tab.label}
              </span>
            </button>
          );
        })}

        {/* Contact Handoff Trigger Tab */}
        <button
          onClick={openHandoffModal}
          className="flex flex-col items-center justify-center py-1 px-3 rounded-xl text-[var(--accent-green)] hover:opacity-90 font-bold transition-all touch-manipulation min-w-[64px]"
        >
          <div className="p-1 rounded-lg bg-[var(--accent-green)] text-white shadow-xs">
            <PhoneCall className="h-4 w-4" />
          </div>
          <span className="text-[10px] tracking-tight leading-tight mt-0.5 font-extrabold">
            Contact
          </span>
        </button>
      </div>
    </div>
  );
};
