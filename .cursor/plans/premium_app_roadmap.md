---
name: Premium app roadmap
overview: "ZIP export UX (progress, ETA, no double-submit), asset-ready gating before PDF capture, PDF size target 100–200 KB per file, and faster batch generation without changing per-report quality or output size."
todos:
  - id: zip-progress-ux
    content: "InspectionResultsPage: determinate ZIP progress (e.g. Generating PDF 3/12), ETA from rolling average, disable button while zipping, clear success/error copy"
    status: completed
  - id: asset-ready-gate
    content: "fir_preview.html + InspectionResultsPage: wait for fonts/images (Quali data-URI, logo/signature imgs) before FIR_PREVIEW_API marks export-ready; optional generatePdfBlob pre-step"
    status: completed
  - id: pdf-size-target
    content: "Tune fir_preview.html html2pdf/html2canvas JPEG scale/quality to hit 100–200 KB typical; warn if over; document tradeoffs; optional server-side tuning"
    status: completed
  - id: faster-batch-same-output
    content: "Speed: capped parallel generatePdfBlob (e.g. 2–3) or queue; verify identical options per iframe so PDF bytes/quality unchanged vs sequential"
    status: completed
  - id: brand-logo-hybrid-svg
    content: "BrandLogo: hybrid lockup — inline SVG for Q group only (user stroke/circuit paths, viewBox ~0–140×140); wordmark remains HTML text (Tailwind) for responsive sizing; no SVG <text> for TheAIQualisys"
    status: completed
  - id: layout-trial-days-banner
    content: "Layout: banner below header (same slot as admin impersonation strip) showing company FIR trial days remaining for signed-in company users only — hide when platform admin impersonation strip is shown or user is not in company shell"
    status: completed
  - id: upgrade-page-fir-pricing-link
    content: "UpgradePage: section for used modules & pricing — v1 show single actionable row for FIR Automation linking to /workspace/pricing (workspace FIR pricing; handles plan selection + WhatsApp). Later extend from /api/modules/overview + module catalog when more modules ship"
    status: completed
  - id: workspace-pricing-annual-banner
    content: "PricingPage (variant=workspace only): horizontal promo banner — teal/sage palette, gift icon, headline + subline for annual prepay (pay for 11 months, get 12); CTA links to /upgrade with anchor or query annual=1 for WhatsApp context; responsive flex"
    status: completed
  - id: parts-master-uppercase-alphanumeric
    content: "PartsPage: Part number + Description inputs — force uppercase A–Z and 0–9 only (strip or block other chars on change); optional backend mirror validation on POST /api/app/parts"
    status: completed
  - id: parts-master-excel-duplicate-block
    content: "PartsPage onExcelPickForReview: after preview-excel-master returns bundle, compare each extracted part_no (case-insensitive trim) to loaded rows; if any match, set error, clear pending review, block save — user must remove duplicate from Excel or delete existing part first"
    status: completed
  - id: part-number-global-fe
    content: "Shared sanitizePartNo (or reuse part_field_validation parity): ManualEntryPage part number input onChange/paste; optional ExtractedPage editable Part Number column if we add inline edit — same [A-Z0-9] uppercase strip; normalize partMasterKeys lookups with sanitizer"
    status: completed
  - id: part-number-global-be
    content: "fir_excel.parse_invoice_excel: after building rows, sanitize Part Number column with same logic as sanitize_part_master_alnum_upper; fir_part_excel: normalize part_no strings when assigning from cells/sheets so Excel/section imports match Parts master"
    status: completed
---

# Roadmap: premium ZIP, asset readiness, size target, faster batches

## Scope (this iteration)

1. **ZIP progress**: Determinate **progress bar** (e.g. “Generating PDF 3/12”), **estimated time remaining** (rolling average of per-PDF duration), **disable** the ZIP button (and double-clicks) while building, **clear** success/error messaging.
2. **Consistent assets before capture**: Ensure **custom Quali TTF** and **logo/signature** images (DB `data:` URIs) are **fully loaded** before `generatePdfBlob` / before treating a preview as “export-ready.” Add explicit **ready** checks in `fir_preview.html` and wire `InspectionResultsPage` to preflight.
3. **PDF size target**: Aim for **~100–200 KB per PDF** file inside the ZIP (tune `html2canvas` scale + JPEG quality in `fir_preview.html`; optional soft warning if a file exceeds band after generation).
4. **Faster report generation** without changing **per-report** output: **no** intentional change to **visual quality** or **file-size policy** vs today’s sequential path—use **capped parallel** `generatePdfBlob` (e.g. concurrency 2–3) or an equivalent **queue** so total wall time drops while each iframe uses the **same** html2pdf options.

