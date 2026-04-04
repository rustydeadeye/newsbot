"use client";

import { useState, useTransition } from "react";
import { useSearchParams } from "next/navigation";

import { getRoleHomePath } from "@/lib/product-mode";
import { getXConnectUrl } from "@/lib/api";

export function ConnectXButton({ connected, nextPath = getRoleHomePath("customer") }: { connected: boolean; nextPath?: string }) {
  const searchParams = useSearchParams();
  const justConnected = searchParams.get("x_connected") === "1";
  const oauthError = searchParams.get("x_error");

  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function connect() {
    startTransition(async () => {
      try {
        const { auth_url } = await getXConnectUrl(null, nextPath);
        window.location.href = auth_url;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start X OAuth");
      }
    });
  }

  const isConnected = connected || justConnected;

  return (
    <div className="stack">
      <div className="row space">
        <div>
          <div className="field-label">Connection status</div>
          <div className="card-subtle">
            {isConnected
              ? "X account is connected. Newsbot will post from this account."
              : "No X account connected. Newsbot cannot post until you connect one."}
          </div>
        </div>
        <span className={isConnected ? "pill" : "pill danger"}>
          {isConnected ? "connected" : "not connected"}
        </span>
      </div>
      {!isConnected ? (
        <div className="actions">
          <button className="button" disabled={isPending} onClick={connect}>
            {isPending ? "Redirecting…" : "Connect X Account"}
          </button>
        </div>
      ) : (
        <div className="actions">
          <button className="button secondary" disabled={isPending} onClick={connect}>
            Reconnect X Account
          </button>
        </div>
      )}
      {justConnected ? <div className="card-subtle">X account connected successfully.</div> : null}
      {oauthError ? <div className="card-subtle">Connection failed: {oauthError.replaceAll("_", " ")}</div> : null}
      {error ? <div className="card-subtle">{error}</div> : null}
    </div>
  );
}
