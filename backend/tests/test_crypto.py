import pytest
from backend.core.crypto import encrypt, decrypt, mask_key


def test_encrypt_decrypt_roundtrip():
    plaintext = "sk-test123456789"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_mask_key():
    assert mask_key("sk-abcdefghijklmnopqrstuvwxyz") == "sk-***wxyz"
    assert mask_key("my-plaintext-key") == "sk-***-key"
    assert mask_key("abc") == "***"
    assert mask_key("abcd") == "***"
