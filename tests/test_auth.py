from app.auth import generate_key, hash_key


def test_generate_key_has_prefix():
    assert generate_key().startswith("gw_")

def test_generate_key_is_unique():
    assert generate_key() != generate_key()

def test_hash_key_is_deterministic():
    assert hash_key("gw_abc")  == hash_key("gw_abc")

def test_hash_key_hides_the_key():
    key = generate_key()
    hashed = hash_key(key)

    assert key not in hashed
    assert len(hashed) == 64 #sha256 hex digest
    
