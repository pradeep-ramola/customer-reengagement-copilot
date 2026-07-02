import type { Metadata } from "next";
import Link from "next/link";
import { Database, Send, Users } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Customer Re-Engagement AI Copilot",
  description: "Campaign scoring and draft review workbench"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-line bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-5">
            <Link href="/" className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-teal text-white">
                <Send size={18} />
              </span>
              <span className="hidden text-base font-semibold text-ink sm:inline">Re-Engagement Copilot</span>
            </Link>
            <nav className="flex min-w-0 items-center gap-1 text-sm text-slate-700 sm:gap-2">
              <Link className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-mist" href="/customers">
                <Users size={16} />
                Customers
              </Link>
              <Link className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-mist" href="/campaigns/new">
                <Database size={16} />
                Campaign
              </Link>
            </nav>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
