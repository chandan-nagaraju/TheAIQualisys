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
PHASE_DOWNLOADS = "6-protected-downloads"
PHASE_MACHINE = "7-machine-license"

# Signed entitlement (Phase 7)
LICENSE_ENTITLEMENT_ISSUER = "aiqualisys-license"
LICENSE_ENTITLEMENT_SCHEMA_VERSION = 1
LICENSE_MAX_OFFLINE_DAYS_DEFAULT = 14
LICENSE_CLOCK_SKEW_SECONDS = 300

# Machine API stable error codes
MACHINE_ERR_NOT_AUTHENTICATED = "not_authenticated"
MACHINE_ERR_LICENSING_DISABLED = "licensing_disabled"
MACHINE_ERR_INVALID_LICENSE = "invalid_license"
MACHINE_ERR_WRONG_USER = "wrong_user"
MACHINE_ERR_WRONG_PRODUCT = "wrong_product"
MACHINE_ERR_EXPIRED = "expired"
MACHINE_ERR_REVOKED = "revoked"
MACHINE_ERR_SUSPENDED = "suspended"
MACHINE_ERR_DEVICE_BOUND = "device_bound"
MACHINE_ERR_INVALID_DEVICE = "invalid_device"
MACHINE_ERR_SIGNING_UNAVAILABLE = "signing_unavailable"
MACHINE_ERR_RATE_LIMITED = "rate_limited"
MACHINE_ERR_INVALID_REQUEST = "invalid_request"
MACHINE_ERR_INVALID_STATUS = "invalid_status"
MACHINE_ERR_TRIAL_NOT_SUPPORTED = "trial_not_supported"

ADMIN_RESET_REASON_MIN_LEN = 8

# License email delivery statuses (per order; never remints on retry)
LICENSE_EMAIL_PENDING = "pending"
LICENSE_EMAIL_SENT = "sent"
LICENSE_EMAIL_FAILED = "failed"

# Resend rate protection (seconds between attempts for same order)
LICENSE_EMAIL_RESEND_MIN_SECONDS = 60
LICENSE_EMAIL_RESEND_MAX_ATTEMPTS_PER_HOUR = 10

# Installer upload security (Phase 6)
INSTALLER_ALLOWED_EXTENSIONS = frozenset({".exe", ".msi", ".zip", ".msix"})
INSTALLER_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/octet-stream",
        "application/x-msdownload",
        "application/vnd.microsoft.portable-executable",
        "application/x-msi",
        "application/zip",
        "application/x-zip-compressed",
        "application/msix",
        "application/msixbundle",
    }
)
DOWNLOAD_TOKEN_BYTES = 32