## Design tension (explicit)

- **100–200 KB** per page and **raster** html2pdf output are **tight**; hitting the band may require **compression/scale** settings that interact with quality. The plan treats **size target** as a **tunable goal** with QA on real FIRs; if the band conflicts with “no blur” on specific customers, **relax the band** or move **server-side print/vector PDF** (later phase).
- **Parallel PDF generation** does not change **intrinsic** PDF size/quality if each iframe runs the **same** `generatePdfBlob` code path; **verify** with a before/after byte/hash spot check on a sample row.

## Implementation notes

### A. ZIP progress + ETA (`InspectionResultsPage.tsx`)

- State: `zipCurrent`, `zipTotal`, `zipStartTime`, `lastDurations[]` for ETA.
- On each completed PDF: update progress; ETA = `avg(last N durations) * (total - current)`.
- `disabled={zipping}` on ZIP button; optional `aria-busy` / `aria-live` for screen readers.

### B. Asset-ready (`fir_preview.html`)

- On load: `document.fonts.ready` + wait for `img` with `src` starting with `data:` or `http` → `decode()` / `onload`.
- Extend `window.FIR_PREVIEW_API` with e.g. `assetsReady: boolean` or `waitForAssets(): Promise<void>` that `generatePdfBlob` **awaits** first.
- Parent page: before ZIP loop, **await** `waitForAssets` per iframe (or batch await).

### C. PDF 100–200 KB (`fir_preview.html`)

- Adjust **html2canvas** `scale` and **image** `quality` (and `firGrayscaleImageForPdf` JPEG factor if needed) toward the band; **measure** mean/median KB on sample reports.
- Optional: after each blob, `blob.size` — if > 200 KB, show non-blocking **warning** in batch message (do not fail ZIP unless product asks).

### D. Faster batches (same quality)

- Replace sequential `for` loop with a **pool** of `Promise` workers: `concurrency = min(3, n)`; assign indices; **await** all; **same** `generatePdfBlob` per index.
- **Load test**: 10-row batch — compare total seconds vs sequential; spot-check PDF **size** for row 1 vs old build.

## Files (primary)

- `saas/frontend/src/pages/workspace/InspectionResultsPage.tsx` — progress, ETA, parallel pool, button state.
- `saas/backend/templates/fir_preview.html` — asset wait, `generatePdfBlob` await, optional size tuning constants.

## Out of scope (unless later)

- Phase C **vector/Chromium print PDF** (separate plan for “premium print” if raster target is insufficient).
- **Skeletons** / lazy iframes — optional follow-up; parallel ZIP may increase memory; lazy load conflicts with “all previews ready” unless ordering is defined.

## Deferred from earlier plan

- Full **server-side PDF** service — keep as optional follow-up if client parallel is not enough.
- **Export history UI** — Phase D polish.

## Brand logo (hybrid SVG + HTML wordmark)

**Decision:** Use the user-provided **Q icon** geometry (outer circle, tail, circuit lines + nodes) as **inline SVG only**. Keep **“TheAIQualisys”** as **HTML text** next to the icon (same pattern as current `BrandLogo.tsx`), styled with Tailwind (`text-lg` / `sm:` breakpoints, `font-bold`, `tracking-tight`, `currentColor` via `text-*` on the parent).

**Why:** Responsive typography without editing SVG `x`/`y`/`font-size`; theme-aware color still flows from CSS; smaller SVG = less JSX to maintain.

**Implementation sketch:**

- Extract the `<g transform="translate(20,20)">` … `</g>` block from the 600×160 master; set a tight **`viewBox`** on the root `<svg>` around the icon bounds (e.g. `0 0 140 140` after normalizing translate—adjust so the icon crops cleanly).
- Convert attributes to **React camelCase** (`strokeWidth`, `strokeLinecap`, etc.).
- **`wordmark={false}`** path: icon-only span; **`wordmark` default true**: `inline-flex items-center gap-2` + icon + `<span>TheAIQualisys</span>`.

