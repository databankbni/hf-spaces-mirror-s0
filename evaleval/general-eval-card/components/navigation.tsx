"use client"

import { useEffect, useState } from "react"
import { Menu, Moon, Sun, X } from "lucide-react"
import { useTheme } from "next-themes"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"

export function Navigation() {
  const { theme, setTheme } = useTheme()
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)

  const navItems = [
    {
      href: "/",
      label: "Overview",
      isActive: pathname === "/",
    },
    {
      href: "/models",
      label: "Models",
      isActive:
        pathname === "/models" ||
        pathname?.startsWith("/models/") ||
        pathname?.startsWith("/developers/"),
    },
    {
      href: "/evals",
      label: "Evaluations",
      isActive: pathname === "/evals" || pathname?.startsWith("/evals/"),
    },
    {
      href: "/help",
      label: "Help",
      isActive: pathname === "/help" || pathname?.startsWith("/help/"),
    },
    {
      href: "/about",
      label: "About",
      isActive: pathname === "/about",
    },
    {
      href: "/feedback",
      label: "Feedback",
      isActive: pathname === "/feedback",
    },
  ]

  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  return (
    <>
      <header className="ec-topbar motion-academic-enter-soft">
        <div className="ec-topbar-inner">
          <Link href="/" className="ec-brand">
            <img
              src="https://evalevalai.com/assets/img/logo-square.png"
              alt=""
              className="ec-brand-mark-img h-7 w-7 shrink-0"
              width={28}
              height={28}
            />
            <span>Evaluation Cards</span>
            <span className="ec-brand-sub hidden lg:inline">Beta · EvalEval</span>
          </Link>

          <nav className="ec-nav-links hidden lg:flex">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(item.isActive && "active")}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3 lg:ml-0">
            <button
              type="button"
              className="ec-icon-btn"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label="Toggle theme"
              title="Toggle theme"
            >
              <Sun className="h-3.5 w-3.5 dark:hidden" />
              <Moon className="hidden h-3.5 w-3.5 dark:block" />
            </button>

            <button
              type="button"
              className="ec-icon-btn lg:hidden"
              onClick={() => setMobileOpen((current) => !current)}
              aria-expanded={mobileOpen}
              aria-label="Toggle navigation menu"
            >
              {mobileOpen ? <X className="h-3.5 w-3.5" /> : <Menu className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {mobileOpen && (
          <div className="lg:hidden border-t border-[color:var(--border-soft)] bg-[color:var(--bg)]">
            <div className="mx-auto w-full max-w-[96rem] px-4 py-3 sm:px-8">
              <nav className="grid gap-0.5">
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "block px-2 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors",
                      item.isActive
                        ? "text-[color:var(--fg)]"
                        : "text-[color:var(--fg-muted)] hover:text-[color:var(--fg)]"
                    )}
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
          </div>
        )}
      </header>
    </>
  )
}
