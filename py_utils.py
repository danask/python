import random
from typing import List


def generate_lotto(count: int = 6, min_value: int = 1, max_value: int = 45) -> List[int]:
    """Return a list of unique lotto numbers."""
    if count < 1:
        raise ValueError("count must be >= 1")
    if count > (max_value - min_value + 1):
        raise ValueError("count is too large for range")
    return random.sample(range(min_value, max_value + 1), count)


def generate_password(website: str) -> str:
    """Generate a simple password from a website string.

    Logic: remove http(s)://, split on dots, prefer domain part (skip 'www'), then
    return first 3 chars + length + count('o') + '!'
    """
    if not website:
        raise ValueError("website required")
    temp = website.replace("http://", "").replace("https://", "")
    parts = [p for p in temp.split('.') if p]
    if not parts:
        raise ValueError("invalid website")
    # choose domain-like part (skip 'www' when present)
    if parts[0].lower() == 'www' and len(parts) > 1:
        domain = parts[1]
    else:
        domain = parts[0]
    password = domain[:3] + str(len(domain)) + str(domain.count('o')) + "!"
    return password


def count_word(text: str, word: str) -> int:
    return text.count(word)
