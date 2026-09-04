# Desktop Licensing — Production Implementation Plan

This document tracks the **production** desktop licensing system in this repository.
The prior local BETA is reference-only architecture; nothing was recovered from beta Git history.

## Non-negotiable rule

**1 license key = 1 website user + 1 physical device + 1 product.**

No `max_devices=N`, no shared seats. Multiple installations require multiple paid keys.

Products: `QR_CODE`, `ASN_PDF_PRINTER`, `ASN_AUTO_FILLER`

Feature flag: `ENABLE_DESKTOP_LICENSING` (default **false**)

## Phase status

| Phase | Scope | Status |
|-------|--------|--------|
| 0 | Audit / gap | **Done** — production repo had no licensing tables/APIs |
| 1 | Foundation (schema, flag, service, admin/customer/machine routers, key crypto) | **Merged** (PR #31) |
| 2 | Admin catalog / pricing | **In review** |
| 3 | Customer orders | Not started |
| 4 | UPI payment approval + mint | Not started |
| 5 | Email + My Licenses | Not started |
| 6 | Protected installers / downloads | Not started |
| 7 | Machine License API (Ed25519) | Not started (stubs return 501) |
| 7A | 7-day trial system | Not started |
| 8+ | Desktop app integration (QR / ASN) | Explicitly deferred |

## Phase 0 — Gap summary

- No `032_*` licensing migration existed on production branches before this work.
- No `/api/license/*`, `/api/desktop/*`, or `ENABLE_DESKTOP_LICENSING`.
- Existing auth, companies, email, UPI settings, and migration runner are reusable.
- Identity must not be duplicated: licenses bind to `company_users` / `companies`.

## Phase 1 — What shipped

### Migration

- `saas/backend/migrations/032_desktop_licensing.sql`
  - Products, plans, orders, payments, licenses, devices, activations, events
  - Installers + download tokens (schema ready for Phase 6)
  - Seeds three products + annual 1-seat plans (placeholder INR)

### Backend package

- `saas/backend/app/licensing/` — models, constants, keys, service, feature flag, schemas, routers

### APIs (only when `ENABLE_DESKTOP_LICENSING=true`)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/admin/desktop/health` | Platform admin |
| GET | `/api/admin/desktop/products` | Platform admin catalog |
| GET | `/api/desktop/health` | Company user |
| GET | `/api/desktop/products` | Company user catalog |
| POST | `/api/license/activate` | **501 stub** (Phase 7) |
| POST | `/api/license/validate` | **501 stub** (Phase 7) |
| POST | `/api/license/refresh` | **501 stub** (Phase 7) |
| POST | `/api/license/deactivate` | **501 stub** (Phase 7) |
| GET | `/api/license/public-key` | **501 stub** (Phase 7) |

When the flag is **false**, all of the above return **404**.

`/health` exposes `enable_desktop_licensing` for ops visibility (not a secret).

### Secure key handling

- Server-side generation (`AQ-XXXX-…`)
- SHA-256 hash for lookup; optional Fernet ciphertext via `LICENSE_KEY_ENCRYPTION_SECRET`
- Plaintext returned only at mint time to the caller (later: email / reveal)
- Masking helper for UI defaults
- `LICENSE_SIGNING_PRIVATE_KEY` setting reserved for Phase 7 — **do not commit production keys**

### Service helpers ready for later phases

- `create_paid_license_row` / `create_paid_licenses_for_seats` (N independent keys)
- `record_license_event` audit rows

## Security notes (Phase 1)

- Private Ed25519 signing key is **not** generated or committed.
- Feature flag defaults off — schema can apply dark without exposing routes.
- No desktop app code in this phase; no localhost API fallbacks added.
- Rate limiting for machine endpoints lands with Phase 7 implementation.

## Explicitly out of scope until later phases

- Admin pricing UI, customer checkout/UPI, payment approval, emails, My Licenses UI
- Trial issuance / day-6 reminder / unique trial index (Phase 7A)
- Real activate/validate/refresh/deactivate + signed entitlements (Phase 7)
- QR_CODE / ASN_* desktop integration

## How to verify Phase 1

```bash
cd saas/backend
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/test_desktop_licensing_foundation.py -q
```

With DB + flag on (local): apply migrations via normal API startup, then call admin/customer health/products with JWTs.

## Phase 1 corrective patch (post review)

Addressed before Phase 2:

1. **Migration `033_desktop_licensing_one_active_device.sql`**
   - Partial unique index `uq_desktop_activations_one_active_per_license` on `(license_id) WHERE status = 'active'`
   - Fails closed if duplicate active rows exist (lists `license_id`s; **does not delete**)
2. **Fernet-only `LICENSE_KEY_ENCRYPTION_SECRET`**
   - Passphrase→SHA-256 derivation removed; mint fails without a valid Fernet key
3. **`app/licensing/binding.py`**
   - Service enforcement: wrong user / wrong product / other device → `LicenseBindingError`
   - Admin device reset helper (clears bind; does not reassign user/product)

**Production prerequisite for 033:** if any license already has >1 `status='active'` activation (unlikely on fresh 032), deactivate extras manually before applying 033.

## Phase 2 — Admin catalog / pricing

### APIs (`ENABLE_DESKTOP_LICENSING=true`, platform admin JWT)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/admin/desktop/products` | All products/plans including inactive |
| PATCH | `/api/admin/desktop/products/{id}` | name, description, listing_active, sort_order, buy_url_path |
| POST | `/api/admin/desktop/products/{id}/plans` | Create 1-seat plan |
| PATCH | `/api/admin/desktop/plans/{id}` | price_inr, listing, duration, code, name; seats forced to 1 |

### UI

- `/admin/desktop-licensing` — product/plan editors (nav + dashboard link)
- Disabled banner when API returns 404 (flag off)

### Out of scope for Phase 2

Orders, UPI, minting/emails, My Licenses, downloads, machine API, trials.

**Stop after Phase 2 for review** before Phase 3 customer orders.
