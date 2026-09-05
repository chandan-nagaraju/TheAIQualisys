# Desktop OAuth 2.0 (Authorization Code + PKCE) — Phase 9C-B

**Status:** Foundation implemented in code. **Production deployment is NOT AUTHORIZED.**

This document describes the AIQualisys-side contract for native desktop public clients
(starting with QR Code Desktop). QR desktop integration happens in a later phase.

## Goals

- Desktop apps obtain a **short-lived company access JWT** without copying tokens by hand.
- Authorization **code** is the only credential allowed in browser redirects.
- Refresh tokens rotate server-side and are stored as hashes only.
- Existing SPA login (`POST /auth/login`, `POST /auth/unified-login`) is unchanged.
- Platform-admin auth is unchanged.
- Licensing machine API auth (`get_current_company_user`) remains authoritative.
- `ENABLE_DESKTOP_LICENSING` stays independent (default **false**).

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/oauth/authorize` | none | Validate request; 302 to SPA consent UI |
| GET | `/oauth/authorize/preview` | company Bearer | Consent page metadata |
| POST | `/oauth/authorize/consent` | company Bearer | Approve/deny → redirect with `code` |
| POST | `/oauth/token` | public client | `authorization_code` or `refresh_token` |
| POST | `/oauth/revoke` | company Bearer | Revoke one family or all sessions for client |

Same routes are also mounted under `/api/...`.

### Authorize query

Required:

- `response_type=code`
- `client_id`
- `redirect_uri` (exact match against registration)
- `scope` (currently `desktop_license`)
- `state` (required; see **State (desktop client duty)** below)
- `code_challenge`
- `code_challenge_method=S256`

### State (desktop client duty)

The authorization server **requires** `state`, stores/echoes it unchanged on success and
error redirects, and does **not** perform server-side CSRF binding of `state` to a
browser session.

The **desktop client MUST**:

1. Generate a cryptographically random `state` value for each authorization attempt.
2. Retain that value locally for the pending authorization.
3. Validate that the callback `state` exactly matches the retained value.
4. Reject the callback if `state` is missing or does not match.
5. Discard `state` after a successful or failed authorization completes.

`state` protects the desktop client from authorization-response mix-up / CSRF
(an attacker completing an authorization in the user’s browser and tricking the
desktop app into consuming that response).

### Token (authorization_code)

Form or JSON:

- `grant_type=authorization_code`
- `code`
- `client_id`
- `redirect_uri`
- `code_verifier`

### Token (refresh_token)

- `grant_type=refresh_token`
- `refresh_token`
- `client_id`

### Success token response

```json
{
  "access_token": "<company JWT>",
  "token_type": "Bearer",
  "expires_in": 1800,
  "refresh_token": "<opaque>",
  "scope": "desktop_license"
}
```

### OAuth errors

`invalid_request`, `invalid_client`, `invalid_grant`, `invalid_scope`,
`unauthorized_client`, `access_denied`, `unsupported_grant_type`,
`unsupported_response_type`, `server_error`.

Tokens/codes/verifiers are never returned in error bodies or logs.

## Client registration

Table: `oauth_desktop_clients`

- Public clients only (no client secret)
- Exact redirect URI allow-list
- Allowed scopes allow-list
- `enabled` flag (default 0)

### Staging-only placeholders (do not create in production)

```
STAGING_OAUTH_CLIENT_ID=qr-code-desktop-staging
STAGING_OAUTH_REDIRECT_URI=aiqualisys-qr://oauth/callback
STAGING_OAUTH_ALLOWED_SCOPES=desktop_license
```

Conceptual redirect for QR: `aiqualisys-qr://oauth/callback` (design value until QR registers it).

Example staging insert (run only against an isolated staging DB):

```sql
INSERT INTO oauth_desktop_clients (
  client_id, client_name, client_type, redirect_uris, allowed_scopes, enabled
) VALUES (
  'qr-code-desktop-staging',
  'QR Code Desktop',
  'public',
  '["aiqualisys-qr://oauth/callback"]'::jsonb,
  '["desktop_license"]'::jsonb,
  1
);
```

## PKCE

