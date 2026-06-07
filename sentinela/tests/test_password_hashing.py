from src.app.auth import hash_password, verify_password


def test_password_hash_uses_bcrypt():
    hashed = hash_password("senha-forte")
    assert hashed.startswith("$2")
    assert verify_password("senha-forte", hashed)
    assert not verify_password("errada", hashed)
