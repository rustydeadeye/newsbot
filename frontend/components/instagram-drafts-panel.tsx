"use client";

import { useState, useTransition } from "react";

import {
  approveInstagramDraft,
  generateInstagramDrafts,
  publishInstagramDraftNow,
  regenerateInstagramDraft,
  renderApprovedInstagramDrafts,
  renderInstagramDraft,
  rejectInstagramDraft,
  scheduleInstagramDraft,
} from "@/lib/api";
import { formatOptionalDateTime } from "@/lib/lifecycle-ui";
import { InstagramDraft, InstagramPublishJob, InstagramPublishLog } from "@/lib/types";

const LANE_LABELS: Record<string, string> = {
  ai_news: "AI / news",
  ai_explained: "AI / explained",
  ai_for_business: "AI / business",
};

export function InstagramDraftsPanel({
  drafts: initialDrafts,
  publishJobs,
  publishLogs
}: {
  drafts: InstagramDraft[];
  publishJobs: InstagramPublishJob[];
  publishLogs: InstagramPublishLog[];
}) {
  const [drafts, setDrafts] = useState(initialDrafts);
  const [message, setMessage] = useState<string | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<number, string>>({});
  const [isPending, startTransition] = useTransition();

  function replaceDraft(updated: InstagramDraft) {
    setDrafts((prev) => {
      const existing = prev.find((draft) => draft.id === updated.id);
      if (existing) {
        return prev.map((draft) => (draft.id === updated.id ? updated : draft));
      }
      return [updated, ...prev];
    });
  }

  function onGenerate() {
    setMessage(null);
    startTransition(async () => {
      try {
        const generated = await generateInstagramDrafts();
        setDrafts((prev) => [...generated, ...prev]);
        setMessage(generated.length > 0 ? `Generated ${generated.length} Instagram drafts.` : "No new Instagram drafts were generated.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not generate Instagram drafts");
      }
    });
  }

  function onRenderApproved() {
    setMessage(null);
    startTransition(async () => {
      try {
        const rendered = await renderApprovedInstagramDrafts();
        setDrafts((prev) => prev.map((draft) => rendered.find((item) => item.id === draft.id) ?? draft));
        setMessage(rendered.length > 0 ? `Rendered ${rendered.length} approved drafts.` : "No approved drafts were rendered.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not render approved drafts");
      }
    });
  }

  function onApprove(draftId: number) {
    startTransition(async () => {
      try {
        replaceDraft(await approveInstagramDraft(draftId));
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [draftId]: error instanceof Error ? error.message : "Approve failed" }));
      }
    });
  }

  function onReject(draftId: number) {
    startTransition(async () => {
      try {
        replaceDraft(await rejectInstagramDraft(draftId));
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [draftId]: error instanceof Error ? error.message : "Reject failed" }));
      }
    });
  }

  function onRegenerate(draftId: number) {
    startTransition(async () => {
      try {
        replaceDraft(await regenerateInstagramDraft(draftId));
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [draftId]: error instanceof Error ? error.message : "Regenerate failed" }));
      }
    });
  }

  function onRender(draftId: number) {
    startTransition(async () => {
      try {
        replaceDraft(await renderInstagramDraft(draftId));
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [draftId]: error instanceof Error ? error.message : "Render failed" }));
      }
    });
  }

  function onSchedule(draftId: number) {
    startTransition(async () => {
      try {
        const draft = await scheduleInstagramDraft(draftId);
        replaceDraft(draft);
        setMessage(`Scheduled Instagram draft ${draft.id} for ${draft.scheduled_for ?? "now"}.`);
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [draftId]: error instanceof Error ? error.message : "Schedule failed" }));
      }
    });
  }

  function onPublishNow(draftId: number) {
    startTransition(async () => {
      try {
        const draft = await publishInstagramDraftNow(draftId);
        replaceDraft(draft);
        setMessage(`Instagram draft ${draft.id} is now ${draft.publish_status}.`);
      } catch (error) {
        setActionErrors((prev) => ({ ...prev, [draftId]: error instanceof Error ? error.message : "Publish failed" }));
      }
    });
  }

  return (
    <div className="panel stack">
      <div className="row space">
        <div>
          <div className="section-title">Instagram carousel pipeline</div>
          <div className="card-subtle">Generate, render, review, schedule, and inspect Instagram carousels without touching the live X queue.</div>
        </div>
        <div className="actions">
          <button className="button secondary" disabled={isPending} onClick={onRenderApproved} type="button">
            Render approved
          </button>
          <button className="button" disabled={isPending} onClick={onGenerate} type="button">
            Generate drafts
          </button>
        </div>
      </div>
      {message ? <div className="card-subtle">{message}</div> : null}
      {publishJobs.length > 0 ? <div className="card-subtle">Instagram jobs in queue: {publishJobs.length}. Recent publish logs: {publishLogs.length}.</div> : null}
      <div className="log-list">
        {drafts.length === 0 ? <div className="empty">No Instagram drafts yet. Generate a batch to start reviewing carousel blueprints.</div> : null}
        {drafts.map((draft) => (
          <div key={draft.id} className="publish-row">
            <div className="row space">
              <div className="row">
                <span className="pill subtle">{LANE_LABELS[draft.lane] ?? draft.lane}</span>
                <span className="pill">{draft.review_status}</span>
                {draft.quality_band ? <span className="pill subtle">band {draft.quality_band}</span> : null}
                <span className="pill subtle">{draft.render_status}</span>
                <span className="pill subtle">{draft.publish_status}</span>
                <span className="card-subtle">{draft.seed_source_name}</span>
              </div>
              <span className="card-subtle">{formatOptionalDateTime(draft.updated_at) ?? "Just now"}</span>
            </div>
            <div className="queue-row-title">{draft.hook}</div>
            <div className="card-subtle">{draft.angle}</div>
            {draft.preview_slides.length > 0 ? (
              <div className="stack">
                {draft.preview_slides.map((slide) => (
                  <div key={`${draft.id}-preview-${slide.slide_number}`} className="publish-log-row">
                    <div className="row space">
                      <span className="pill subtle">preview {slide.slide_number}</span>
                      <span className="card-subtle">{slide.template_id ?? "template"}</span>
                    </div>
                    <img
                      alt={`${draft.title} slide ${slide.slide_number}`}
                      src={slide.preview_url}
                      style={{ width: "100%", borderRadius: 20, border: "1px solid rgba(148,163,184,0.2)" }}
                    />
                  </div>
                ))}
              </div>
            ) : null}
            <div className="stack">
              {draft.slides.map((slide) => (
                <div key={`${draft.id}-${slide.slide_number}`} className="publish-log-row">
                  <div className="row space">
                    <span className="pill subtle">slide {slide.slide_number}</span>
                    <span className="card-subtle">{slide.role}</span>
                  </div>
                  <div className="queue-row-title">{slide.headline}</div>
                  <div className="card-subtle">{slide.support}</div>
                </div>
              ))}
            </div>
            <div className="card-subtle">
              Caption: {draft.caption.hook} {draft.caption.body} {draft.caption.cta}
            </div>
            {draft.scheduled_for ? <div className="card-subtle">Scheduled: {formatOptionalDateTime(draft.scheduled_for)}</div> : null}
            {draft.published_at ? <div className="card-subtle">Published: {formatOptionalDateTime(draft.published_at)}</div> : null}
            {draft.last_error ? <div className="card-subtle">Last error: {draft.last_error}</div> : null}
            {draft.reviewed_by ? <div className="card-subtle">Last review: {draft.reviewed_by}</div> : null}
            {actionErrors[draft.id] ? <div className="card-subtle">{actionErrors[draft.id]}</div> : null}
            <div className="actions">
              <button className="button secondary" disabled={isPending} onClick={() => onApprove(draft.id)} type="button">
                Approve
              </button>
              <button className="button secondary" disabled={isPending} onClick={() => onReject(draft.id)} type="button">
                Reject
              </button>
              <button className="button secondary" disabled={isPending} onClick={() => onRender(draft.id)} type="button">
                Render
              </button>
              <button className="button secondary" disabled={isPending} onClick={() => onSchedule(draft.id)} type="button">
                Schedule
              </button>
              <button className="button secondary" disabled={isPending} onClick={() => onPublishNow(draft.id)} type="button">
                Publish Now
              </button>
              <button className="button" disabled={isPending} onClick={() => onRegenerate(draft.id)} type="button">
                Regenerate
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
