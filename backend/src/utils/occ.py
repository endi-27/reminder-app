from src.core import OptimisticLockConflictException


def check_optimistic_lock(
    actual_version: int,
    expected_version: int,
    entity_title: str = "запису",
) -> None:
    """
    Перевірка відповідності поточної версії сутності переданій клієнтом (OCC).

    Якщо версія в базі відрізняється від надісланої клієнтом, викликає OptimisticLockConflictException
    (який транслюється в HTTP 409 Conflict).
    """
    if actual_version != expected_version:
        raise OptimisticLockConflictException(
            f"Дані {entity_title} було змінено іншим процесом або користувачем. "
            "Будь ласка, оновіть стан перед внесенням змін."
        )


check_version = check_optimistic_lock
