"""Declarations of some package utilities"""

from . import const


def check_cups_integrity(cups: str):
    """Returns false if cups is not valid, true otherwise"""

    _cups = cups.upper()

    if len(_cups) not in [20, 22]:
        return False

    if not all("0" <= x <= "9" for x in _cups[2:18]):
        return False

    cups_16_digits = int(_cups[2:18])
    base = cups_16_digits % 529
    cups_c = int(base / 23)
    cups_r = base % 23

    if (
        const.CUPS_CONTROL_DIGITS[cups_c] + const.CUPS_CONTROL_DIGITS[cups_r]
        != _cups[18:20]
    ):
        print(const.CUPS_CONTROL_DIGITS[cups_c] + const.CUPS_CONTROL_DIGITS[cups_r])
        return False

    return True
