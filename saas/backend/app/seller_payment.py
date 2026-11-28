"""TheAIQualisys seller GSTIN and settlement account details for customer emails."""

SELLER_GSTIN = "29CCTPC6405L1Z4"
SELLER_BANK_NAME = "Axis Bank"
SELLER_ACCOUNT_HOLDER = "Chandan N"
SELLER_ACCOUNT_NUMBER = "919010044064495"
SELLER_IFSC = "UTIB0001204"
SELLER_ACCOUNT_TYPE = "Savings A/c"
SELLER_UPI_ID = "7892007580@axisbank"


def seller_account_details_lines(*, gstin: str | None = None) -> list[str]:
    number = (gstin or "").strip().upper() or SELLER_GSTIN
    return [
        f"Bank Name: {SELLER_BANK_NAME}",
        f"Primary Account Holder: {SELLER_ACCOUNT_HOLDER}",
        f"Account Number: {SELLER_ACCOUNT_NUMBER}",
        f"IFSC Code: {SELLER_IFSC}",
        f"Account Type: {SELLER_ACCOUNT_TYPE}",
        f"UPI ID: {SELLER_UPI_ID}",
        f"GSTIN: {number}",
    ]


def seller_account_details_text(*, gstin: str | None = None) -> str:
    return "\n".join(seller_account_details_lines(gstin=gstin))
