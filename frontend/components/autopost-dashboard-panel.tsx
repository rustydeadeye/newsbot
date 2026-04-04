"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { disconnectXAccount, pauseAutopost, resumeAutopost } from "@/lib/api";
import { formatOptionalDateTime } from "@/lib/lifecycle-ui";
import { AutopostDashboard } from "@/lib/types";

function formatPostingWindow(startHour: number, endHour: number, timezone: string) {
  if (startHour === endHour) {
    return `24/7 ${timezone}`;
  }
  return `${startHour}:00 to ${endHour}:00 ${timezone}`;
}

function formatPipelineLabel(sourceFamily: string, lane: string | null, sourceName: string) {
  if (sourceFamily === "web") {
    if (lane === "india_preopen") return "Tavily preopen";
    if (lane === "india_close") return "Tavily close";
    if (lane === "global_impact") return "Tavily global";
    return "Tavily web";
  }
  if (sourceName === "tradient_market_news") {
    return "Tradient";
  }
  return "Base wire";
}

export function AutopostDashboardPanel({ initialDashboard }: { initialDashboard: AutopostDashboard }) {
  const router = useRouter();
  const [dashboard, setDashboard] = useState(initialDashboard);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function onPause() {
    setMessage(null);
    startTransition(async () => {
      try {
        const next = await pauseAutopost();
        setDashboard(next);
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

  const statusLabel =
    dashboard.status === "active"
      ? "Autoposting is active"
      : dashboard.status === "needs_attention"
        ? "Autoposting needs attention"
        : "Autoposting is paused";

  return (
    <div className="stack">
      <div className="panel stack">
        <div className="section-title">Status</div>
        <div className="workspace-list">
          <div className="workspace-list-row">
            <span>Status</span>
            <strong>{statusLabel}</strong>
          </div>
          <div className="workspace-list-row">
            <span>X connection</span>
            <strong>{dashboard.x_connected ? "Connected" : "Not connected"}</strong>
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
        </div>
      </div>

      <div className="panel stack">
        <div className="section-title">Next scheduled posts</div>
        {dashboard.next_posts.length === 0 ? (
          <div className="empty">No posts are queued right now.</div>
        ) : (
          <div className="log-list">
            {dashboard.next_posts.map((post) => (
                <div key={post.id} className="publish-row">
                <div className="row space">
                  <div className="row">
                    <span className="pill warn">queued</span>
                    <span className="mono">{post.ticker ?? "MARKET"}</span>
                    <span className="card-subtle">{formatPipelineLabel(post.source_family, post.lane, post.source_name)}</span>
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
        {dashboard.recent_posts.length === 0 ? (
          <div className="empty">No recent posts yet.</div>
        ) : (
          <div className="log-list">
            {dashboard.recent_posts.map((post) => (
              <div key={post.id} className="publish-log-row">
                <div className="row space">
                  <div className="row">
                    <span className="pill">posted</span>
                    <span className="card-subtle">{formatPipelineLabel(post.source_family, post.lane, post.source_name ?? "unknown")}</span>
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
        <div className="section-title">Controls</div>
        <div className="actions">
          {dashboard.autopost_enabled ? (
            <button className="button secondary" disabled={isPending} onClick={onPause} type="button">
              Pause autoposting
            </button>
          ) : (
            <button className="button" disabled={isPending || !dashboard.x_connected} onClick={onResume} type="button">
              Resume autoposting
            </button>
          )}
          <button className="button danger" disabled={isPending} onClick={onDisconnect} type="button">
            Disconnect X
          </button>
        </div>
        {message ? <div className="card-subtle">{message}</div> : null}
      </div>
    </div>
  );
}
