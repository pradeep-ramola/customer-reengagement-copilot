"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Database, Gauge, MailCheck, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export default function HomePage() {
  const [message, setMessage] = useState<string>("");
  const [loading, setLoading] = useState(false);

  async function seedDemo() {
    setLoading(true);
    setMessage("");
    try {
      const result = await api.seedDemo();
      setMessage(`Demo dataset ready: ${result.demo_customers_total} customers.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Seed failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-8">
      <section className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-6 py-4">
          <Badge tone="teal">Mock AI mode</Badge>
          <div className="space-y-4">
            <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-ink md:text-5xl">
              Customer Re-Engagement AI Copilot
            </h1>
            <p className="max-w-2xl text-base leading-7 text-slate-600">
              Score customers by product fit, channel consent, recency, purchase behavior, and engagement, then review
              campaign-ready email and SMS drafts before mock sending.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link href="/campaigns/new">
                Create Campaign
                <ArrowRight size={16} />
              </Link>
            </Button>
            <Button variant="secondary" onClick={seedDemo} disabled={loading}>
              <Database size={16} />
              {loading ? "Seeding..." : "Seed Demo Data"}
            </Button>
          </div>
          {message ? <p className="text-sm text-slate-700">{message}</p> : null}
        </div>

        <div className="surface rounded-lg p-5">
          <div className="grid gap-4">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div>
                <p className="text-sm font-medium text-ink">Campaign preview</p>
                <p className="text-xs text-slate-500">Premium Noise-Canceling Headphones</p>
              </div>
              <Sparkles className="text-teal" size={20} />
            </div>
            {[
              ["Sarah Miller", "83.35", "Both Channels", "High Intent"],
              ["David Chen", "83.32", "SMS Only", "High Intent"],
              ["Maya Patel", "54.13", "Email Only", "Medium Intent"],
              ["Rahul Sharma", "51.57", "Email Only", "Medium Intent"]
            ].map(([name, score, channel, intent]) => (
              <div key={name} className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-md border border-line bg-white p-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{name}</span>
                    <Badge tone={intent === "High Intent" ? "teal" : "amber"}>{intent}</Badge>
                  </div>
                  <div className="mt-3 h-2 rounded-full bg-slate-100">
                    <div className="metric-strip h-2 rounded-full" style={{ width: `${score}%` }} />
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-lg font-semibold text-ink">{score}</p>
                  <p className="text-xs text-slate-500">{channel}</p>
                </div>
              </div>
            ))}
            <div className="grid grid-cols-3 gap-3 border-t border-line pt-3">
              <div className="rounded-md bg-mist p-3">
                <Gauge size={16} className="mb-2 text-cobalt" />
                <p className="text-xs text-slate-500">Scored</p>
                <p className="font-semibold">4</p>
              </div>
              <div className="rounded-md bg-mist p-3">
                <MailCheck size={16} className="mb-2 text-teal" />
                <p className="text-xs text-slate-500">Drafts</p>
                <p className="font-semibold">4</p>
              </div>
              <div className="rounded-md bg-mist p-3">
                <Database size={16} className="mb-2 text-amber" />
                <p className="text-xs text-slate-500">Mode</p>
                <p className="font-semibold">Mock</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
