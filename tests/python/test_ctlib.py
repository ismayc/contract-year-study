"""Unit tests for the pure contract-year helpers, on hand-worked fixtures."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from ctlib import norm, parse_awards, raise_breaks, rookie_scale_seasons, season_label  # noqa: E402

ALL = [True] * 30


def test_norm_matches_across_sources():
    assert norm("Dončić, Jr.") == norm("Doncic")
    assert norm("Ömer Aşık") == norm("Omer Asik")
    assert norm("Gary Trent Jr.") == "garytrent"


def test_season_label():
    assert season_label(1998) == "1997-98"
    assert season_label(2000) == "1999-00"


def test_parse_awards():
    f = parse_awards("MVP-1,AS,NBA1")
    assert f == {"all_star": True, "all_nba": True, "mvp": True, "dpoy": False}
    assert parse_awards("MVP-3,AS")["mvp"] is False
    assert parse_awards("") == {"all_star": False, "all_nba": False, "mvp": False, "dpoy": False}


def test_raise_breaks_constant_raises_through_a_trade():
    # Ray Allen 1999-00..2004-05 (one extension, traded mid-2002-03), then a
    # new deal from 2005-06.
    s = [9_000_000, 10_130_000, 11_250_000, 12_375_000, 13_500_000, 14_625_000, 13_223_140, 14_611_570]
    assert raise_breaks(s, ALL) == [None, False, False, False, False, False, True, None]


def test_raise_breaks_confirms_second_season_retroactively():
    # Bam Adebayo 2021-22..2025-26: one five-year extension.
    s = [28_103_550, 30_351_780, 32_600_060, 34_848_340, 37_096_620]
    assert raise_breaks(s, ALL) == [None, False, False, False, False]


def test_raise_breaks_second_season_after_break_is_undetermined():
    # A pair after a break cannot be judged until a third season arrives.
    s = [1_000_000, 1_100_000, 1_200_000, 5_000_000, 5_400_000]
    assert raise_breaks(s, ALL) == [None, False, False, True, None]


def test_raise_breaks_ignores_one_season_blip():
    # Ray Allen 2005-06..2009-10: 2008-09 is $1M off a path 2009-10 rejoins.
    s = [13_223_140, 14_611_570, 16_000_000, 18_388_430, 18_776_860, 10_000_000]
    assert raise_breaks(s, ALL) == [None, False, False, False, False, True]


def test_raise_breaks_flat_contract():
    s = [10_000_000, 10_000_000, 10_000_000]
    assert raise_breaks(s, ALL) == [None, False, False]


def test_raise_breaks_unusable_salary_resets():
    s = [1_000_000, 1_100_000, 300_000, 2_000_000, 2_100_000, 2_200_000]
    u = [True, True, False, True, True, True]
    assert raise_breaks(s, u) == [None, None, None, None, False, False]


def test_raise_breaks_tolerance_is_relative_to_first_salary():
    # 1.5% of 10M = 150k: a 100k wobble continues, a 200k one breaks.
    assert raise_breaks([10_000_000, 11_000_000, 12_100_000], ALL)[2] is False
    assert raise_breaks([10_000_000, 11_000_000, 12_200_000], ALL)[2] is True


@pytest.mark.parametrize("year,rnd,expected", [
    (1994, 1, None), (1995, 1, 3), (1997, 1, 3), (1998, 1, 4), (2017, 1, 4), (2017, 2, None)])
def test_rookie_scale_seasons(year, rnd, expected):
    assert rookie_scale_seasons(year, rnd) == expected
