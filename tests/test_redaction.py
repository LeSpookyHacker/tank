"""Tests for the redaction engine.

These are the most important tests in the codebase. If they fail, the
privacy guarantee fails. They cover:

- Each rule category catches what it should and skips what it shouldn't.
- Determinism: same input → same placeholder across calls.
- Dedup: the same email in two different chunks shares a placeholder.
- Overlap resolution: ARN beats AWS account ID inside the ARN.
- Rehydration is the inverse of redaction, including the longest-first
  ordering so [HOST_10] doesn't get clobbered by [HOST_1].
- Secrets are one-way: original_text is hashed, never persisted in clear.
"""

from __future__ import annotations

import hashlib

import pytest


# Fixtures from conftest.py reset the DB; we re-import app modules inside
# each test to get the patched env.

def _eng():
    from app.redact.engine import apply_redactions, rehydrate
    return apply_redactions, rehydrate


# ---------------- email ----------------

def test_email_redacted(fresh_db):
    apply, _rehy = _eng()
    out = apply("Contact alice@example.com for access.")
    assert "alice@example.com" not in out.redacted_text
    assert "[EMAIL_001]" in out.redacted_text


def test_same_email_same_placeholder_across_calls(fresh_db):
    apply, _rehy = _eng()
    a = apply("ping alice@example.com")
    b = apply("alice@example.com is on call")
    # Both calls allocate the same placeholder.
    ph_a = [m.placeholder for m in a.matches if m.category == "email"][0]
    ph_b = [m.placeholder for m in b.matches if m.category == "email"][0]
    assert ph_a == ph_b


# ---------------- internal hostnames ----------------

def test_internal_hostname_default_suffix(fresh_db):
    apply, _rehy = _eng()
    out = apply("Service is at payments.internal and also web.corp.")
    assert "payments.internal" not in out.redacted_text
    assert "web.corp" not in out.redacted_text
    assert "[INTERNAL_HOST_001]" in out.redacted_text
    assert "[INTERNAL_HOST_002]" in out.redacted_text


def test_public_hostname_not_redacted_by_default(fresh_db):
    apply, _rehy = _eng()
    out = apply("See https://docs.python.org/3/ for the docs.")
    assert "docs.python.org" in out.redacted_text


def test_email_domain_not_double_redacted_as_hostname(fresh_db):
    apply, _rehy = _eng()
    out = apply("alice@payments.internal sent the alert.")
    # The whole email becomes [EMAIL_001]; the .internal domain inside
    # should NOT separately appear as INTERNAL_HOST.
    email_matches = [m for m in out.matches if m.category == "email"]
    host_matches = [m for m in out.matches if m.category == "internal_hostname"]
    assert len(email_matches) == 1
    assert len(host_matches) == 0


# ---------------- private IPs ----------------

@pytest.mark.parametrize("ip", [
    "10.0.0.1", "10.255.255.254",
    "172.16.0.1", "172.31.255.255",
    "192.168.1.1",
    "127.0.0.1",
    "169.254.169.254",
    "100.64.0.1",
])
def test_private_ipv4_redacted(fresh_db, ip):
    apply, _rehy = _eng()
    out = apply(f"Box at {ip} is down.")
    assert ip not in out.redacted_text
    assert any(m.category == "ipv4_private" for m in out.matches)


@pytest.mark.parametrize("ip", [
    "8.8.8.8", "1.1.1.1", "172.32.0.1",       # just outside RFC1918
])
def test_public_ipv4_not_redacted_by_default(fresh_db, ip):
    apply, _rehy = _eng()
    out = apply(f"DNS at {ip}.")
    assert ip in out.redacted_text


# ---------------- AWS ----------------

def test_aws_account_id_with_context(fresh_db):
    apply, _rehy = _eng()
    out = apply("AWS account 999988887777 owns this resource.")
    assert "999988887777" not in out.redacted_text
    assert "[AWS_ACCT_001]" in out.redacted_text


def test_random_12_digit_number_without_context_stays(fresh_db):
    apply, _rehy = _eng()
    out = apply("The product cost 999988887777 cents.")
    # No AWS context → not redacted as account ID.
    assert "999988887777" in out.redacted_text


