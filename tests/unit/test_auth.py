from mfasha.auth import (LoginThrottle, check_pin, hash_pin, make_token, normalize_phone, read_token,
                         valid_pin)


def test_phone_numbers_are_normalised_to_one_form():
    for raw in ("0788123456", "0788 123 456", "+250 788 123 456", "250788123456", "0788-123-456"):
        assert normalize_phone(raw) == "0788123456"
    assert normalize_phone("abc") is None and normalize_phone("123") is None


def test_pin_must_be_four_to_six_digits():
    assert valid_pin("1234") and valid_pin("123456")
    assert not valid_pin("123") and not valid_pin("1234567") and not valid_pin("12a4") and not valid_pin("")


def test_pin_is_hashed_and_checked():
    salt, digest = hash_pin("4821")
    assert "4821" not in digest and len(digest) == 64
    assert check_pin("4821", salt, digest) and not check_pin("4822", salt, digest)
    assert hash_pin("4821")[0] != salt             # a new random salt every time


def test_token_round_trip_expiry_and_tampering():
    token = make_token("secret", "0788123456", "Jeanne")
    assert read_token("secret", token) == {"phone": "0788123456", "name": "Jeanne"}
    assert read_token("other-secret", token) is None
    assert read_token("secret", make_token("secret", "0788123456", "Jeanne", hours=-1)) is None
    body, sig = token.split(".")
    assert read_token("secret", body + "x." + sig) is None
    assert read_token("secret", "garbage") is None


def test_throttle_locks_after_repeated_failures_and_resets():
    t = LoginThrottle(max_failures=3, lock_seconds=60)
    for _ in range(2):
        t.record_failure("0788123456")
    assert t.seconds_locked("0788123456") == 0
    t.record_failure("0788123456")
    assert t.seconds_locked("0788123456") > 0
    assert t.seconds_locked("0799999999") == 0      # another phone is unaffected
    t.reset("0788123456")
    assert t.seconds_locked("0788123456") == 0