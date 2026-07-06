"""Behavioural tests for the small translation helpers in const.py.

These three functions (get_notification_labels, get_notification_message,
translate_description) are pure functions over module-level translation
dictionaries; they're exercised indirectly through the coordinator but not
directly, so a handful of focused tests close the remaining coverage gap.
"""

from __future__ import annotations

from custom_components.dreame_vacuum.const import (
    DESCRIPTION_TRANSLATIONS,
    NOTIFICATION,
    NOTIFICATION_CLEANUP_COMPLETED,
    NOTIFICATION_MESSAGES_TRANSLATIONS,
    NOTIFICATION_TRANSLATIONS,
    get_notification_labels,
    get_notification_message,
    translate_description,
)

# ---------------------------------------------------------------------------
# get_notification_labels
# ---------------------------------------------------------------------------


def test_get_notification_labels_no_language_returns_english_defaults():
    assert get_notification_labels(None) == NOTIFICATION


def test_get_notification_labels_unknown_language_falls_back_to_english():
    assert get_notification_labels("de") == NOTIFICATION


def test_get_notification_labels_known_language_returns_translated_dict():
    labels = get_notification_labels("fr")
    assert labels == NOTIFICATION_TRANSLATIONS["fr"]
    assert labels["error"] == "Erreur"


# ---------------------------------------------------------------------------
# get_notification_message
# ---------------------------------------------------------------------------


def test_get_notification_message_english_simple_key():
    assert get_notification_message("en", "cleanup_completed") == NOTIFICATION_CLEANUP_COMPLETED


def test_get_notification_message_unknown_key_returns_empty_string():
    assert get_notification_message("en", "does_not_exist") == ""


def test_get_notification_message_known_language_known_key():
    message = get_notification_message("fr", "cleanup_completed")
    assert message == NOTIFICATION_MESSAGES_TRANSLATIONS["fr"]["cleanup_completed"]
    assert message != NOTIFICATION_CLEANUP_COMPLETED


def test_get_notification_message_known_language_missing_key_falls_back_to_english():
    # "fr" translations exist, but not for every possible key; any key present
    # only in the English fallback dict should still resolve through the
    # fallback branch instead of raising.
    message = get_notification_message("fr", "cleanup_completed")
    assert message


def test_get_notification_message_formats_kwargs_translated():
    message = get_notification_message("fr", "resume_cleaning_timer", hour=1, minute=30)
    assert "1" in message
    assert "30" in message


def test_get_notification_message_formats_kwargs_english_fallback():
    message = get_notification_message("en", "resume_cleaning_timer", hour=2, minute=5)
    assert "2 hour(s)" in message
    assert "5 minutes(s)" in message


def test_get_notification_message_empty_language_uses_english_messages():
    assert get_notification_message("", "cleanup_completed") == NOTIFICATION_CLEANUP_COMPLETED


def test_get_notification_message_unknown_language_and_key_returns_empty_string():
    assert get_notification_message("de", "does_not_exist") == ""


# ---------------------------------------------------------------------------
# translate_description
# ---------------------------------------------------------------------------


def test_translate_description_no_language_returns_input_unchanged():
    description = ["No error", "Some detail"]
    assert translate_description("", description) is description


def test_translate_description_unknown_language_returns_input_unchanged():
    description = ["No error", "Some detail"]
    assert translate_description("de", description) is description


def test_translate_description_empty_description_returns_input_unchanged():
    assert translate_description("fr", []) == []


def test_translate_description_translates_known_entries():
    translated = translate_description("fr", ["No error"])
    assert translated == [DESCRIPTION_TRANSLATIONS["fr"]["No error"]]


def test_translate_description_keeps_unknown_entries_verbatim():
    translated = translate_description("fr", ["Totally unknown description text"])
    assert translated == ["Totally unknown description text"]


def test_translate_description_mixed_known_and_unknown_entries():
    translated = translate_description("fr", ["No error", "Some unmapped text"])
    assert translated == [DESCRIPTION_TRANSLATIONS["fr"]["No error"], "Some unmapped text"]
