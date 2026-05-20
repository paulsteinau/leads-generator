from pipeline.extractor.contact import _deobfuscate, _extract_email_from_text, _extract_phone_from_text


def test_deobfuscate_bracket_at():
    assert "@" in _deobfuscate("info [at] firma.de")


def test_deobfuscate_paren_at():
    assert "@" in _deobfuscate("info(at)firma.de")


def test_deobfuscate_bracket_dot():
    assert "." in _deobfuscate("firma[dot]de")


def test_extract_plain_email():
    assert _extract_email_from_text("Kontakt: info@beispiel.de bitte") == "info@beispiel.de"


def test_extract_obfuscated_email():
    r = _extract_email_from_text("info [at] beispiel [dot] de")
    assert r == "info@beispiel.de"


def test_extract_phone_with_area():
    r = _extract_phone_from_text("Tel: 030 12345678")
    assert r is not None and "030" in r


def test_no_email_returns_none():
    assert _extract_email_from_text("Kein Kontakt hier") is None


def test_no_phone_returns_none():
    assert _extract_phone_from_text("Kein Telefon") is None
