import { useState } from "react";
import { apiFetch } from "../api";

type SendResponse = {
  ok?: boolean;
  email_status: string;
};

type PreviewResponse = {
  subject: string;
  message: string;
  invoice_number: string | null;
  invoice_attached: boolean;
  recipient_count: number;
  recipients: string[];
};

type ReminderType = "ending_soon" | "already_ended" | "trial_ending" | "payment_overdue" | "thank_you";

type Props = {
  companyId: number;
  /** Compact style for table cells (smaller button, no full-width feedback). */
  variant?: "default" | "inline";
};

const THANK_YOU_CATEGORIES = [
  { value: "running", label: "Running" },
  { value: "regular", label: "Regular" },
  { value: "occasional", label: "Occasional" },
  { value: "stranger", label: "Stranger" },
  { value: "new", label: "New" },
  { value: "all", label: "All — combined message" },
] as const;

type ThankYouCategory = (typeof THANK_YOU_CATEGORIES)[number]["value"];

type ModalStep = "menu" | "thankYouCategory" | "edit";

export function AdminSubscriptionReminderButton({ companyId, variant = "default" }: Props) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<ModalStep>("menu");
  const [thankYouCategory, setThankYouCategory] = useState<ThankYouCategory>("running");
  const [reminderType, setReminderType] = useState<ReminderType | null>(null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [invoiceNote, setInvoiceNote] = useState<string | null>(null);
  const [recipientCount, setRecipientCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("Sending…");
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null);

  function hideModal() {
    setOpen(false);
    setStep("menu");
    setReminderType(null);
    setSubject("");
    setMessage("");
    setInvoiceNote(null);
  }

  async function loadPreview(type: ReminderType, category?: ThankYouCategory) {
    setBusy(true);
    setBusyLabel("Loading…");
    setFeedback(null);
    try {
      const payload: Record<string, string> = { reminder_type: type };
      if (type === "thank_you") payload.thank_you_category = category || thankYouCategory;
      const res = await apiFetch<PreviewResponse>(
        `/admin/companies/${companyId}/subscription-reminder/preview`,
        { method: "POST", token: "admin", body: JSON.stringify(payload) },
      );
      setReminderType(type);
      setSubject(res.subject);
      setMessage(res.message);
      setRecipientCount(res.recipient_count);
      setInvoiceNote(
        res.invoice_attached && res.invoice_number
          ? `${res.invoice_number}.pdf will be attached`
          : null,
      );
      setStep("edit");
    } catch (e) {
      setFeedback({
        ok: false,
        text: e instanceof Error ? e.message : "Could not load message.",
      });
      hideModal();
    } finally {
      setBusy(false);
    }
  }

  async function sendEdited() {
    if (!reminderType) return;
    const sub = subject.trim();
    const msg = message.trim();
    if (!sub || !msg) {
      setFeedback({ ok: false, text: "Subject and message are required." });
      return;
    }
    setBusy(true);
    setBusyLabel("Sending…");
    setFeedback(null);
    try {
      const payload: Record<string, string> = {
        reminder_type: reminderType,
        subject: sub,
        message: msg,
      };
      if (reminderType === "thank_you") payload.thank_you_category = thankYouCategory;
      const res = await apiFetch<SendResponse>(`/admin/companies/${companyId}/subscription-reminder`, {
        method: "POST",
        token: "admin",
        body: JSON.stringify(payload),
      });
      const text = res.email_status === "partial" ? "Email sent (not all recipients)." : "Email sent.";
      setFeedback({ ok: true, text });
      hideModal();
    } catch {
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
      : "inline-flex h-10 shrink-0 items-center justify-center rounded-lg border border-amber-600/50 bg-amber-950/30 px-4 text-sm font-medium text-amber-100 hover:bg-amber-950/50 disabled:opacity-50";

  return (
    <div
      className={
        variant === "inline"
          ? "inline-flex flex-col items-start text-left"
          : "inline-flex flex-col items-start"
      }
    >
      <button
        type="button"
        className={btnClass}
        disabled={busy}
        onClick={() => {
          setStep("menu");
          setOpen(true);
        }}
      >
        {busy ? busyLabel : "Reminder"}
      </button>
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
          onClick={() => {
            if (!busy) hideModal();
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={
              step === "menu"
                ? "reminder-modal-title"
                : step === "edit"
                  ? "reminder-edit-title"
                  : "thank-you-category-title"
            }
            className={`${step === "edit" ? "max-w-3xl" : "max-w-lg"} rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl max-h-[90vh] overflow-y-auto w-full`}
            onClick={(e) => e.stopPropagation()}
          >
            {step === "menu" ? (
              <>
                <h3 id="reminder-modal-title" className="text-lg font-semibold text-white">
                  Send subscription reminder
                </h3>
                <p className="mt-2 text-sm text-slate-400">
                  Choose the message type. You will review and can edit the full email before it is sent to every
                  non-blocked workspace user for this company.
                </p>
                <div className="mt-6 flex flex-col gap-3">
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                    onClick={() => void loadPreview("trial_ending")}
                  >
                    <span className="font-medium text-white">Trial users — subscribe reminder</span>
                    <span className="mt-1 block text-xs text-slate-400">
                      Trial ending or ended — ask them to subscribe so work is not interrupted.
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                    onClick={() => void loadPreview("ending_soon")}
                  >
                    <span className="font-medium text-white">Subscription Ending Soon</span>
                    <span className="mt-1 block text-xs text-slate-400">
                      Expires on date — renewal encouragement before lapse.
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                    onClick={() => void loadPreview("already_ended")}
                  >
                    <span className="font-medium text-white">Subscription Already Ended</span>
                    <span className="mt-1 block text-xs text-slate-400">
                      Past expiry — win-back and renew messaging.
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                    onClick={() => void loadPreview("payment_overdue")}
                  >
                    <span className="font-medium text-white">Payment overdue — settle before we close ties</span>
                    <span className="mt-1 block text-xs text-slate-400">
                      Days overdue, Pay now, bank / UPI / GSTIN, previous invoice attached, deadline after the 30th we
                      close all ties.
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-left text-sm text-slate-100 hover:bg-slate-800 disabled:opacity-50"
                    onClick={() => setStep("thankYouCategory")}
                  >
                    <span className="font-medium text-white">Thank You &amp; Performance Summary</span>
                    <span className="mt-1 block text-xs text-slate-400">
                      Send a thank-you email with detailed usage analytics and business impact.
                    </span>
                  </button>
                </div>
                <div className="mt-6 flex justify-end gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white"
                    onClick={() => {
                      if (!busy) hideModal();
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : step === "edit" ? (
              <div className="flex max-h-[min(40rem,85vh)] flex-col">
                <h3 id="reminder-edit-title" className="text-lg font-semibold text-white">
                  Review and edit message
                </h3>
                <p className="mt-2 text-sm text-slate-400">
                  This is the complete email. Edit the subject or body, then send. Goes to {recipientCount} recipient
                  {recipientCount === 1 ? "" : "s"}.
                  {invoiceNote ? ` ${invoiceNote}.` : ""}
                </p>
                <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
                  <div>
                    <label htmlFor="reminder-subject" className="block text-xs font-medium text-slate-500">
                      Subject
                    </label>
                    <input
                      id="reminder-subject"
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                      value={subject}
                      disabled={busy}
                      onChange={(e) => setSubject(e.target.value)}
                    />
                  </div>
                  <div>
                    <label htmlFor="reminder-message" className="block text-xs font-medium text-slate-500">
                      Message
                    </label>
                    <textarea
                      id="reminder-message"
                      rows={18}
                      className="mt-1 w-full resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs leading-relaxed text-slate-100"
                      value={message}
                      disabled={busy}
                      onChange={(e) => setMessage(e.target.value)}
                    />
                  </div>
                </div>
                <div className="mt-4 flex shrink-0 flex-wrap justify-end gap-2 border-t border-slate-800 pt-4">
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white"
                    onClick={() => setStep("menu")}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={busy || !subject.trim() || !message.trim()}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-50"
                    onClick={() => void sendEdited()}
                  >
                    {busy ? busyLabel : "Send email"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex max-h-[min(32rem,85vh)] flex-col">
                <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
                  <h3 id="thank-you-category-title" className="text-lg font-semibold text-white">
                    Thank You &amp; Performance Summary
                  </h3>
                  <p className="text-sm text-slate-400">
                    Choose the tone of the message (or <strong className="text-slate-300">All</strong> for one email that
                    speaks to every part engagement category). You can review and edit the full email next.
                  </p>
                  <div>
                    <label htmlFor="thank-you-category" className="block text-xs font-medium text-slate-500">
                      Category
                    </label>
                    <select
                      id="thank-you-category"
                      className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                      value={thankYouCategory}
                      disabled={busy}
                      onChange={(e) => setThankYouCategory(e.target.value as ThankYouCategory)}
                    >
                      {THANK_YOU_CATEGORIES.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="mt-4 flex shrink-0 flex-wrap justify-end gap-2 border-t border-slate-800 pt-4">
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white"
                    onClick={() => setStep("menu")}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-500 disabled:opacity-50"
                    onClick={() => void loadPreview("thank_you", thankYouCategory)}
                  >
                    {busy ? busyLabel : "Review message"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
