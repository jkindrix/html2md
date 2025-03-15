import re


def find_nth_occurrence(text: str, substring: str, n: int) -> int:
    """
    Find the nth occurrence of a substring in a string.

    Args:
        text (str): The input string to search within.
        substring (str): The substring to find.
        n (int): The occurrence index (1-based).

    Returns:
        int: The starting index of the nth occurrence, or -1 if not found.

    Edge Cases:
        - If `text` or `substring` is empty, returns -1.
        - If `n <= 0`, returns -1 (invalid occurrence count).
        - If `substring` is not found at least `n` times, returns -1.
    """
    if not text or not substring or n <= 0:
        return -1  # Invalid input

    matches = [match.start() for match in re.finditer(re.escape(substring), text)]

    return matches[n - 1] if len(matches) >= n else -1
