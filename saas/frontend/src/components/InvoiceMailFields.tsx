import { forwardRef, useImperativeHandle, useState } from "react";

export type InvoiceMailHandle = { commitDraft: () => string[] };

function mergeCc(existing: string[], incoming: string, toAddr: string): string[] {
  const parts = incoming
    .split(/[\s,;]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  const skip = toAddr.trim().toLowerCase();
  const out = [...existing];
  for (const part of parts) {
    if (part === skip || out.some((e) => e.toLowerCase() === part)) continue;
    if (out.length >= 20) break;
    out.push(part);
  }
  return out;
}

const InvoiceMailFields = forwardRef<InvoiceMailHandle, {
  accountsEmail: string;
  ccEmails: string[];
  onAccountsEmail: (v: string) => void;
  onCcEmails: (v: string[]) => void;
  inputClass: string;
  labelClass?: string;
}>(function InvoiceMailFields(
  { accountsEmail, ccEmails, onAccountsEmail, onCcEmails, inputClass, labelClass },
  ref,
) {
  const [draft, setDraft] = useState("");

  function commit(incoming = draft): string[] {
    const next = mergeCc(ccEmails, incoming, accountsEmail);
    onCcEmails(next);
    setDraft("");
    return next;
  }

  useImperativeHandle(ref, () => ({ commitDraft: () => commit() }), [ccEmails, draft, accountsEmail]);

  return (
    <div className="space-y-3">
      <label className={labelClass || "block text-xs font-medium text-slate-600"}>
        Accounts email (To)
        <input
          type="email"
          className={inputClass}
          value={accountsEmail}
          onChange={(e) => onAccountsEmail(e.target.value)}
          placeholder="accounts@company.com"
        />
      </label>
      <div>
        <p className={labelClass || "text-xs font-medium text-slate-600"}>CC email ids</p>
        <p className="mt-1 text-xs text-slate-500">
          Click Add CC (or Save) after typing each address. Saved CCs receive the invoice automatically.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {ccEmails.map((email) => (
            <span
              key={email}
              className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-xs text-slate-800"
            >
              {email}
              <button
                type="button"
                className="text-slate-500 hover:text-red-600"
                onClick={() => onCcEmails(ccEmails.filter((e) => e !== email))}
                aria-label={`Remove ${email}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            type="email"
            className={inputClass}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => {
              if (draft.trim()) commit();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                commit();
              }
            }}
            placeholder="Add a CC email"
          />
          <button type="button" className="shrink-0 rounded border border-slate-300 px-3 py-2 text-sm" onClick={() => commit()}>
            Add CC
          </button>
        </div>
      </div>
    </div>
  );
});

export default InvoiceMailFields;
