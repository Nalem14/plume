"""How strong a password is, told here (nothing leaves the computer), in five steps like the site's meter.

An estimate, not zxcvbn: the size of the alphabet and the length give the raw entropy, then what attackers
try first takes it down (the most common passwords, keyboard rows, sequences, repeats, a word with digits at
the end, a year, the name of the site or the account). Enough to flag "weak" in the security view.
"""
import math
import re
import unicodedata

COMMON = set("""
123456 123456789 12345678 password 12345 qwerty 1234567 111111 123123 1234567890 000000 abc123 azerty
password1 iloveyou 1q2w3e4r qwerty123 dragon monkey football letmein sunshine princess admin welcome
master login passw0rd starwars superman hello freedom whatever shadow michael trustno1 baseball
soleil bonjour motdepasse doudou loulou chouchou marseille nicolas camille louise jetaime toto
coucou 123soleil azertyuiop qwertz hallo passwort schatz ficken hallo123 orneos orneos123
""".split())
ROWS = ("azertyuiop", "qsdfghjklm", "wxcvbn", "qwertyuiop", "asdfghjkl", "zxcvbnm", "qwertzuiop", "yxcvbnm",
        "1234567890", "abcdefghijklmnopqrstuvwxyz")


def _fold(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _runs(text):
    """Characters that belong to a sequence (abcd, 4321) or a keyboard row (azer, qwerty) of 3 or more."""
    n, low, used, i = len(text), text.lower(), 0, 0
    while i < n - 2:
        longest = 0
        for row in ROWS:
            k = i + 3
            while k <= n and (low[i:k] in row or low[i:k][::-1] in row):
                k += 1
            longest = max(longest, k - 1 - i)
        if longest >= 3:
            used += longest
            i += longest
        else:
            i += 1
    return used


def bits(password, context=()):
    """Estimated entropy in bits."""
    if not password:
        return 0.0
    pool = 0
    if re.search(r"[a-z]", password):
        pool += 26
    if re.search(r"[A-Z]", password):
        pool += 26
    if re.search(r"\d", password):
        pool += 10
    if re.search(r"[^A-Za-z0-9]", password):
        pool += 33
    folded = _fold(password)
    if folded in COMMON or folded.rstrip("0123456789!.") in COMMON:
        return 8.0
    # repeats (aaaa, abab) count once
    effective = len(re.sub(r"(.+?)\1+", r"\1", password))
    effective -= _runs(password) * 0.7
    for word in context:
        word = _fold(word or "")
        if len(word) >= 4 and word in folded:
            effective -= len(word) * 0.8
    if re.fullmatch(r"[A-Za-z]+[0-9]{1,4}[^A-Za-z0-9]?", password):
        effective -= 2                          # a word, then digits: the first thing tried
    if re.search(r"(19|20)\d\d", password):
        effective -= 2
    return max(1.0, effective) * math.log2(max(pool, 2))


def score(password, context=()):
    """0 very weak … 4 very strong."""
    b = bits(password, context)
    return 0 if b < 28 else 1 if b < 45 else 2 if b < 60 else 3 if b < 80 else 4


def weak(password, context=()):
    return bool(password) and score(password, context) <= 1
