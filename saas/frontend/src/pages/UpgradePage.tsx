import { useEffect, useState } from "react";
import { apiFetch } from "../api";

type UpgradeInfo = { upi_id: string; whatsapp_url: string; message: string };

export default function UpgradePage() {
  const [info, setInfo] = useState<UpgradeInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setInfo(await apiFetch<UpgradeInfo>("/subscription/upgrade-info"));
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load");
      }
    })();
  }, []);

  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-slate-800 bg-slate-900/60 p-8">
      <h1 className="text-2xl font-semibold text-white">Upgrade (manual payment)</h1>
      <p className="mt-2 text-sm text-slate-400">
        We use a simple UPI + WhatsApp flow. After you pay, send the screenshot on WhatsApp; our admin activates your
        subscription.
      </p>
      {err && <p className="mt-4 text-sm text-red-400">{err}</p>}
      {info && (
        <div className="mt-8 space-y-4">
          <div className="rounded-xl border border-slate-700 bg-slate-950/80 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">UPI ID</p>
            <p className="mt-1 font-mono text-lg text-white">{info.upi_id}</p>
          </div>
          <p className="text-sm text-slate-300">{info.message}</p>
          <a
            href={info.whatsapp_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-full justify-center rounded-lg bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-500"
          >
            Open WhatsApp with message
          </a>
        </div>
      )}
    </div>
  );
}
