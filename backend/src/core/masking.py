from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "private_key",
    "passphrase",
    "tax_number",
    "inn",
    "edrpou",
    "iban",
    "card_number",
    "cvv",
    "pin",
    "ssn",
    "signature",
    "session_token_hash",
)
MASKED_VALUE = "***MASKED***"


def is_sensitive_key(key: str) -> bool:
    """Перевіряє, чи містить назва ключа конфіденційні підрядки (регістронезалежно)."""
    lowered = key.lower()
    return any(sub in lowered for sub in SENSITIVE_SUBSTRINGS)


def mask_sensitive_data(data: Any, _visited: set[int] | None = None) -> Any:
    """
    Рекурсивно маскує конфіденційні поля (паролі, токени, хеші, секрети) у словниках, списках та множинах.
    Безпечно обробляє циклічні посилання та довільні вкладені структури даних.
    """
    if data is None or isinstance(data, (int, float, bool)):
        return data

    if isinstance(data, (str, bytes, bytearray)):
        return data

    if _visited is None:
        _visited = set()

    obj_id = id(data)
    if obj_id in _visited:
        return "<circular reference>"

    if isinstance(data, Mapping):
        _visited.add(obj_id)
        result: dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            if is_sensitive_key(key_str):
                result[key_str] = MASKED_VALUE
            else:
                result[key_str] = mask_sensitive_data(v, _visited)
        _visited.remove(obj_id)
        return result

    if isinstance(data, (set, frozenset)):
        _visited.add(obj_id)
        res_set = {mask_sensitive_data(item, _visited) for item in data}
        _visited.remove(obj_id)
        return frozenset(res_set) if isinstance(data, frozenset) else res_set

    if isinstance(data, Sequence):
        _visited.add(obj_id)
        res_list = [mask_sensitive_data(item, _visited) for item in data]
        _visited.remove(obj_id)
        return res_list

    return data