**Files:** `saas/frontend/src/components/BrandLogo.tsx` (primary).

## Company trial days banner (QMS shell — non-admin users)

**Goal:** Show **pending trial days** in the **same horizontal band** as the yellow “platform admin” impersonation banner (between global header and `<main>`), for **regular company users** — **not** when a platform admin is viewing the tenant (that slot stays the admin strip).

**Visibility rules**

- **Show** when: user has **`fir_token`**, **`showImpersonationBannerPath(pathname)`** is true (same routes as today: `/dashboard`, `/upgrade`, `/dashboard/*`, `/modules/*`), and **`trial_active`** (company still in FIR trial window).
- **Hide** when: **impersonation strip** is active (`fir_impersonating` + company token + same path rules) — admins keep the yellow banner only.
- **Hide** when: not logged in as company user, or trial no longer active (paid / expired) — optional copy for expired can be a separate follow-up.

**Data**

- Prefer **`GET /subscription/status`**: already returns **`trial_active`** and **`company`** (`trial_end_date`, `subscription_status`). Either:
  - **A (recommended):** add **`trial_days_remaining: int | null`** to `SubscriptionStatusResponse` computed server-side with the same `date` logic as `trial_is_valid` (avoids client timezone off-by-one on date-only strings), or
  - **B:** derive on the client from `company.trial_end_date` with careful **date-only** parsing.

**UI**

- Reuse **full-width** strip pattern from `Layout.tsx` (`impersonationBannerCls` sibling); use a **distinct** palette (e.g. sky/neutral info) so it is not confused with the **amber admin** warning.
- Copy example: “Your company trial ends in **N** day(s).” Optional link to **`/upgrade`** or **`/dashboard/billing`**.
- Fetch on route change / mount; handle loading and errors quietly (omit banner if fetch fails).

**Files (primary)**

- `saas/frontend/src/components/Layout.tsx` — conditional second strip for trial countdown.
- `saas/backend/app/routers/subscription.py` + `saas/backend/app/schemas.py` — optional `trial_days_remaining` on `/subscription/status`.
- `saas/frontend/src/api` usage — same `apiFetch` pattern as other pages.

## Upgrade page: modules used & pricing (FIR first)

**Goal:** On **`/upgrade`**, give users a clear path to see **which modules they use** and **pricing**, without replacing the manual UPI/WhatsApp flow.

**v1 (current product scope — FIR only aired):**

- Add a compact section **above or below** the intro paragraph on `UpgradePage.tsx` (theme-aware card), titled e.g. **“Your modules & pricing”**.
- Show **one row**: **FIR Automation** — short line that FIR billing is usage-based plans (optional one-line hint from existing `/subscription/plans` or static copy).
- Primary action: **`Link` to `/workspace/pricing`** with copy like **“View FIR pricing & plans”** — that route (`App.tsx` → `WorkspaceLayout` → `PricingPage variant="workspace"`) already lists FIR plans and WhatsApp upgrade; user must be logged in (same as Upgrade).

**Not in v1:** Full dynamic matrix of all QMS modules from `/api/modules/overview` until those modules are productized the same way; then extend the section to list rows per module with links to `/pricing/modules/:slug` or workspace equivalents.

**Files:** `saas/frontend/src/pages/UpgradePage.tsx` (primary); optional thin helper or copy constants if the section grows.

## Workspace FIR pricing: annual savings banner

**Where:** `PricingPage.tsx` when **`variant === "workspace"`** (`/workspace/pricing`) — insert **below the hero** (H1 + lead) and **above the plan grid** so it frames the monthly cards with an annual alternative.

**Visual (inspired by reference):** Full-width (within `max-w-*` container) **rounded-xl** bar; **soft sage / mint** background (`bg-emerald-50` or `bg-teal-50`); **teal** text and **outline** CTA; optional small **gift** SVG inline (no new asset file) or emoji fallback for accessibility.

**Copy (effective, honest):**

- **Headline:** e.g. *“Prefer annual billing? Pay for 11 months, get 12.”* (clearer than “save 20%” when the product promise is one free month).
- **Subline (optional):** *“Same FIR usage caps — we’ll confirm your plan and activate after payment on WhatsApp.”*
- **CTA:** *“Ask for annual on WhatsApp”* or *“Upgrade — annual”* → links to **`/upgrade`** (manual flow). Optionally append query e.g. **`?billing=annual`** and teach `UpgradePage` / WhatsApp prefill to mention annual so support can quote **11× monthly** as yearly total.

