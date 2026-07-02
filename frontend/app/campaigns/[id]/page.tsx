"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  Edit3,
  RefreshCw,
  RotateCcw,
  Send,
  X
} from "lucide-react";
import { api, exportUrl, type Campaign, type CampaignResult, type Draft } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type DraftEdits = {
  email_subject: string;
  email_body: string;
  sms_body: string;
};

const toneOptions = ["professional", "friendly", "short-direct", "promotional", "warm"];

export default function CampaignResultsPage() {
  const params = useParams<{ id: string }>();
  const campaignId = params.id;
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [results, setResults] = useState<CampaignResult[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [edits, setEdits] = useState<Record<number, DraftEdits>>({});
  const [tones, setTones] = useState<Record<number, string>>({});
  const [instructions, setInstructions] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setMessage("");
    try {
      const [campaignData, resultData] = await Promise.all([
        api.getCampaign(campaignId),
        api.getCampaignResults(campaignId)
      ]);
      setCampaign(campaignData);
      setResults(resultData);
      const nextEdits: Record<number, DraftEdits> = {};
      const nextTones: Record<number, string> = {};
      resultData.forEach((result) => {
        if (result.draft) {
          nextEdits[result.draft.id] = draftToEdits(result.draft);
          nextTones[result.draft.id] = tones[result.draft.id] || "professional";
        }
      });
      setEdits(nextEdits);
      setTones(nextTones);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load campaign.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  const metrics = useMemo(() => {
    const drafts = results.filter((result) => result.draft).length;
    const approved = results.filter((result) => result.draft?.status === "approved").length;
    const sent = results.filter((result) => result.draft?.status === "sent_mock").length;
    return { drafts, approved, sent };
  }, [results]);

  async function replaceDraft(draftId: number, operation: () => Promise<Draft>) {
    const draft = await operation();
    setResults((current) =>
      current.map((result) => (result.draft?.id === draftId ? { ...result, draft } : result))
    );
    setEdits((current) => ({ ...current, [draft.id]: draftToEdits(draft) }));
  }

  async function saveDraft(draft: Draft) {
    try {
      await replaceDraft(draft.id, () => api.updateDraft(draft.id, edits[draft.id]));
      setMessage("Draft saved for review.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save failed.");
    }
  }

  async function regenerate(draft: Draft) {
    try {
      await replaceDraft(draft.id, () =>
        api.regenerateDraft(draft.id, {
          tone: tones[draft.id] || "professional",
          instruction: instructions[draft.id] || undefined
        })
      );
      setMessage("Draft regenerated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Regeneration failed.");
    }
  }

  async function action(draft: Draft, actionName: "approve" | "reject" | "send") {
    try {
      const response =
        actionName === "approve"
          ? await api.approveDraft(draft.id)
          : actionName === "reject"
            ? await api.rejectDraft(draft.id)
            : await api.sendMock(draft.id);
      setResults((current) =>
        current.map((result) => (result.draft?.id === draft.id ? { ...result, draft: response.draft } : result))
      );
      setMessage(response.message);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Draft action failed.");
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-5 py-7">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">{campaign?.name || "Campaign"}</h1>
          <div className="mt-2 flex flex-wrap gap-2">
            {campaign ? <Badge tone={campaign.status === "failed" ? "rose" : "teal"}>{campaign.status}</Badge> : null}
            <Badge tone="cobalt">{results.length} scored</Badge>
            <Badge tone="amber">{metrics.drafts} drafts</Badge>
            <Badge tone="neutral">{metrics.approved} approved</Badge>
            <Badge tone="teal">{metrics.sent} sent mock</Badge>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={load}>
            <RefreshCw size={16} />
            Refresh
          </Button>
          <Button asChild variant="secondary">
            <a href={exportUrl(campaignId)}>
              <Download size={16} />
              Export CSV
            </a>
          </Button>
        </div>
      </div>

      {campaign?.error_message ? (
        <div className="mb-4 rounded-md border border-rose/25 bg-rose/10 px-4 py-3 text-sm text-rose">
          {campaign.error_message}
        </div>
      ) : null}
      {message ? <div className="mb-4 rounded-md border border-line bg-white px-4 py-3 text-sm text-slate-700">{message}</div> : null}

      <div className="surface overflow-hidden rounded-lg">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] border-collapse text-sm">
            <thead className="border-b border-line bg-mist text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="w-12 px-4 py-3"></th>
                <th className="px-4 py-3 font-semibold">Customer</th>
                <th className="px-4 py-3 font-semibold">Intent</th>
                <th className="px-4 py-3 font-semibold">Channel</th>
                <th className="px-4 py-3 font-semibold">Draft</th>
                <th className="px-4 py-3 font-semibold">Reason</th>
                <th className="px-4 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={7}>
                    Loading results...
                  </td>
                </tr>
              ) : results.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-slate-500" colSpan={7}>
                    No ranked customers.
                  </td>
                </tr>
              ) : (
                results.map((result) => (
                  <Fragment key={result.id}>
                    <tr className="border-b border-line bg-white align-top">
                      <td className="px-4 py-3">
                        <Button
                          data-testid={`toggle-${result.id}`}
                          variant="ghost"
                          size="icon"
                          title="Toggle row"
                          onClick={() => setExpanded(expanded === result.id ? null : result.id)}
                        >
                          {expanded === result.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </Button>
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-ink">
                          {result.customer.first_name} {result.customer.last_name}
                        </p>
                        <p className="text-xs text-slate-500">{result.customer.email}</p>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-lg font-semibold">{result.buyer_score.toFixed(2)}</span>
                          <Badge tone={result.buyer_score >= 75 ? "teal" : "amber"}>
                            {result.buyer_score >= 75 ? "High Intent" : "Medium Intent"}
                          </Badge>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={channelTone(result.recommended_channel)}>{channelLabel(result.recommended_channel)}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={draftTone(result.draft?.status)}>{draftLabel(result.draft?.status)}</Badge>
                      </td>
                      <td className="max-w-md px-4 py-3 text-slate-600">{result.ranking_reason}</td>
                      <td className="px-4 py-3">
                        {result.draft ? (
                          <div className="flex flex-wrap gap-2">
                            <Button data-testid={`approve-${result.draft.id}`} variant="secondary" size="sm" onClick={() => action(result.draft!, "approve")}>
                              <Check size={14} />
                              Approve
                            </Button>
                            <Button data-testid={`reject-${result.draft.id}`} variant="secondary" size="sm" onClick={() => action(result.draft!, "reject")}>
                              <X size={14} />
                              Reject
                            </Button>
                            <Button data-testid={`send-${result.draft.id}`} size="sm" onClick={() => action(result.draft!, "send")}>
                              <Send size={14} />
                              Mock Send
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-500">No draft</span>
                        )}
                      </td>
                    </tr>
                    {expanded === result.id ? (
                      <tr className="border-b border-line bg-mist/60">
                        <td colSpan={7} className="px-4 py-5">
                          <ExpandedResult
                            result={result}
                            edits={result.draft ? edits[result.draft.id] : undefined}
                            tone={result.draft ? tones[result.draft.id] || "professional" : "professional"}
                            instruction={result.draft ? instructions[result.draft.id] || "" : ""}
                            onEdit={(draftId, next) => setEdits((current) => ({ ...current, [draftId]: next }))}
                            onTone={(draftId, tone) => setTones((current) => ({ ...current, [draftId]: tone }))}
                            onInstruction={(draftId, instruction) =>
                              setInstructions((current) => ({ ...current, [draftId]: instruction }))
                            }
                            onSave={saveDraft}
                            onRegenerate={regenerate}
                          />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

function ExpandedResult({
  result,
  edits,
  tone,
  instruction,
  onEdit,
  onTone,
  onInstruction,
  onSave,
  onRegenerate
}: {
  result: CampaignResult;
  edits?: DraftEdits;
  tone: string;
  instruction: string;
  onEdit: (draftId: number, edits: DraftEdits) => void;
  onTone: (draftId: number, tone: string) => void;
  onInstruction: (draftId: number, instruction: string) => void;
  onSave: (draft: Draft) => Promise<void>;
  onRegenerate: (draft: Draft) => Promise<void>;
}) {
  const draft = result.draft;

  return (
    <div className="grid gap-5 lg:grid-cols-[330px_1fr]">
      <div className="rounded-md border border-line bg-white p-4">
        <p className="mb-3 text-sm font-semibold text-ink">Score Breakdown</p>
        <div className="grid gap-2">
          {Object.entries(result.score_breakdown_json).map(([key, value]) => (
            <div key={key} className="grid grid-cols-[145px_1fr_48px] items-center gap-2 text-xs">
              <span className="capitalize text-slate-600">{key.replaceAll("_", " ")}</span>
              <span className="h-2 overflow-hidden rounded-full bg-slate-100">
                <span className="block h-2 rounded-full bg-teal" style={{ width: `${Math.min(value * 2.85, 100)}%` }} />
              </span>
              <span className="text-right font-medium text-ink">{value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>

      {draft && edits ? (
        <div className="grid gap-4 rounded-md border border-line bg-white p-4">
          <div className="grid gap-3 md:grid-cols-[1fr_170px]">
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Email Subject
              <Input
                value={edits.email_subject}
                onChange={(event) => onEdit(draft.id, { ...edits, email_subject: event.target.value })}
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-slate-700">
              Tone
              <Select value={tone} onChange={(event) => onTone(draft.id, event.target.value)}>
                {toneOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </label>
          </div>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Email Body
            <Textarea
              value={edits.email_body}
              onChange={(event) => onEdit(draft.id, { ...edits, email_body: event.target.value })}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            SMS Body
            <Textarea
              className="min-h-20"
              value={edits.sms_body}
              onChange={(event) => onEdit(draft.id, { ...edits, sms_body: event.target.value })}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Regeneration Instruction
            <Input value={instruction} onChange={(event) => onInstruction(draft.id, event.target.value)} />
          </label>
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={() => onSave(draft)}>
              <Edit3 size={16} />
              Save Edits
            </Button>
            <Button onClick={() => onRegenerate(draft)}>
              <RotateCcw size={16} />
              Regenerate
            </Button>
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-line bg-white p-4 text-sm text-slate-500">No draft generated.</div>
      )}
    </div>
  );
}

function draftToEdits(draft: Draft): DraftEdits {
  return {
    email_subject: draft.email_subject || "",
    email_body: draft.email_body || "",
    sms_body: draft.sms_body || ""
  };
}

function channelLabel(channel: string) {
  if (channel === "both") return "Both Channels";
  if (channel === "sms") return "SMS Only";
  if (channel === "email") return "Email Only";
  return "No Channel";
}

function channelTone(channel: string): "teal" | "cobalt" | "amber" | "neutral" {
  if (channel === "both") return "teal";
  if (channel === "sms") return "cobalt";
  if (channel === "email") return "amber";
  return "neutral";
}

function draftLabel(status?: string | null) {
  if (!status) return "No Draft";
  return status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function draftTone(status?: string | null): "teal" | "amber" | "rose" | "cobalt" | "neutral" {
  if (status === "approved" || status === "sent_mock") return "teal";
  if (status === "rejected") return "rose";
  if (status === "regenerated") return "cobalt";
  if (status === "pending_review") return "amber";
  return "neutral";
}
