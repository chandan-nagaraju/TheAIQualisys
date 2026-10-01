import { useState } from "react";

export default function InvoiceMailFields({
  accountsEmail,
  ccEmails,
  onAccountsEmail,
  onCcEmails,
  inputClass,
  labelClass,
}: {
  accountsEmail: string;
  ccEmails: string[];
  onAccountsEmail: (v: string) => void;
  onCcEmails: (v: string[]) => void;
  inputClass: string;
  labelClass?: string;
}) {
  const [draft, setDraft] = useState("");

  function addCc() {
    const next = draft.trim().toLowerCase();
    if (!next) return;
    if (ccEmails.some((e) => e.toLowerCase() === next) || next === accountsEmail.trim().toLowerCase()) {
      setDraft("");
      return;
    }
    if (ccEmails.length >= 20) return;
    onCcEmails([...ccEmails, next]);
    setDraft("");
  }

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
        <p className="mt-1 text-xs text-slate-500">Saved CCs are added automatically when the invoice is emailed.</p>
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
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addCc();
              }
            }}
            placeholder="Add a CC email"
          />
          <button
            type="button"
            className="shrink-0 rounded border border-slate-300 px-3 py-2 text-sm"
            onClick={addCc}
          >
            Add CC
          </button>
        </div>
      </div>
    </div>
  );
}