- Method: **S256 only**
- `code_verifier`: 43–128 unreserved characters
- `code_challenge`: BASE64URL(SHA256(verifier)) without padding
- Authorization codes: random, **1–5 minutes** TTL (default 180s), single-use, hashed at rest
- Bound to `client_id`, `redirect_uri`, `code_challenge`, and authenticated user

## Access JWT (desktop)

Compatible with `get_current_company_user` / licensing:

- `sub` — company user id
- `company_id`
- `typ` = `company`
- `exp`
- also: `iat`, `iss=aiqualisys`, `aud=aiqualisys-desktop`, `client_id`, `scope`, `amr`

Lifetime: **15–60 minutes** (default 30). SPA tokens remain ~7 days and omit desktop `aud`.

Must **not** include: platform-admin identity, license keys, MachineGuid, fingerprints, entitlement tokens.

Ed25519 entitlement signing remains separate.

## Refresh tokens

- Opaque, hashed at rest
- Family id; rotate on every refresh; previous token invalidated
- Replay of a rotated token revokes the **entire family**
- Default lifetime: 90 days
- Never appear in redirects or logs

## Revocation

Revoke on:

- `POST /oauth/revoke` (this desktop / all for client)
- user blocked
- password change / reset (company user)
- membership mismatch on refresh

Browser logout does **not** automatically revoke desktop sessions unless revoke is called.

## Admin impersonation (hard rule)

Platform-admin impersonation JWTs (`impersonated_by_admin=true` on a company token)
may continue to access SPA support surfaces, but **must never** authorize desktop OAuth.

`GET /oauth/authorize/preview`, `POST /oauth/authorize/consent`, and `POST /oauth/revoke`
reject impersonated sessions with `access_denied`. A platform-admin JWT cannot call these
routes successfully either (`typ` must be `company` via a direct company login).

## Scopes

- Scopes are validated at authorization against the client allow-list and `SUPPORTED_SCOPES`.
- The issued desktop access JWT includes the granted `scope` claim.
- **Current limitation:** `get_current_company_user` (and therefore company APIs / licensing)
  does **not** enforce OAuth scope as an API authorization boundary. A valid short-lived
  company JWT can call company endpoints regardless of `scope`. Do not claim scope provides
  API isolation today. Future hardening may add scope checks where appropriate.
- Licensing machine API checks (`licensed_user_id`, membership, product, fingerprint, 1:1:1)
  are unchanged and are not weakened by OAuth.

## Rate limiting

OAuth endpoints use an **in-process** limiter.

**NON-DISTRIBUTED / STAGING-ONLY HARDENING.** Multi-worker production deployments require
a distributed rate limiter. Do not treat the current limiter as production-grade.

## Security rules

- Never put JWT/refresh token in URL query, history, clipboard, email, or license key
- Do not use `?token=` / `get_bearer_token_or_query` for this flow
- Exact redirect URI matching
- Rate limits on authorize/token/consent/revoke (see Rate limiting)
- Desktop client must validate `state` (see State)
- Admin impersonation cannot authorize desktop sessions
- Audit events without secrets
- `oauth_authorization_codes.client_id` and `oauth_refresh_sessions.client_id` FK to
  `oauth_desktop_clients.client_id` (migration 038)

## Audit events

- `desktop_authorization_started`
- `desktop_authorization_granted`
- `desktop_authorization_denied`
- `desktop_token_issued`
- `desktop_token_refreshed`
- `desktop_refresh_replay_detected`
- `desktop_session_revoked`

## Migration

`038_desktop_oauth_pkce.sql` — additive tables only. Do not apply to production from this agent.

## Staging requirements

Isolated staging portal, API, DB, JWT secrets, Ed25519 licensing key, CORS, frontend, staging QR build, test company/user/licenses/trial, staging OAuth client. Never copy production credentials. Keep production licensing disabled.

## QR high-level flow (later)

QR → system browser → AIQualisys login → consent → authorization code → secure token exchange → company JWT + refresh → `/api/license/*` → entitlement token → offline until `naf`.

## Production

**NOT AUTHORIZED.** Do not register production clients, do not enable production licensing, do not deploy this foundation to production without explicit approval.
