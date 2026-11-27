"""
sec_ua.py: идентификацията пред SEC (ПРОЛЕТР9, Фаза 1).
=========================================================
SEC иска в заглавката User-Agent име и адрес за контакт. В кода няма записан
адрес: низът идва само от променливата на средата SEC_USER_AGENT
(в GitHub Actions: тайната SEC_USER_AGENT; локално: променлива на средата
за потребителя). Без нея скриптът спира с ясна грешка, без подразбираща се стойност.

Стойността се чете при заявката, не при импорта: тестовете и сухите ходове
внасят модулите без настройката.
"""

import os

ENV = "SEC_USER_AGENT"


def sec_user_agent() -> str:
    ua = (os.environ.get(ENV) or "").strip()
    if not ua:
        # ASCII: конзолата на Windows (cp1252) не печата кирилица в грешка.
        raise SystemExit(
            f"{ENV} is not set. SEC requires a contact name and address in the "
            f"User-Agent header. Set the environment variable {ENV} locally, "
            f"or the repository secret {ENV} for GitHub Actions."
        )
    # HTTP заглавките са latin-1: кирилица или неподменен образец гърмят при всяка заявка
    # и събирачът минава на следващото име (27.11.2026). Спираме веднага.
    if not ua.isascii() or "<" in ua or ">" in ua:
        raise SystemExit(
            f"{ENV} must be plain Latin text with a real name and contact address "
            f"(no Cyrillic, no <...> placeholder left in it)."
        )
    return ua


def sec_headers(extra=None) -> dict:
    """Заглавките за заявка към SEC: User-Agent от настройката плюс допълнителните."""
    h = {"User-Agent": sec_user_agent()}
    if extra:
        h.update(extra)
    return h
