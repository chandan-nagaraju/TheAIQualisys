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

PAYMENT_STATUS_SUBMITTED = "submitted"
PAYMENT_STATUS_APPROVED = "approved"
PAYMENT_STATUS_REJECTED = "rejected"

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
