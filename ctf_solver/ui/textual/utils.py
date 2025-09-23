import pyperclip


def copy_to_clipboard(text: str) -> bool:
    try:
        pyperclip.copy(text or "")
        return True
    except Exception:
        return False


def truncate_middle(text: str, max_len: int) -> str:
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return text[:max_len]
    half = (max_len - 1) // 2
    return text[:half] + "…" + text[-half:]