**Scope guard:** Show **only** for workspace variant; marketing `/pricing` can omit or use shorter strip later.

**Files:** `saas/frontend/src/pages/PricingPage.tsx`; optional `UpgradePage.tsx` query-param handling for WhatsApp message if we add `billing=annual`.

## Parts master: uppercase alphanumeric fields + Excel duplicate guard

**Goal:** On **`/workspace/parts`**, keep **Part number** and **Description** aligned to **uppercase letters and digits only** (no spaces, punctuation, or lowercase). On **Upload Excel**, after the server parses the workbook (`POST /api/app/parts/preview-excel-master`), **block** proceeding to review/save if **any** extracted part number already exists in the current tenant’s part master (same behavior as “no duplicate part numbers”).

### Uppercase + allowed charset (UI)

- **Fields:** **Part number** and **Description** in the New part / Update part form (`PartsPage.tsx`).
- **Behavior:** On each keystroke/paste, normalize to **uppercase** and **drop** (or reject) any character outside **`[A-Z0-9]`**. Empty description remains allowed unless product later requires non-empty.
- **Edit mode:** When loading a row for edit, run the same sanitizer on initial values so legacy mixed-case data becomes consistent on next save.
- **Optional hardening:** Mirror validation in FastAPI on create/update (`schemas` / parts router) so API clients cannot bypass the rule.

### Excel: duplicate detection vs part master

- **When:** Immediately after a successful **`preview-excel-master`** response, before opening **`PartMasterExcelReview`** (or right after setting state — same net effect).
- **Data:** Build a **`Set`** of normalized keys from `rows` already loaded: `part_no.trim().toLowerCase()` (or uppercase — one canonical form).
- **Check:** For each `bundle.parts[].part.part_no`, normalize the same way; if **any** key is in the set, **do not** show the review modal as a valid import path for that file:
  - **`setErr`** with a clear message listing **which part number(s)** conflict (cap list length, e.g. first 5 + “and N more”).
  - **`setPendingExcelBundle(null)`**, clear file label, **do not** call `confirmExcelImport` until the user fixes the Excel or removes the existing part from master.
- **Edge case:** Multiple **new** rows in the same Excel with the **same** part number — optionally flag as duplicate-within-file (nice-to-have); primary requirement is **no overlap with server-backed master list**.

**Files (primary):** `saas/frontend/src/pages/workspace/PartsPage.tsx`; optional `saas/backend/app/routers` + `schemas` for server-side charset validation.

## Part number normalization everywhere (FIR flows)

**Rule (same as Parts master part number):** On input (including paste), **uppercase** and **only `[A-Z0-9]`** — strip everything else.

**Already done:** `PartsPage.tsx` (part number field), backend `sanitize_part_master_alnum_upper` on workspace parts APIs and bundle import.

**Frontend — still apply the shared helper**

- **`ManualEntryPage.tsx`**: Part Number text inputs — wire `onChange` to the same sanitizer as Parts page; when comparing to Parts master (`partMasterKeys`), normalize both sides with the sanitizer + lowercase key (or compare sanitized strings).
- **`ExtractedPage.tsx`**: Read-only table today; if Part Number becomes editable, use the same sanitizer. If it stays read-only, normalization can be **server-side** on upload so the preview table shows canonical values (see backend).
- **Optional:** Move `sanitizePartMasterAlnumUpper` to e.g. `saas/frontend/src/utils/partFields.ts` and import from `PartsPage` + `ManualEntryPage` to avoid drift.

**Backend — canonical values at parse time**

- **`fir_excel.py` (`parse_invoice_excel`)**: After building each row’s `"Part Number"` string, apply **`sanitize_part_master_alnum_upper`** so invoice Excel upload → extracted → inspection all see the same part keys as Parts master.
- **`fir_part_excel.py`**: When setting `part_no` from sheet cells or grouped keys, apply the same sanitizer so part master Excel import/review matches DB and FIR rows.

**Out of scope for this rule:** Admin read-only tables that only **display** `part_no` from the API (no user typing).
