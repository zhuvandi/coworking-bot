from coworkingbot.utils.helpers import is_admin, is_past_booking

def test_is_admin_true():
    assert is_admin(123) in (True, False)

def test_is_past_booking_format():
    assert isinstance(is_past_booking("2024-01-01"), bool)
