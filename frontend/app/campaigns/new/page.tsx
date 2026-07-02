"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Play } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export default function NewCampaignPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    name: "Headphones Re-Engagement",
    product_name: "Premium Noise-Canceling Headphones",
    product_description: "Over-ear wireless headphones with adaptive noise cancellation and premium comfort.",
    product_category: "Audio",
    launch_offer: "15% off during launch week"
  });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await api.createCampaign(form);
      router.push(`/campaigns/${response.campaign_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Campaign failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-5 py-7">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink">Create Campaign</h1>
        <p className="text-sm text-slate-500">Product launch details</p>
      </div>

      <form onSubmit={submit} className="surface rounded-lg p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Name
            <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Product Name
            <Input
              value={form.product_name}
              onChange={(event) => setForm({ ...form, product_name: event.target.value })}
              required
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Category
            <Input
              value={form.product_category}
              onChange={(event) => setForm({ ...form, product_category: event.target.value })}
              required
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Launch Offer
            <Input
              value={form.launch_offer}
              onChange={(event) => setForm({ ...form, launch_offer: event.target.value })}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700 md:col-span-2">
            Product Description
            <Textarea
              value={form.product_description}
              onChange={(event) => setForm({ ...form, product_description: event.target.value })}
              required
            />
          </label>
        </div>

        {error ? <div className="mt-4 rounded-md border border-rose/25 bg-rose/10 px-4 py-3 text-sm text-rose">{error}</div> : null}

        <div className="mt-5 flex justify-end">
          <Button type="submit" disabled={loading}>
            {loading ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
            {loading ? "Running..." : "Run AI Campaign"}
          </Button>
        </div>
      </form>
    </main>
  );
}
