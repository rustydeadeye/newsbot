"use client";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  return (
    <html lang="en">
      <body>
        <div className="auth-shell">
          <div className="auth-card">
            <div className="eyebrow">Application error</div>
            <h1>Newsbot could not render this screen.</h1>
            <p className="auth-copy">
              Something failed before the page could fully load. Try resetting the app once. If the issue
              continues, verify the local backend and Supabase auth configuration.
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
                Reload app
              </button>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
