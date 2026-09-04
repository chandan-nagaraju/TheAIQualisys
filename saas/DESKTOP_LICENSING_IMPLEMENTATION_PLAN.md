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
| 2 | Admin catalog / pricing | **Merged** (PR #32) |
| 3 | Customer orders | **Merged** (PR #33) |
| 4 | UPI payment approval + mint | **Merged** (PR #34) |
| 5 | Email + My Licenses | **Merged** (PR #35) |
| 6 | Protected installers / downloads | **Merged** (PR #36) |
| 7 | Machine License API (Ed25519) | **In review** |
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

## Phase 3 — Customer orders

### Migration
- `034_desktop_order_numbers.sql` — `order_number` (TAQ-YYYY-######), catalog snapshots, sequence counter table

### Customer APIs (`ENABLE_DESKTOP_LICENSING=true`)
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/desktop/checkout-context` | company + email for confirm |
| POST | `/api/desktop/orders` | create pending_payment order; no licenses |
| GET | `/api/desktop/orders` | own orders only |
| GET | `/api/desktop/orders/{id}` | own order only |

### Admin (read-only prep)
| GET | `/api/admin/desktop/orders` | list; no approve/reject |

### UI
- `/software` catalog, `/software/:productCode` plan+seats+confirm, `/software/orders`, `/software/orders/:orderId`

### Out of scope
UPI/UTR/screenshot, payment approval, license mint, email, downloads, machine API, trials, desktop apps.

## Phase 4 — Payment + admin approval + license minting

### Migration
- `035_desktop_payment_and_mint.sql` — `desktop_upi_settings`, unique `(order_id, seat_index)` on licenses, one `pending_review` payment per order

### Payment state transitions
- Order: `pending_payment` → (UTR submit) → `payment_submitted` → (approve) → `approved` | (reject) → `pending_payment`
- Payment: `pending_review` → `approved` | `rejected`
- UTR submit never auto-approves

### License state on approve
- Mint exactly `order.seats` independent keys (`issued`, device unbound, paid entitlement, expiry from `duration_days`)
- Idempotent: re-approve → 409; existing licenses for order → 409

### APIs
Customer: `GET /upi-settings`, `GET|POST .../orders/{id}/payments`
Admin: `GET|PUT /upi-settings`, `GET /payment-requests`, `POST .../approve`, `POST .../reject`

### UI
- Order detail payment instructions + UTR form
- `/admin/desktop-payments`

### Out of scope
Email, My Licenses reveal UI, downloads, machine API, trials, desktop apps, production secrets.

### Post–Phase 4 security hardening backlog (accepted, non-blocking)

Recorded from the Phase 4 security review approval. Do **not** treat as Phase 5 scope unless scheduled; implement as follow-up hardening:

1. Map duplicate pending-payment `IntegrityError` to HTTP 409.
2. Document recovery procedure for licenses existing without an approved payment.
3. Add screenshot magic-byte validation.
4. Add authenticated admin screenshot retrieval if screenshot review is required.
5. Add deeper Postgres integration tests for locks / unique constraints.
6. Add explicit test that approve responses never expose `key_encrypted` / plaintext.
7. Add test that company JWT cannot access admin approval endpoints.

## Phase 5 — My Licenses + reveal + license email

### Migration
- `036_desktop_license_email.sql` — `desktop_license_email_deliveries` (one row per order: pending/sent/failed, attempt tracking)

### Customer
- `/software/licenses` — My Licenses (masked keys, reveal/copy, resend email)
- APIs: `GET /licenses`, `GET /licenses/{id}`, `POST /licenses/{id}/reveal`, `POST /orders/{id}/resend-license-email`

### Admin
- `/admin/desktop-licenses` — masked metadata + resend
- Explicit audited `POST /licenses/{id}/reveal` (not used by default UI)

### Email
- After approve mint commits, send license email separately (failure does not roll back licenses)
- Resend never remints; rate-limited

### Out of scope
Downloads, machine activation, trials, QR/ASN desktop, payment gateway, production secrets.

## Phase 6 — Software management + protected downloads

### Schema
- Reuses `desktop_installers` + `desktop_download_tokens` from `032`
- **No migration 037** — service enforces exclusive current/recommended/mandatory channels

### Storage
- Private S3 (or `INSTALLER_STORAGE_BACKEND=memory` for tests)
- Keys: `desktop-installers/{product_code}/{version}/{safe_filename}`
- Never uses `PUBLIC_S3_BASE_URL` / permanent public URLs / AWS credentials in responses

### Entitlement
Paid license, `licensed_user_id` match, status issued/active, wall-clock `expires_at`, no device binding.
Installer must be published, not archived, file present.

### Tokens
Opaque single-use, hash-only storage, TTL 60–300s; redeem re-checks entitlement + installer eligibility; concurrent redeem → one success.

### Version history
Entitled customers may download any **published** version; archived/unpublished admin-only; no hard delete.

### APIs / UI
Admin: `/admin/desktop-installers` + `/api/admin/desktop/.../installers*`
Customer: `/software/downloads` + `/api/desktop/downloads*`

### Out of scope
Machine activation, trials, QR/ASN desktop integration, payment gateway, prod deploy/migrate/flag.

## Phase 7 — Machine License API + signed entitlements

### Status
**In review** on `cursor/desktop-licensing-phase07-64b6` (not merged; flag remains false).

### Schema
- Reuses `desktop_licenses`, `desktop_devices`, `desktop_activations`, `desktop_license_events`
- Reuses `uq_desktop_activations_one_active_per_license` (migration `033`)
- **No migration 037** — deactivation/reset reasons live in audit `meta_json`

### Machine APIs (feature-flagged)
| Method | Path | Auth |
|--------|------|------|
| POST | `/api/license/activate` | Company JWT + license key |
| POST | `/api/license/validate` | Company JWT |
| POST | `/api/license/refresh` | Company JWT |
| POST | `/api/license/deactivate` | Company JWT |
| GET | `/api/license/public-key` | None (informational) |
| POST | `/api/admin/desktop/licenses/{id}/reset-device` | Platform admin + reason |

### Binding
- 1 key = 1 user + 1 device + 1 product
- First activate: `issued` → `active`, set `bound_device_id`
- Same device: reaffirm
- Other device: `409 device_bound`
- Wall-clock `expires_at` always overrides stale issued/active
- Phase 7 accepts **paid** entitlements only (trials → 7A)
- Client deactivate marks activation deactivated but **preserves** `bound_device_id`
- Admin reset clears binding; does not auto-activate replacement

### Concurrent activation
- `SELECT … FOR UPDATE` on license + partial unique active index
- `IntegrityError` → deterministic `device_bound`

### Signed entitlement (Ed25519)
- Private key: `LICENSE_SIGNING_PRIVATE_KEY` (server-only; fail closed → `503 signing_unavailable`)
- Token: `base64url(canonical_json).base64url(sig)`
- Claims: `v, iss, aud, jti, license_id, activation_id, uid, fp, ent, iat, nbf, exp?, naf, st`
- `naf = min(expires_at, iat + LICENSE_MAX_OFFLINE_DAYS)` (default **14 days**)
- Desktop must **pin** public key in signed release; `GET /public-key` is **not** the trust root

### Offline / revocation tradeoff
A revoked/suspended license on a fully offline PC may remain usable until local `naf`.
Mitigation: finite offline window + periodic online refresh. Instant remote kill of offline devices is not promised.

### Rate limiting
- Wires `LICENSE_API_RATE_LIMIT_PER_MINUTE` (default 30) with tighter activate buckets
- **Limitation:** in-process sliding window — not distributed across multi-worker production.
  Prefer edge/gateway or Redis limits as non-blocking hardening.

### Error codes
`not_authenticated`, `invalid_license`, `wrong_user`, `wrong_product`, `expired`, `revoked`,
`suspended`, `device_bound`, `invalid_device`, `signing_unavailable`, `rate_limited`,
`invalid_request`, `trial_not_supported`

### Audit events
`license_activated`, `license_reaffirmed`, `license_validated`, `license_refreshed`,
`license_deactivated_client`, `license_device_reset` — never log plaintext keys, tokens, or secrets.

### Fingerprint (server)
- Expects opaque SHA-256 hex (64 chars) only
- Future desktop: `SHA-256("AQ|" + product_code + "|" + MachineGuid)`
- No raw MachineGuid collection on server

### Production prerequisites (before enabling flag)
1. Stable production Ed25519 private key in secret store
2. Matching public key pinned in released desktop builds
3. Migrations 032–036 applied
4. Rate limits / monitoring / admin reset runbook
5. Key rotation plan
6. **`ENABLE_DESKTOP_LICENSING` remains false until signed off**

### Out of scope (Phase 7)
- Trials (7A)
- QR / ASN desktop integration (Phase 8+)
- Token denylist / `token_epoch`
- Production deploy, migrate, secrets, flag enablement

### Known non-blocking hardening
- Distributed rate limiting
- Dual-key rotation UX
- Optional `token_epoch` for faster offline revoke
- Broader HTTP multi-tenant integration tests under real Postgres concurrency
