"""Desktop licensing constants.

Product codes are stable identifiers used by desktop apps and the API.
One license key binds to exactly one website user + one device + one product.
"""

from __future__ import annotations

PRODUCT_QR_CODE = "QR_CODE"
PRODUCT_ASN_PDF_PRINTER = "ASN_PDF_PRINTER"
PRODUCT_ASN_AUTO_FILLER = "ASN_AUTO_FILLER"

DESKTOP_PRODUCT_CODES: tuple[str, ...] = (
    PRODUCT_QR_CODE,
    PRODUCT_ASN_PDF_PRINTER,
    PRODUCT_ASN_AUTO_FILLER,
)

ENTITLEMENT_PAID = "paid"
ENTITLEMENT_TRIAL = "trial"

LICENSE_STATUS_ISSUED = "issued"  # pending first activation
LICENSE_STATUS_ACTIVE = "active"
LICENSE_STATUS_EXPIRED = "expired"
LICENSE_STATUS_REVOKED = "revoked"
LICENSE_STATUS_SUSPENDED = "suspended"

ORDER_STATUS_PENDING_PAYMENT = "pending_payment"
ORDER_STATUS_PAYMENT_SUBMITTED = "payment_submitted"
ORDER_STATUS_APPROVED = "approved"
ORDER_STATUS_REJECTED = "rejected"
ORDER_STATUS_CANCELLED = "cancelled"

PAYMENT_STATUS_SUBMITTED = "submitted"  # legacy alias; prefer pending_review
PAYMENT_STATUS_PENDING_REVIEW = "pending_review"
PAYMENT_STATUS_APPROVED = "approved"
PAYMENT_STATUS_REJECTED = "rejected"

# Screenshot upload limits (customer payment proof)
PAYMENT_SCREENSHOT_MAX_BYTES = 5 * 1024 * 1024
PAYMENT_SCREENSHOT_ALLOWED_MIME = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/jpg"}
)

ACTIVATION_STATUS_ACTIVE = "active"
ACTIVATION_STATUS_DEACTIVATED = "deactivated"

INSTALLER_CHANNEL_CURRENT = "current"
INSTALLER_CHANNEL_RECOMMENDED = "recommended"
INSTALLER_CHANNEL_MANDATORY = "mandatory"
INSTALLER_CHANNEL_ARCHIVED = "archived"

TRIAL_DURATION_DAYS = 7
TRIAL_REMINDER_DAY = 6

# Machine API rate-limit defaults (per IP+route window). Tunable via settings later.
LICENSE_API_RATE_LIMIT_PER_MINUTE = 30

PHASE_FOUNDATION = "1-foundation"
PHASE_EMAIL_LICENSES = "5-email-licenses"

# License email delivery statuses (per order; never remints on retry)
LICENSE_EMAIL_PENDING = "pending"
LICENSE_EMAIL_SENT = "sent"
LICENSE_EMAIL_FAILED = "failed"

# Resend rate protection (seconds between attempts for same order)
LICENSE_EMAIL_RESEND_MIN_SECONDS = 60
LICENSE_EMAIL_RESEND_MAX_ATTEMPTS_PER_HOUR = 10
