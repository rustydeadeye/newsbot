"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { ConnectXButton } from "@/components/connect-x-button";
import { updateProfileSettings } from "@/lib/api";

export function AutopostSetupPanel({
  displayName,
  wireProduct,
  xConnected,
  openaiConfigured,
  tavilyConfigured,
}: {
  displayName: string | null;
  wireProduct: string;
  xConnected: boolean;
  openaiConfigured: boolean;
  tavilyConfigured: boolean;
}) {
  const router = useRouter();
  const [name, setName] = useState(displayName ?? "");
  const [product, setProduct] = useState<"finance" | "ai">(wireProduct === "ai" ? "ai" : "finance");
  const [openAiKey, setOpenAiKey] = useState("");
  const [tavilyKey, setTavilyKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function saveName() {
    setMessage(null);
    startTransition(async () => {
      try {
        await updateProfileSettings({
          display_name: name.trim(),
          wire_product: product,
          openai_api_key: openAiKey.trim() || undefined,
          tavily_api_key: tavilyKey.trim() || undefined,
        });
        setOpenAiKey("");
        setTavilyKey("");
        setMessage("Setup saved. Your pipeline integrations are ready to use.");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not save your setup");
      }
    });
  }

  return (
    <div className="stack">
      <div className="panel stack">
        <div className="eyebrow">Autopost setup</div>
        <div className="section-hero-title">Choose your news product and connect X</div>
        <p className="card-subtle">
          Newsbot will fetch, draft, and schedule posts for the product you choose. Keep setup simple: pick your topic, add your name, connect X, then turn autoposting on.
        </p>
        <div className="setup-steps">
          <div className="setup-step">
            <span className="setup-step-number">1</span>
            <div>
              <strong>Pick your product</strong>
              <div className="card-subtle">Choose whether this account should run finance updates or AI updates.</div>
            </div>
          </div>
          <div className="setup-step">
            <span className="setup-step-number">2</span>
            <div>
              <strong>Connect your tools</strong>
              <div className="card-subtle">Link X for publishing, OpenAI for drafting, and Tavily for news retrieval.</div>
            </div>
          </div>
          <div className="setup-step">
            <span className="setup-step-number">3</span>
            <div>
              <strong>Start autoposting</strong>
              <div className="card-subtle">Review the queue, pause anytime, and switch products later if your needs change.</div>
            </div>
          </div>
        </div>
      </div>

      <div className="product-choice-grid">
        <button
          className={product === "finance" ? "product-choice active" : "product-choice"}
          onClick={() => setProduct("finance")}
          type="button"
        >
          <div className="product-choice-top">
            <span className="pill">Finance</span>
          </div>
          <strong>Market and business updates</strong>
          <span className="card-subtle">Use Tradient and Tavily to cover finance, companies, policy, and market-moving context.</span>
        </button>
        <button
          className={product === "ai" ? "product-choice active" : "product-choice"}
          onClick={() => setProduct("ai")}
          type="button"
        >
          <div className="product-choice-top">
            <span className="pill">AI</span>
          </div>
          <strong>AI launches, moves, and policy</strong>
          <span className="card-subtle">Cover model launches, product changes, company moves, and major AI regulation in public-friendly language.</span>
        </button>
      </div>

      <div className="panel stack">
        <label>
          <span className="field-label">Display name</span>
          <input
            className="editor compact"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="How should Newsbot refer to you?"
          />
        </label>
        <div className="settings-layout">
          <div className="briefing-section">
            <div className="row space">
              <strong>OpenAI API key</strong>
              <span className={openaiConfigured ? "pill success" : "pill warn"}>
                {openaiConfigured ? "connected" : "needed"}
              </span>
            </div>
            <div className="card-subtle">
              Used for drafting, rewriting, and ranking your posts.
            </div>
            <input
              className="editor compact"
              value={openAiKey}
              onChange={(event) => setOpenAiKey(event.target.value)}
              placeholder={openaiConfigured ? "OpenAI key already saved. Paste a new key to replace it." : "Paste your OpenAI API key"}
            />
            <a className="source-link" href="https://platform.openai.com/api-keys" rel="noreferrer" target="_blank">
              How to get an OpenAI key
            </a>
          </div>
          <div className="briefing-section">
            <div className="row space">
              <strong>Tavily API key</strong>
              <span className={tavilyConfigured ? "pill success" : "pill warn"}>
                {tavilyConfigured ? "connected" : "needed"}
              </span>
            </div>
            <div className="card-subtle">
              Used to search the web and find the latest news for your pipeline.
            </div>
            <input
              className="editor compact"
              value={tavilyKey}
              onChange={(event) => setTavilyKey(event.target.value)}
              placeholder={tavilyConfigured ? "Tavily key already saved. Paste a new key to replace it." : "Paste your Tavily API key"}
            />
            <a className="source-link" href="https://app.tavily.com/home" rel="noreferrer" target="_blank">
              How to get a Tavily key
            </a>
          </div>
        </div>
        <div className="row">
          <span className="pill subtle">{product === "ai" ? "AI autopost" : "Finance autopost"}</span>
          <span className={xConnected ? "pill success" : "pill warn"}>
            {xConnected ? "X connected" : "Connect X next"}
          </span>
          <span className={openaiConfigured ? "pill success" : "pill warn"}>
            {openaiConfigured ? "OpenAI ready" : "OpenAI needed"}
          </span>
          <span className={tavilyConfigured ? "pill success" : "pill warn"}>
            {tavilyConfigured ? "Tavily ready" : "Tavily needed"}
          </span>
        </div>
        <div className="actions">
          <button className="button" disabled={isPending || !name.trim()} onClick={saveName} type="button">
            {isPending ? "Saving…" : "Save setup"}
          </button>
        </div>
        <ConnectXButton connected={xConnected} nextPath="/autopost" />
        <div className="card-subtle">
          Once setup is saved and all three integrations are connected, Newsbot can build and publish from your live queue.
        </div>
        {message ? <div className="inline-note">{message}</div> : null}
      </div>
    </div>
  );
}
