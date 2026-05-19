"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clsx } from "clsx";

import { clearStoredToken } from "@/lib/auth-store";
import { Wordmark } from "./wordmark";

const navItems = [
  { href: "/dashboard", label: "Overview" },
  { href: "/decisions", label: "Decisions" },
  { href: "/studio", label: "Studio" },
  { href: "/setup-agent", label: "Setup agent" },
  { href: "/tuning-agent", label: "Tuning agent" },
  { href: "/settings", label: "Settings" },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    clearStoredToken();
    router.push("/login");
  }

  return (
    <aside className="flex w-56 flex-col border-r border-ink-800 bg-ink-900">
      <div className="flex h-14 items-center px-5 border-b border-ink-800">
        <Link href="/dashboard" className="text-base">
          <Wordmark variant="logo" />
        </Link>
      </div>

      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const active =
              pathname === item.href || pathname?.startsWith(item.href + "/");
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={clsx(
                    "block rounded-md px-3 py-1.5 text-sm transition",
                    active
                      ? "bg-ink-800 text-ink-50"
                      : "text-ink-200 hover:bg-ink-800 hover:text-ink-50",
                  )}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-ink-800 px-3 py-3">
        <button
          onClick={logout}
          className="w-full rounded-md px-3 py-1.5 text-left text-xs text-ink-400 hover:bg-ink-800 hover:text-ink-200"
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
