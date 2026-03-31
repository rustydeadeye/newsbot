"use client";

type TokenEditorProps = {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder: string;
  help?: string;
};

function normalize(value: string) {
  return value.trim().replace(/\s+/g, " ");
}

export function TokenEditor({ label, value, onChange, placeholder, help }: TokenEditorProps) {
  function updateFromInput(nextValue: string) {
    const tokens = nextValue
      .split(",")
      .map(normalize)
      .filter(Boolean);
    onChange(tokens);
  }

  function removeToken(token: string) {
    onChange(value.filter((item) => item !== token));
  }

  return (
    <label>
      <span className="field-label">{label}</span>
      <div className="token-editor">
        {value.length > 0 ? (
          <div className="token-list">
            {value.map((token) => (
              <button
                key={token}
                className="token-chip"
                onClick={() => removeToken(token)}
                type="button"
              >
                <span>{token}</span>
                <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
        ) : null}
        <textarea
          className="editor token-editor-input"
          value={value.join(", ")}
          onChange={(event) => updateFromInput(event.target.value)}
          placeholder={placeholder}
        />
      </div>
      {help ? <span className="card-subtle">{help}</span> : null}
    </label>
  );
}
