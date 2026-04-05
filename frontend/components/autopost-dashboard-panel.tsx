"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { disconnectXAccount, pauseAutopost, resumeAutopost, updateProfileSettings } from "@/lib/api";
import { formatOptionalDateTime } from "@/lib/lifecycle-ui";
import { AutopostDashboard } from "@/lib/types";

function formatPostingWindow(startHour: number, endHour: number, timezone: string) {
  if (startHour === endHour) {
    return `24/7 ${timezone}`;
  }
  return `${startHour}:00 to ${endHour}:00 ${timezone}`;
}

function formatPipelineLabel(product: string, sourceFamily: string, lane: string | null, sourceName: string) {
  if (sourceFamily === "web") {
    if (product === "ai") {
      if (lane === "product_updates") return "Tavily AI products";
      if (lane === "industry_moves") return "Tavily AI industry";
      if (lane === "policy_regulation") return "Tavily AI policy";
      return "Tavily AI web";
    }
    if (lane === "india_preopen") return "Tavily preopen";
    if (lane === "india_close") return "Tavily close";
    if (lane === "global_impact") return "Tavily global";
    return "Tavily web";
  }
  if (product === "ai") return "AI base";
  if (sourceName === "tradient_market_news") return "Tradient";
  return "Base wire";
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

  return (
    <div className="stack">
      <div className="hero-panel">
        <div className="hero-copy">
          <div className="eyebrow">Autopost overview</div>
          <h3>{dashboard.wire_product_label} autopost</h3>
          <p>{productDescription}</p>
        </div>
        <div className="hero-actions">
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
          <div className="workspace-chip">
            <span className="status-dot" />
            <span>{statusLabel}</span>
          </div>
        </div>
      </div>

      <div className="panel stack">
        <div className="section-title">Status</div>
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
            <span>X connection</span>
            <strong>{dashboard.x_connected ? "Connected" : "Not connected"}</strong>
          </div>
          <div className="workspace-list-row">
            <span>OpenAI</span>
            <strong>{dashboard.openai_configured ? "Connected" : "Missing"}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Tavily</span>
            <strong>{dashboard.tavily_configured ? "Connected" : "Missing"}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Publishing</span>
            <strong>{formatPostingWindow(dashboard.posting_window.start_hour, dashboard.posting_window.end_hour, "IST")}</strong>
          </div>
          <div className="workspace-list-row">
            <span>Quiet hours</span>
            <strong>{formatPostingWindow(dashboard.quiet_hours.start_hour, dashboard.quiet_hours.end_hour, "IST")} for standard posts</strong>
          </div>
          <div className="workspace-list-row">
            <span>Scan cadence</span>
            <strong>Every {dashboard.scan_interval_minutes} minutes</strong>
          </div>
          <div className="workspace-list-row">
            <span>Pipeline readiness</span>
            <strong>{dashboard.publishing_ready ? "Ready to publish" : "Finish setup first"}</strong>
          </div>
        </div>
      </div>

      <div className="panel stack">
        <div className="section-title">Next scheduled posts</div>
        <div className="card-subtle">These posts are already selected and waiting for their next publishing slot.</div>
        {dashboard.next_posts.length === 0 ? (
          <div className="empty">Nothing is scheduled right now. The next approved post will appear here automatically.</div>
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
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="panel stack">
        <div className="section-title">Recent posts</div>
        <div className="card-subtle">A simple view of what was published recently and which pipeline produced it.</div>
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
        <div className="section-title">How it works</div>
        <div className="info-grid">
          <div className="info-tile">
            <strong>1. Fetch</strong>
            <span className="card-subtle">Newsbot pulls updates from the product you selected and filters for relevance.</span>
          </div>
          <div className="info-tile">
            <strong>2. Draft</strong>
            <span className="card-subtle">Approved updates are turned into short publishable posts that are easy to read quickly.</span>
          </div>
          <div className="info-tile">
            <strong>3. Schedule</strong>
            <span className="card-subtle">The queue spaces posts out, avoids duplicates, and keeps the feed understandable.</span>
          </div>
        </div>
      </div>

      <div className="panel stack">
        <div className="section-title">Controls</div>
        <div className="card-subtle">Pause the queue when you want a break, or disconnect X if you no longer want this account to publish.</div>
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
        {message ? <div className="inline-note">{message}</div> : null}
      </div>
    </div>
  );
}
