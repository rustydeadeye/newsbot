"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { disconnectXAccount, pauseAutopost, resumeAutopost, updateProfileSettings } from "@/lib/api";
import { formatOptionalDateTime, formatPipelineLabel } from "@/lib/lifecycle-ui";
import { AutopostDashboard } from "@/lib/types";

function formatPostingWindow(startHour: number, endHour: number, timezone: string) {
  if (startHour === endHour) {
    return `24/7 ${timezone}`;
  }
  return `${startHour}:00 to ${endHour}:00 ${timezone}`;
}

function formatStatusSummary(status: AutopostDashboard["status"]) {
  if (status === "active") {
    return "Your autopost system is live and scheduling posts automatically.";
  }
  if (status === "needs_attention") {
    return "Autopost is running, but something needs attention before you can trust the queue fully.";
  }
  return "Autopost is paused. Nothing new will publish until you turn it back on again.";
}

export function AutopostDashboardPanel({ initialDashboard }: { initialDashboard: AutopostDashboard }) {
  const router = useRouter();
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [selectedProduct, setSelectedProduct] = useState<"finance" | "ai">(initialDashboard.wire_product === "ai" ? "ai" : "finance");
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function onPause() {
    setMessage(null);
    startTransition(async () => {
      try {
        const next = await pauseAutopost();
        setDashboard(next);
        setSelectedProduct(next.wire_product === "ai" ? "ai" : "finance");
        setMessage("Autoposting paused.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not pause autoposting");
      }
    });
  }

  function onResume() {
    setMessage(null);
    startTransition(async () => {
      try {
        const next = await resumeAutopost();
        setDashboard(next);
        setSelectedProduct(next.wire_product === "ai" ? "ai" : "finance");
        setMessage("Autoposting resumed.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not resume autoposting");
      }
    });
  }

  function onDisconnect() {
    setMessage(null);
    startTransition(async () => {
      try {
        await disconnectXAccount();
        setMessage("X disconnected.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not disconnect X");
      }
    });
  }

  function onProductChange(product: "finance" | "ai") {
    setMessage(null);
    setSelectedProduct(product);
    startTransition(async () => {
      try {
        await updateProfileSettings({ wire_product: product });
        setMessage(`Autopost product switched to ${product === "ai" ? "AI" : "Finance"}.`);
        router.refresh();
      } catch (error) {
        setSelectedProduct(dashboard.wire_product === "ai" ? "ai" : "finance");
        setMessage(error instanceof Error ? error.message : "Could not switch product");
      }
    });
  }

  const statusLabel =
    dashboard.status === "active"
      ? "Autoposting is active"
      : dashboard.status === "needs_attention"
        ? "Autoposting needs attention"
        : "Autoposting is paused";

  const productDescription =
    dashboard.wire_product === "ai"
      ? "Newsbot is set up to track AI launches, company moves, and policy updates in plain public-facing language."
      : "Newsbot is set up to track finance, company, and market-moving updates with a mix of structured feeds and editorial web coverage.";
  const nextPost = dashboard.next_posts[0] ?? null;
  const statusSummary = formatStatusSummary(dashboard.status);

  return (
    <div className="stack">
      <div className="hero-panel">
        <div className="hero-copy">
          <div className="eyebrow">Live overview</div>
          <h3>{dashboard.wire_product_label} dashboard</h3>
          <p>{statusSummary}</p>
        </div>
        <div className="hero-actions">
          <div className="workspace-chip">
            <span className="status-dot" />
            <span>{statusLabel}</span>
          </div>
          <div className="hero-kicker">
            <span className="pill subtle">{dashboard.wire_product_label}</span>
            <span className="card-subtle">
              {nextPost
                ? `Next post ${formatOptionalDateTime(nextPost.scheduled_for, "Asia/Kolkata") ?? "scheduled soon"}`
                : "No post is scheduled right now"}
            </span>
          </div>
        </div>
      </div>

      <div className="customer-home-grid">
        <div className="panel stack">
          <div className="section-title">At a glance</div>
          <div className="workspace-list">
            <div className="workspace-list-row">
              <span>Status</span>
              <strong>{statusLabel}</strong>
            </div>
            <div className="workspace-list-row">
              <span>Product</span>
              <strong>{dashboard.wire_product_label}</strong>
            </div>
            <div className="workspace-list-row">
              <span>Queue</span>
              <strong>{dashboard.next_posts.length > 0 ? `${dashboard.next_posts.length} post${dashboard.next_posts.length > 1 ? "s" : ""} waiting` : "Nothing waiting"}</strong>
            </div>
            <div className="workspace-list-row">
              <span>Recent activity</span>
              <strong>{dashboard.recent_posts.length > 0 ? "Publishing history available" : "No posts published yet"}</strong>
            </div>
          </div>
        </div>

        <div className="panel stack">
          <div className="section-title">Current setup</div>
          <div className="workspace-list">
            <div className="workspace-list-row">
              <span>X connection</span>
              <strong>{dashboard.x_connected ? "Connected" : "Not connected"}</strong>
            </div>
            <div className="workspace-list-row">
              <span>Publishing readiness</span>
              <strong>{dashboard.publishing_ready ? "Ready to publish" : "Needs attention"}</strong>
            </div>
            <div className="workspace-list-row">
              <span>Publishing window</span>
              <strong>{formatPostingWindow(dashboard.posting_window.start_hour, dashboard.posting_window.end_hour, "IST")}</strong>
            </div>
          </div>
          <div className="card-subtle">{productDescription}</div>
        </div>
      </div>

      <div className="panel stack">
        <div className="section-title">Next scheduled posts</div>
        <div className="card-subtle">These are the posts already approved and waiting for their next publishing slot.</div>
        {dashboard.next_posts.length === 0 ? (
          <div className="empty">Nothing is scheduled right now. Once Newsbot approves the next item, it will appear here automatically.</div>
        ) : (
          <div className="log-list">
            {dashboard.next_posts.map((post) => (
              <div key={post.id} className="publish-row">
                <div className="row space">
                  <div className="row">
                    <span className="pill warn">scheduled</span>
                    <span className="mono">{post.ticker ?? "MARKET"}</span>
                    <span className="card-subtle">{formatPipelineLabel(post.product, post.source_family, post.lane, post.source_name)}</span>
                  </div>
                  <span className="card-subtle">{formatOptionalDateTime(post.scheduled_for, "Asia/Kolkata") ?? "Time unavailable"}</span>
                </div>
                <div className="queue-row-title">{post.tweet_text}</div>
                <div className="card-subtle">{post.source_title}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel stack">
        <div className="section-title">Recent posts</div>
        <div className="card-subtle">A quick history of what Newsbot has already published for this account.</div>
        {dashboard.recent_posts.length === 0 ? (
          <div className="empty">No recent posts yet. Once Newsbot publishes, this becomes your quick history view.</div>
        ) : (
          <div className="log-list">
            {dashboard.recent_posts.map((post) => (
              <div key={post.id} className="publish-log-row">
                <div className="row space">
                  <div className="row">
                    <span className="pill">posted</span>
                    <span className="card-subtle">{formatPipelineLabel(post.product, post.source_family, post.lane, post.source_name ?? "unknown")}</span>
                  </div>
                  <span className="card-subtle">{formatOptionalDateTime(post.posted_at, "Asia/Kolkata") ?? "Time unavailable"}</span>
                </div>
                <div className="queue-row-title">{post.tweet_text ?? "Posted item"}</div>
                <div className="card-subtle">{post.source_title}</div>
                {post.x_url ? (
                  <a className="source-link" href={post.x_url} rel="noreferrer" target="_blank">
                    View on X
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel stack">
        <div className="section-title">Controls</div>
        <div className="card-subtle">Pause publishing when you want a break, disconnect X if you no longer want this account to publish, or switch products deliberately.</div>
        <div className="actions">
          {dashboard.autopost_enabled ? (
            <button className="button secondary" disabled={isPending} onClick={onPause} type="button">
              Pause autoposting
            </button>
          ) : (
            <button className="button" disabled={isPending || !dashboard.publishing_ready} onClick={onResume} type="button">
              Resume autoposting
            </button>
          )}
          <button className="button danger" disabled={isPending} onClick={onDisconnect} type="button">
            Disconnect X
          </button>
        </div>
        <div className="briefing-section">
          <div className="row space">
            <strong>Publishing product</strong>
            <span className="pill subtle">{dashboard.wire_product_label}</span>
          </div>
          <div className="card-subtle">Change this only if you want this account to switch from finance news to AI news, or the other way around.</div>
          <div className="product-switcher" role="tablist" aria-label="Autopost product">
            <button
              className={selectedProduct === "finance" ? "product-switch active" : "product-switch"}
              disabled={isPending}
              onClick={() => onProductChange("finance")}
              type="button"
            >
              Finance
            </button>
            <button
              className={selectedProduct === "ai" ? "product-switch active" : "product-switch"}
              disabled={isPending}
              onClick={() => onProductChange("ai")}
              type="button"
            >
              AI
            </button>
          </div>
        </div>
        {message ? <div className="inline-note">{message}</div> : null}
      </div>

      <details className="settings-disclosure">
        <summary>Technical details</summary>
        <div className="settings-group">
          <div className="workspace-list-row">
            <span>OpenAI</span>
            <strong>{dashboard.openai_configured ? "Connected" : "Missing"}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Tavily</span>
            <strong>{dashboard.tavily_configured ? "Connected" : "Missing"}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Quiet hours</span>
            <strong>{formatPostingWindow(dashboard.quiet_hours.start_hour, dashboard.quiet_hours.end_hour, "IST")} for standard posts</strong>
          </div>
          <div className="workspace-list-row">
            <span>Scan cadence</span>
            <strong>Every {dashboard.scan_interval_minutes} minutes</strong>
          </div>
        </div>
      </details>
    </div>
  );
}
