# test_app.py
from app import hash_password

def test_hash_password():
    # 準備（Arrange）
    password_1 = "my_secret_123"
    password_2 = "my_secret_123"
    password_3 = "different_pass"

    # 実行（Act）
    hash_1 = hash_password(password_1)
    hash_2 = hash_password(password_2)
    hash_3 = hash_password(password_3)

    # 検証（Assert）
    # ① 同じパスワードなら、必ず同じハッシュ値になること
    assert hash_1 == hash_2
    # ② 違うパスワードなら、違うハッシュ値になること
    assert hash_1 != hash_3
    # ③ ハッシュ化された文字列が元のパスワードと全く違うこと
    assert hash_1 != password_1