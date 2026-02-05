import os
import sys

import pytest


# Ensure repository root is importable so `import src.*` works
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def test_extract_release_date_from_filename_mmddyyyy():
    from src.wasde_parser import extract_release_date

    d = extract_release_date("wasde_01122026.txt", "")
    assert d.year == 2026 and d.month == 1 and d.day == 12


def test_extract_release_date_from_filename_mmddyy():
    from src.wasde_parser import extract_release_date

    d = extract_release_date("wasde011226.txt", "")
    assert d.year == 2026 and d.month == 1 and d.day == 12


def test_extract_release_date_from_monthname_filename():
    from src.wasde_parser import extract_release_date

    d = extract_release_date("wasde_jul_12_2021.txt", "")
    assert d.year == 2021 and d.month == 7 and d.day == 12


def test_extract_release_date_from_header_text():
    from src.wasde_parser import extract_release_date

    content = (
        "World Agricultural Supply and Demand Estimates\n"
        "For release 12:00 P.M. ET January 12, 2026\n"
        "Some other header text\n"
    )
    d = extract_release_date("wasde_latest.txt", content)
    assert d.year == 2026 and d.month == 1 and d.day == 12


def test_extract_release_date_rejects_month_year_only():
    from src.wasde_parser import extract_release_date

    content = "World Agricultural Supply and Demand Estimates\nJanuary 2026\n"
    with pytest.raises(ValueError):
        extract_release_date("wasde0126.txt", content)


def test_extract_release_date_avoids_false_digit_matches():
    from src.wasde_parser import extract_release_date

    # Would match naive (\d{2})(\d{2})(\d{2}) as 20/24/01 without validity checks.
    with pytest.raises(ValueError):
        extract_release_date("wasde_202401.txt", "")


def test_parse_wasde_txt_guards_against_day_one():
    from src.wasde_parser import parse_wasde_txt

    with pytest.raises(ValueError):
        parse_wasde_txt("", "wasde010126.txt")
