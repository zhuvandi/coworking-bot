from coworkingbot.routers.booking import format_phone, validate_phone


def test_validate_phone_accepts_variants():
    assert validate_phone("89991234567")
    assert validate_phone("+79991234567")
    assert validate_phone("9991234567")


def test_format_phone_normalizes():
    assert format_phone("89991234567") == "79991234567"
    assert format_phone("+79991234567") == "79991234567"
    assert format_phone("9991234567") == "79991234567"
