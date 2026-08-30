"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelsTopLeft } from "lucide-react";
import { cn } from "@/components/ui";

const navItems = [
  { href: "/", label: "拜访记录分析", match: (pathname: string) => pathname === "/" },
  { href: "/history", label: "分析历史", match: (pathname: string) => pathname.startsWith("/history") },
];

export function AppHeader() {
  const pathname = usePathname();

  return (
    <header className="border-b border-border bg-white">
      <div className="mx-auto flex min-h-16 max-w-5xl flex-col justify-center gap-3 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
        <Link href="/" className="group flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-900 transition-colors group-hover:border-slate-300">
            <PanelsTopLeft className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <p className="text-[17px] font-semibold leading-6 text-slate-950 transition-colors group-hover:text-slate-700">
            商机录入与分析助手
          </p>
        </Link>
        <nav className="inline-flex w-fit items-center rounded-full border border-slate-200/80 bg-slate-100/55 p-0.5 text-[14px] font-medium" aria-label="主导航">
          {navItems.map((item) => {
            const active = item.match(pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-full px-3.5 py-1.5 text-slate-500 transition-colors hover:text-slate-950",
                  active && "bg-white/90 text-slate-950",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
