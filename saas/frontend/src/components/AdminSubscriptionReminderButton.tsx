import { useState } from "react";
import { apiFetch } from "../api";

type SendResponse = {
  ok?: boolean;
  email_status: string;
};

type Props = {
  companyId: number;
  /** Compact style for table cells (smaller button, no full-width feedback). */
  variant?: "default" | "inline";
};

export function AdminSubscriptionReminderButton({ companyId, variant = "default" }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null);

  async function send(reminderType: "ending_soon" | "already_ended") {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await apiFetch<SendResponse>(`/admin/companies/${companyId}/subscription-reminder`, {
        method: "POST",
        token: "admin",
        body: JSON.stringify({ reminder_type: reminderType }),
      });
      const text =
        res.email_status === "partial" ? "Email sent (not all recipients)." : "Email sent.";
      setFeedback({ ok: true, text });
      setOpen(false);
    } catch (e) {
      setFeedback({
        ok: false,
        text: "Email not sent.",
      });
    } finally {
      setBusy(false);
    }
  }

  const btnClass =
    variant === "inline"
      ? "rounded border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-50"
      : "inline-flex shrink-0 items-center justify-center rounded-lg border border-amber-600/50 bg-amber-950/30 px-4 py-2 text-sm font-medium text-amber-100 hover:bg-amber-950/50 disabled:opacity-50";

  return (
    <div
      className={
        variant === "inline"
          ? "inline-flex flex-col items-start text-left"
          : "inline-flex flex-col items-start"
      }
    >
      <button type="button" className={btnClass} disabled={busy} onClick={() => setOpen(true)}>
        {busy ? "Sending…" : "Reminder"}
      </button>
      {/* Fixed-height line so the Actions row / table layout does not jump when status appears */}
      <p
        className={`mt-1 min-h-[1.25rem] text-xs leading-tight tabular-nums ${feedback == null ? "text-transparent" : feedback.ok ? "text-emerald-400" : "text-red-400"}`}
        aria-live="polite"
      >
        {feedback?.text ?? "\u00a0"}
      </p>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="presentation"
          onClick={() => !busy && setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reminder-modal-title"
            className="max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="reminder-modal-title" className="text-lg font-semibold text-white">
              Send subscription reminder
            </h3>
            <p className="mt-2 text-sm text-slate-400">
              Choose the message type. Email goes to every non-blocked workspace user for this company.
            </p>
            <div className="mt-6 flex flex-col gap-3">
              <button
                type="button"
                disabled={busy}
                className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                onClick={() => void send("ending_soon")}
              >
                <span className="font-medium text-white">Subscription Ending Soon</span>
                <span className="mt-1 block text-xs text-slate-400">Expires on date — renewal encouragement before lapse.</span>
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                onClick={() => void send("already_ended")}
              >
                <span className="font-medium text-white">Subscription Already Ended</span>
                <span className="mt-1 block text-xs text-slate-400">Past expiry — win-back and renew messaging.</span>
              </button>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={busy}
                className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white"
                onClick={() => setOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
