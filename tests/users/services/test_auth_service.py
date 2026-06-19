from app.users.services.user_auth_service import AuthService


def test_verify_password_accepts_correct_secret():
    password = "Sup3r$ecret!"
    password_hash = AuthService.hash_password(password)

    assert AuthService.verify_password(password, password_hash) is True


def test_verify_password_rejects_wrong_secret():
    password_hash = AuthService.hash_password("correct-horse")

    assert AuthService.verify_password("battery-staple", password_hash) is False


def test_hash_password_uses_unique_salt_for_same_secret():
    password = "repeatable"

    first_hash = AuthService.hash_password(password)
    second_hash = AuthService.hash_password(password)

    assert first_hash != second_hash  # bcrypt should salt differently
    assert AuthService.verify_password(password, first_hash)
    assert AuthService.verify_password(password, second_hash)
