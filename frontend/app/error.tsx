"use client";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorProps) {
  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="eyebrow">Workspace issue</div>
        <h1>We hit a loading problem.</h1>
        <p className="auth-copy">
          The page could not be rendered cleanly. Try again first. If this keeps happening, check your
          authentication and API configuration.
        </p>
        <div className="workspace-list">
          <div className="workspace-list-row">
            <span>Error</span>
            <strong>{error.message || "Unexpected application error"}</strong>
          </div>
          {error.digest ? (
            <div className="workspace-list-row">
              <span>Digest</span>
              <strong>{error.digest}</strong>
            </div>
          ) : null}
        </div>
        <div className="hero-actions">
          <button className="button button-primary" onClick={() => reset()} type="button">
            Try again
          </button>
        </div>
      </div>
    </div>
  );
}
