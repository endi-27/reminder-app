from collections.abc import Sequence


def normalize_spaces(v: str) -> str:
    """Очищення від зайвих та множинних пробілів всередині рядка."""
    return " ".join(v.split())


def normalize_human_name(v: str) -> str:
    """
    Очищення від множинних пробілів та капіталізація слів ПІБ.
    Коректно обробляє апострофи (Ім'я, В'ячеслав, О'Коннор) та дефіси (Жан-Поль).
    """
    parts = v.split()
    normalized_words = []
    for part in parts:
        subparts = []
        for sub in part.split("-"):
            if not sub:
                subparts.append("")
                continue
            for apostrophe in ("'", "’", "`"):
                if apostrophe in sub:
                    prefix, rest = sub.split(apostrophe, 1)
                    if prefix.lower() in ("о", "д", "o", "d"):
                        sub = f"{prefix.capitalize()}{apostrophe}{rest.capitalize()}"
                    else:
                        sub = f"{prefix.capitalize()}{apostrophe}{rest.lower()}"
                    break
            else:
                sub = sub[0].upper() + sub[1:].lower() if len(sub) > 1 else sub.upper()
            subparts.append(sub)
        normalized_words.append("-".join(subparts))
    return " ".join(normalized_words)


def deduplicate_preserve_order[T](items: Sequence[T] | None) -> list[T] | None:
    """Усунення дублікатів зі збереженням вихідного порядку елементів."""
    if items is None:
        return None
    return list(dict.fromkeys(items))