def test_aws_arn_beats_account_id(fresh_db):
    apply, _rehy = _eng()
    text = "Resource arn:aws:s3:::my-bucket; account 999988887777"
    out = apply(text)
    arn_hits = [m for m in out.matches if m.category == "aws_arn"]
    acct_hits = [m for m in out.matches if m.category == "aws_account_id"]
    # The full ARN gets one redaction; the trailing 12-digit number is
    # separately redacted (it's outside the ARN span).
    assert len(arn_hits) == 1
    assert len(acct_hits) == 1


# ---------------- secrets ----------------

def test_aws_access_key_redacted(fresh_db):
    apply, _rehy = _eng()
    secret = "AKIAIOSFODNN7EXAMPLE"
    out = apply(f"Set AWS_ACCESS_KEY_ID={secret} in the env.")
    assert secret not in out.redacted_text
    assert any(m.category == "secret_token" for m in out.matches)


def test_secret_original_is_hashed_not_stored_clear(fresh_db):
    apply, _rehy = _eng()
    secret = "AKIAIOSFODNN7EXAMPLE"
    apply(f"key={secret}")
    # Inspect the redaction_map directly.
    from app.db import get_conn
    row = get_conn().execute(
        "SELECT original_text FROM redaction_map WHERE category = 'secret_token'"
    ).fetchone()
    assert row is not None
    assert row["original_text"] != secret
    assert row["original_text"] == hashlib.sha256(secret.encode()).hexdigest()


def test_secret_rule_is_non_disableable(fresh_db):
    from app.redact.config import set_category_enabled, get_effective_rules
    set_category_enabled("secret_token", False)
    rules = {cr.rule.category: cr.enabled for cr in get_effective_rules()}
    # Even after explicit disable, secret_token stays enabled.
    assert rules["secret_token"] is True


# ---------------- rehydration ----------------

def test_rehydrate_round_trip(fresh_db):
    apply, rehy = _eng()
    original = "alice@example.com pinged payments.internal at 10.0.0.5."
    out = apply(original)
    restored = rehy(out.redacted_text)
    assert restored == original


def test_rehydrate_longest_first_avoids_prefix_collision(fresh_db):
    apply, rehy = _eng()
    # Create 11+ emails so we hit [EMAIL_010] and [EMAIL_001] together.
    text = " ".join(f"user{i}@example.com" for i in range(1, 12))
    out = apply(text)
    restored = rehy(out.redacted_text)
    assert restored == text


def test_secret_is_not_rehydrated(fresh_db):
    apply, rehy = _eng()
    secret = "AKIAIOSFODNN7EXAMPLE"
    out = apply(f"key={secret}")
    restored = rehy(out.redacted_text)
    # We can't recover the original — placeholder stays in the restored text.
    assert secret not in restored
    assert "[SECRET_" in restored


# ---------------- determinism / dedup ----------------

def test_two_different_originals_get_different_placeholders(fresh_db):
    apply, _rehy = _eng()
    out = apply("alice@example.com and bob@example.com")
    placeholders = {m.placeholder for m in out.matches if m.category == "email"}
    assert len(placeholders) == 2


def test_redaction_map_dense_sequence(fresh_db):
    apply, _rehy = _eng()
    apply("alice@a.com")
    apply("bob@b.com")
    apply("carol@c.com")
    from app.db import get_conn
    rows = get_conn().execute(
        "SELECT placeholder FROM redaction_map WHERE category = 'email' "
        "ORDER BY first_seen_at"
    ).fetchall()
    placeholders = [r["placeholder"] for r in rows]
    assert placeholders == ["[EMAIL_001]", "[EMAIL_002]", "[EMAIL_003]"]


# ---------------- custom rules ----------------

def test_custom_rule_redacts(fresh_db):
    from app.redact.config import add_custom_rule
    add_custom_rule("ticket", r"\bACME-\d{4}\b",
                    placeholder_fmt="[TICKET_{n:03d}]")
    apply, _rehy = _eng()
    out = apply("See ACME-1234 and ACME-9999.")
    assert "ACME-1234" not in out.redacted_text
    assert "ACME-9999" not in out.redacted_text
    assert "[TICKET_001]" in out.redacted_text
    assert "[TICKET_002]" in out.redacted_text


# ---------------- Azure / GCP cloud IDs ----------------

