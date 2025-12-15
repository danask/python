from py_utils import generate_lotto, generate_password, count_word


def test_lotto():
    nums = generate_lotto(6)
    assert len(nums) == 6
    assert len(set(nums)) == 6
    assert all(1 <= n <= 45 for n in nums)


def test_password():
    assert generate_password("http://www.google.com.test") == "goo62!"


def test_count():
    text = "robot robot robot"
    assert count_word(text, "robot") == 3
