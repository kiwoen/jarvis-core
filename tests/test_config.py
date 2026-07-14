"""Tests for SurvivalConfig: roundtrip, from_config factory, file I/O."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.court.config import SurvivalConfig
from jarvis.court.evolution import (
    CrossoverMode,
    EliteTurnoverMode,
    EvolutionRateMode,
    SurvivalMechanism,
    WindowMode,
)


# ── Defaults ─────────────────────────────────────────────────────────

def test_default_config_sane() -> None:
    c = SurvivalConfig()
    assert c.elitism_count == 2
    assert c.crossover_rate == 0.6
    assert c.crossover_mode == "sbx"
    assert c.turnover_mode == "adaptive"
    assert c.rate_mode == "adaptive"
    assert c.enable_sliding_merit is True
    assert c.enable_auto_breeding is True


# ── enum property helpers ────────────────────────────────────────────

def test_crossover_mode_enum() -> None:
    assert SurvivalConfig(crossover_mode="sbx").crossover_mode_enum == CrossoverMode.SBX
    assert SurvivalConfig(crossover_mode="uniform").crossover_mode_enum == CrossoverMode.UNIFORM


def test_turnover_mode_enum() -> None:
    assert SurvivalConfig(turnover_mode="adaptive").turnover_mode_enum == EliteTurnoverMode.ADAPTIVE


def test_rate_mode_enum() -> None:
    assert SurvivalConfig(rate_mode="adaptive").rate_mode_enum == EvolutionRateMode.ADAPTIVE
    assert SurvivalConfig(rate_mode="fixed").rate_mode_enum == EvolutionRateMode.FIXED


def test_sliding_window_mode_enum() -> None:
    assert SurvivalConfig(sliding_window_mode="hard_cutoff").sliding_window_mode_enum == WindowMode.HARD_CUTOFF


# ── from_dict / to_dict roundtrip ────────────────────────────────────

def test_to_dict_roundtrip() -> None:
    c = SurvivalConfig(
        elitism_count=3,
        crossover_rate=0.8,
        sbx_eta=20.0,
        genome_path="/tmp/genomes.json",
        enable_auto_breeding=False,
    )
    d = c.to_dict()
    c2 = SurvivalConfig.from_dict(d)
    assert c2.elitism_count == 3
    assert c2.crossover_rate == 0.8
    assert c2.sbx_eta == 20.0
    assert c2.genome_path == "/tmp/genomes.json"
    assert c2.enable_auto_breeding is False


def test_from_dict_ignores_unknown_keys() -> None:
    c = SurvivalConfig.from_dict({"elitism_count": 5, "unknown_field": 999})
    assert c.elitism_count == 5
    # should not raise


def test_from_dict_partial_uses_defaults() -> None:
    c = SurvivalConfig.from_dict({"elitism_count": 7})
    assert c.elitism_count == 7
    assert c.crossover_rate == 0.6  # default


# ── JSON I/O ─────────────────────────────────────────────────────────

def test_json_roundtrip(tmp_path: Path) -> None:
    c = SurvivalConfig(elitism_count=4, min_elites=2, max_elites=6)
    path = tmp_path / "config.json"
    c.to_json(path)

    c2 = SurvivalConfig.from_json(path)
    assert c2.elitism_count == 4
    assert c2.min_elites == 2
    assert c2.max_elites == 6


# ── from_config factory ──────────────────────────────────────────────

def test_from_config_creates_valid_survival_mechanism() -> None:
    c = SurvivalConfig(
        elitism_count=3,
        crossover_rate=0.5,
        sbx_eta=10.0,
        enable_sliding_merit=False,
        enable_auto_breeding=False,
    )
    sm = SurvivalMechanism.from_config(c)
    assert sm._elitism_count == 3
    assert sm._crossover_rate == 0.5
    assert sm._sbx_eta == 10.0


def test_from_config_respects_genome_path() -> None:
    c = SurvivalConfig(genome_path="/tmp/test_genomes.json")
    sm = SurvivalMechanism.from_config(c)
    assert sm._genome_path == "/tmp/test_genomes.json"


def test_from_config_empty_genome_path_is_none() -> None:
    c = SurvivalConfig(genome_path="")
    sm = SurvivalMechanism.from_config(c)
    assert sm._genome_path is None


def test_from_config_with_merit_board() -> None:
    from jarvis.court.merit_board import MeritBoard

    board = MeritBoard()
    sm = SurvivalMechanism.from_config(
        SurvivalConfig(enable_sliding_merit=False), merit_board=board,
    )
    assert sm._merit_board is board


def test_from_config_default_config_works() -> None:
    """Default config should produce a working SurvivalMechanism."""
    sm = SurvivalMechanism.from_config(SurvivalConfig())
    assert sm._cycle_count == 0
    assert sm._enable_auto_breeding is True
    assert sm._genome_path is None
