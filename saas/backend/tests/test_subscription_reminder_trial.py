from datetime import date
from types import SimpleNamespace

from app.subscription_reminder_runner import _build_reminder_slots, company_due_for_trial_reminder


def test_trial_reminder_window() -> None:
    today = date(2026, 9, 10)
    trial = SimpleNamespace(
        subscription_status="trial",
        subscription_start=None,
        subscription_end=None,
        trial_end_date=date(2026, 9, 12),
    )
    assert company_due_for_trial_reminder(trial, today) is True
    trial.trial_end_date = date(2026, 9, 10)
    assert company_due_for_trial_reminder(trial, today) is True
    trial.trial_end_date = date(2026, 9, 9)
    assert company_due_for_trial_reminder(trial, today) is True
    trial.trial_end_date = date(2026, 9, 1)
    assert company_due_for_trial_reminder(trial, today) is False


def test_paid_active_skips_trial_reminder() -> None:
    today = date(2026, 9, 10)
    paid = SimpleNamespace(
        subscription_status="active",
        subscription_start=date(2026, 1, 1),
        subscription_end=date(2026, 12, 31),
        trial_end_date=date(2026, 9, 10),
    )
    assert company_due_for_trial_reminder(paid, today) is False


def test_ending_soon_gets_morning_slot() -> None:
    slots = _build_reminder_slots(
        force=True,
        in_morning_slot=False,
        in_evening_slot=False,
        mask=0,
        expires_today=False,
        expired=False,
        ending_soon=True,
        morning_hour=9,
        evening_hour=18,
    )
    assert slots == [("morning", 1)]