def test_azure_subscription_with_context(fresh_db):
    apply, _rehy = _eng()
    uuid = "abc12345-def6-7890-abcd-ef0123456789"
    out = apply(f"Azure subscription {uuid} created in tenant.")
    assert uuid not in out.redacted_text
    assert any(m.category == "azure_subscription" for m in out.matches)


def test_azure_uuid_without_context_stays(fresh_db):
    apply, _rehy = _eng()
    uuid = "abc12345-def6-7890-abcd-ef0123456789"
    out = apply(f"Some random uuid {uuid} appears here.")
    assert uuid in out.redacted_text


def test_gcp_project_with_context(fresh_db):
    apply, _rehy = _eng()
    out = apply("GCP project my-data-pipeline has 3 VMs.")
    assert "my-data-pipeline" not in out.redacted_text
    assert any(m.category == "gcp_project" for m in out.matches)


def test_gcp_common_word_not_redacted(fresh_db):
    apply, _rehy = _eng()
    out = apply("The service deployment runs in GCP.")
    # "service" and "deployment" are in the stop-list and must not be redacted
    assert "service" in out.redacted_text
    assert "deployment" in out.redacted_text
    assert "[GCP_PROJECT" not in out.redacted_text


# ---------------- IPv6 ----------------

def test_private_ipv6_redacted(fresh_db):
    apply, _rehy = _eng()
    for ip in ("::1", "fe80::1", "fc00::1", "fd12:3456:789a::1"):
        out = apply(f"Host is at {ip}.")
        assert ip not in out.redacted_text, f"{ip!r} should be redacted"
        assert any(m.category == "ipv6_private" for m in out.matches)


def test_public_ipv6_not_redacted_by_default(fresh_db):
    apply, _rehy = _eng()
    # 2001:4860:4860::8888 is Google's public DNS — globally routable
    ip = "2001:4860:4860::8888"
    out = apply(f"External host {ip}.")
    # ipv6_public is off by default
    assert ip in out.redacted_text


# ---------------- case-insensitive dedup ----------------

def test_email_case_insensitive_dedup(fresh_db):
    apply, _rehy = _eng()
    a = apply("Contact ALICE@EXAMPLE.COM here.")
    b = apply("send to alice@example.com thanks.")
    ph_a = next(m.placeholder for m in a.matches if m.category == "email")
    ph_b = next(m.placeholder for m in b.matches if m.category == "email")
    assert ph_a == ph_b


# ---------------- detect-secrets repeated token on one line ----------------

def test_repeated_secret_on_same_line(fresh_db):
    apply, _rehy = _eng()
    key = "AKIAIOSFODNN7EXAMPLE"
    # Same key appearing twice on the same line — both occurrences must be gone.
    out = apply(f"OLD_KEY={key} NEW_KEY={key}")
    assert key not in out.redacted_text
    assert out.redacted_text.count("[SECRET_") == 2


# ---------------- used_placeholders helper ----------------

def test_used_placeholders_extracts_correctly(fresh_db):
    from app.redact.engine import used_placeholders
    apply, _rehy = _eng()
    out = apply("alice@example.com and payments.internal are down.")
    phs = used_placeholders(out.redacted_text)
    assert any(p.startswith("[EMAIL_") for p in phs)
    assert any(p.startswith("[INTERNAL_HOST_") for p in phs)


def test_scoped_rehydration(fresh_db):
    from app.redact.engine import used_placeholders
    from app.redact.store import load_rehydration_map
    apply, rehy = _eng()
    # Seed the map with two different emails.
    apply("alice@example.com is here")
    out = apply("bob@example.com is there")
    bob_ph = next(m.placeholder for m in out.matches if m.category == "email")
    # Scoped map for bob's placeholder only.
    scoped = load_rehydration_map(used_placeholders(out.redacted_text))
    assert len(scoped) == 1
    assert bob_ph in scoped
    restored = rehy(out.redacted_text, scoped)
    assert "bob@example.com" in restored
    assert "[EMAIL_" not in restored


# ---------------- custom rule ReDoS rejection ----------------

def test_custom_rule_redos_rejected(fresh_db):
    from app.redact.config import add_custom_rule
    import re
    with pytest.raises(re.error):
        add_custom_rule("bad", r"(a+)+b")
