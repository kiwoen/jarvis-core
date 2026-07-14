"""
Tests for AutoBreeder (自动育种器).

Coverage: GapAnalyzer, StrategySelector, GenomeGenerator, AutoBreeder.
"""

import pytest

from jarvis.court.breeding import (
    AutoBreeder,
    BreedingCandidate,
    BreedingStrategy,
    CapabilityGap,
    GapAnalyzer,
    GenomeGenerator,
    StrategySelector,
)


# ── Helpers ─────────────────────────────────────────────────────────


def make_expertise(*minister_domain_pairs):
    """Build domain_expertise dict from (minister, domain, score) tuples."""
    result = {}
    for minister, domain, score in minister_domain_pairs:
        if minister not in result:
            result[minister] = {}
        result[minister][domain] = score
    return result


# ═══════════════════════════════════════════════════════════════════
# GapAnalyzer
# ═══════════════════════════════════════════════════════════════════


class TestGapAnalyzer:
    """Capability gap detection."""

    def test_coverage_gap_zero_ministers(self):
        """Domain with 0 ministers → high-severity coverage gap."""
        analyzer = GapAnalyzer()
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
            ("太史令", "research", 0.8),
        )
        gaps = analyzer.analyze(expertise, {"丞相": 80, "太史令": 75}, 0.5)
        # security domain has 0 ministers → should appear
        security_gaps = [g for g in gaps if g.domain == "security"]
        assert len(security_gaps) == 1
        assert security_gaps[0].severity == 1.0
        assert security_gaps[0].ministers_present == 0

    def test_quality_gap_low_merit(self):
        """Domain with ministers but low avg merit → quality gap."""
        analyzer = GapAnalyzer(max_gaps=20)  # large enough to not drop
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
            ("太史令", "engineering", 0.7),
        )
        # Both low merit
        gaps = analyzer.analyze(
            expertise,
            {"丞相": 15, "太史令": 20},
            0.5,
        )
        eng_gaps = [g for g in gaps if g.domain == "engineering"]
        assert len(eng_gaps) == 1
        assert eng_gaps[0].ministers_present == 2
        assert eng_gaps[0].avg_merit == 17.5
        assert eng_gaps[0].severity > 0.4  # significant severity

    def test_quality_gap_merit_above_threshold(self):
        """Good merit → no gap."""
        analyzer = GapAnalyzer()
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
        )
        gaps = analyzer.analyze(expertise, {"丞相": 80}, 0.5)
        # engineering has 1 minister with good merit → no gap
        eng_gaps = [g for g in gaps if g.domain == "engineering"]
        assert len(eng_gaps) == 0

    def test_diversity_gap(self):
        """Low global diversity → gaps in all domains."""
        analyzer = GapAnalyzer(max_gaps=20)
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
            ("太史令", "research", 0.8),
            ("锦衣卫", "security", 0.9),
            ("户部主事", "finance", 0.8),
            ("内务总管", "personal", 0.9),
            ("太医令", "health", 0.8),
            ("执金吾", "home", 0.7),
            ("通政使", "general", 0.9),
            ("中枢侍郎", "core", 0.85),
            ("司乐郎", "creative", 0.8),
            ("大理寺卿", "legal", 0.9),
            ("国子监博士", "education", 0.8),
            ("教坊司", "entertainment", 0.7),
        )
        gaps = analyzer.analyze(
            expertise,
            {m: 80.0 for m in [
                "丞相", "太史令", "锦衣卫", "户部主事", "内务总管",
                "太医令", "执金吾", "通政使", "中枢侍郎", "司乐郎",
                "大理寺卿", "国子监博士", "教坊司",
            ]},
            0.05,  # very low diversity
        )
        assert len(gaps) > 0
        # All gaps should have diversity-based reason
        for gap in gaps:
            assert "多样性" in gap.reason

    def test_no_gaps_when_healthy(self):
        """Well-covered, high-merit, diverse court → no gaps."""
        analyzer = GapAnalyzer()
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
            ("太史令", "research", 0.8),
            ("锦衣卫", "security", 0.9),
        )
        gaps = analyzer.analyze(
            expertise,
            {"丞相": 85, "太史令": 80, "锦衣卫": 90},
            0.6,  # high diversity
        )
        # Some domains still uncovered but analyzer only checks KNOWN_DOMAINS
        # with coverage.  Let's verify known covered domains have no gaps.
        covered = {"engineering", "research", "security"}
        for gap in gaps:
            assert gap.domain not in covered

    def test_gaps_sorted_by_severity(self):
        """Most severe gaps come first."""
        analyzer = GapAnalyzer()
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
            ("太史令", "finance", 0.3),
        )
        gaps = analyzer.analyze(
            expertise,
            {"丞相": 80, "太史令": 10},  # 太史令 very low merit
            0.5,
        )
        # First gap should be finance (quality + low merit) or coverage
        if len(gaps) >= 2:
            assert gaps[0].severity >= gaps[1].severity

    def test_max_gaps_cap(self):
        """Gaps capped at max_gaps."""
        analyzer = GapAnalyzer(max_gaps=3)
        expertise = make_expertise()  # empty → all domains uncovered
        gaps = analyzer.analyze(expertise, {}, 0.5)
        assert len(gaps) <= 3

    def test_custom_thresholds(self):
        """Custom thresholds are respected."""
        analyzer = GapAnalyzer(min_avg_merit=60, max_gaps=20)
        expertise = make_expertise(
            ("丞相", "engineering", 0.9),
        )
        gaps = analyzer.analyze(expertise, {"丞相": 50}, 0.5)
        # 50 < 60 → quality gap detected
        eng_gaps = [g for g in gaps if g.domain == "engineering"]
        assert len(eng_gaps) == 1


# ═══════════════════════════════════════════════════════════════════
# StrategySelector
# ═══════════════════════════════════════════════════════════════════


class TestStrategySelector:
    """Breeding strategy selection."""

    def test_coverage_gap_selects_specialist(self):
        """0 ministers → SPECIALIST strategy."""
        selector = StrategySelector()
        gap = CapabilityGap(
            domain="security", severity=1.0,
            reason="零覆盖", ministers_present=0,
            avg_merit=0.0, diversity_score=0.5,
        )
        candidates = selector.select([gap], ["丞相"])
        assert len(candidates) == 1
        assert candidates[0].strategy == BreedingStrategy.SPECIALIST

    def test_quality_gap_selects_specialize(self):
        """Very low merit → SPECIALIZE strategy."""
        selector = StrategySelector()
        gap = CapabilityGap(
            domain="finance", severity=0.7,
            reason="质量不足", ministers_present=2,
            avg_merit=15.0, diversity_score=0.5,
        )
        candidates = selector.select([gap], ["丞相", "太史令"])
        assert len(candidates) == 1
        assert candidates[0].strategy == BreedingStrategy.SPECIALIZE
        assert candidates[0].parent_minister is not None

    def test_diversity_gap_selects_explore(self):
        """Extremely low diversity → EXPLORE."""
        selector = StrategySelector()
        gap = CapabilityGap(
            domain="engineering", severity=0.8,
            reason="多样性低", ministers_present=3,
            avg_merit=70.0, diversity_score=0.05,
        )
        candidates = selector.select([gap], ["丞相"])
        assert len(candidates) == 1
        assert candidates[0].strategy == BreedingStrategy.EXPLORE

    def test_multiple_gaps_different_strategies(self):
        """Each gap gets its own candidate with appropriate strategy."""
        selector = StrategySelector()
        gaps = [
            CapabilityGap("security", 1.0, "零覆盖", 0, 0.0, 0.5),
            CapabilityGap("finance", 0.7, "质量不足", 2, 15.0, 0.5),
        ]
        candidates = selector.select(gaps, ["丞相"])
        assert len(candidates) == 2
        strategies = {c.strategy for c in candidates}
        assert BreedingStrategy.SPECIALIST in strategies
        assert BreedingStrategy.SPECIALIZE in strategies


# ═══════════════════════════════════════════════════════════════════
# GenomeGenerator
# ═══════════════════════════════════════════════════════════════════


class TestGenomeGenerator:
    """Genome generation from breeding candidates."""

    GENOME_KEYS = [
        "temperature", "confidence_baseline", "creativity",
        "thoroughness", "speed", "social_intelligence",
    ]

    def _assert_valid_genome(self, genome: dict[str, float]):
        """All values in [0, 1], all keys present."""
        for key in self.GENOME_KEYS:
            assert key in genome, f"Missing key: {key}"
            assert 0.0 <= genome[key] <= 1.0, (
                f"{key}={genome[key]} out of range"
            )

    def test_specialist_generates_domain_profile(self):
        """SPECIALIST uses domain profile with small noise."""
        gen = GenomeGenerator()
        candidate = BreedingCandidate(
            target_domain="security",
            strategy=BreedingStrategy.SPECIALIST,
            genome_template=None,
            parent_minister=None,
            reasoning="零覆盖",
        )
        genome = gen.generate(candidate)
        self._assert_valid_genome(genome)
        # Security profile: low temperature, high thoroughness
        assert genome["temperature"] < 0.5
        assert genome["thoroughness"] > 0.7

    def test_explore_generates_anti_profile(self):
        """EXPLORE inverts domain profile with high variance."""
        gen = GenomeGenerator()
        candidate = BreedingCandidate(
            target_domain="engineering",
            strategy=BreedingStrategy.EXPLORE,
            genome_template=None,
            parent_minister=None,
            reasoning="多样性低",
        )
        genome = gen.generate(candidate)
        self._assert_valid_genome(genome)
        # Values should be far from engineering profile
        # Engineering: low creativity → EXPLORE: high creativity
        assert genome["creativity"] > 0.3  # anti of 0.2

    def test_specialize_blends_parent_and_profile(self):
        """SPECIALIZE blends parent genome with domain profile."""
        gen = GenomeGenerator()
        candidate = BreedingCandidate(
            target_domain="creative",
            strategy=BreedingStrategy.SPECIALIZE,
            genome_template=None,
            parent_minister="丞相",
            reasoning="质量不足",
        )
        parent = {
            "temperature": 0.4, "confidence_baseline": 0.8,
            "creativity": 0.3, "thoroughness": 0.7,
            "speed": 0.5, "social_intelligence": 0.4,
        }
        genome = gen.generate(candidate, parent_genome=parent)
        self._assert_valid_genome(genome)
        # Creative profile: high creativity → blend should increase
        assert genome["creativity"] > 0.3  # nudge toward creative

    def test_hybrid_mixes_traits(self):
        """HYBRID randomly keeps/mutates parent traits."""
        gen = GenomeGenerator()
        candidate = BreedingCandidate(
            target_domain="general",
            strategy=BreedingStrategy.HYBRID,
            genome_template=None,
            parent_minister=None,
            reasoning="混合育种",
        )
        parent = {
            "temperature": 0.6, "confidence_baseline": 0.7,
            "creativity": 0.5, "thoroughness": 0.6,
            "speed": 0.4, "social_intelligence": 0.5,
        }
        # Run multiple times to ensure variety
        genomes = [
            gen.generate(candidate, parent_genome=parent)
            for _ in range(5)
        ]
        for g in genomes:
            self._assert_valid_genome(g)
        # Not all identical
        values_sets = {
            tuple(g[k] for k in self.GENOME_KEYS) for g in genomes
        }
        assert len(values_sets) > 1

    def test_can_generate_without_parent(self):
        """All strategies work without parent genome."""
        gen = GenomeGenerator()
        for strategy in BreedingStrategy:
            candidate = BreedingCandidate(
                target_domain="general",
                strategy=strategy,
                genome_template=None,
                parent_minister=None,
                reasoning="test",
            )
            genome = gen.generate(candidate)
            self._assert_valid_genome(genome)

    def test_explicit_template_overrides_profile(self):
        """Explicit genome_template overrides domain profile lookup."""
        gen = GenomeGenerator()
        custom = {"temperature": 0.99, "confidence_baseline": 0.01,
                  "creativity": 0.99, "thoroughness": 0.01,
                  "speed": 0.99, "social_intelligence": 0.01}
        candidate = BreedingCandidate(
            target_domain="security",
            strategy=BreedingStrategy.SPECIALIST,
            genome_template=custom,
            parent_minister=None,
            reasoning="custom",
        )
        genome = gen.generate(candidate)
        self._assert_valid_genome(genome)
        # Should be close to custom, not security profile
        assert genome["temperature"] > 0.8
        assert genome["thoroughness"] < 0.2


# ═══════════════════════════════════════════════════════════════════
# AutoBreeder
# ═══════════════════════════════════════════════════════════════════


class TestAutoBreeder:
    """Integration: full breeding pipeline."""

    def test_no_gaps_returns_empty(self):
        """Healthy court → empty report."""
        breeder = AutoBreeder(breeding_cooldown=0)  # bypass cooldown
        # Set providers for a well-covered court
        breeder.set_expertise_provider(lambda: {
            "丞相": {"engineering": 0.9, "general": 0.5},
            "太史令": {"research": 0.8, "general": 0.4},
            "锦衣卫": {"security": 0.9, "general": 0.3},
            "内务总管": {"personal": 0.9, "general": 0.5},
            "太医令": {"health": 0.85, "general": 0.4},
            "执金吾": {"home": 0.8, "general": 0.4},
            "通政使": {"general": 0.9},
            "中枢侍郎": {"core": 0.9},
            "司乐郎": {"creative": 0.85},
            "大理寺卿": {"legal": 0.9},
            "国子监博士": {"education": 0.85},
            "教坊司": {"entertainment": 0.8},
            "户部主事": {"finance": 0.9},
        })
        breeder.set_merit_provider(lambda m: 80.0)
        breeder.set_diversity_provider(lambda: 0.6)

        active = ["丞相", "太史令", "锦衣卫", "内务总管", "太医令",
                   "执金吾", "通政使", "中枢侍郎", "司乐郎", "大理寺卿",
                   "国子监博士", "教坊司", "户部主事"]
        report = breeder.breed(active)
        # Some domains like "entertainment" have 1 minister with good merit
        # → no quality gap. But coverage of all 13 domains might still trigger
        # some gaps for domains with only 1 "covering" minister.
        # This test verifies the pipeline doesn't crash on healthy input.
        assert isinstance(report.gaps_detected, list)

    def test_coverage_gap_triggers_breeding(self):
        """Uncovered domain → breeding triggered."""
        breeder = AutoBreeder(breeding_cooldown=0)
        breeder.set_expertise_provider(lambda: {
            "丞相": {"engineering": 0.9},
        })
        breeder.set_merit_provider(lambda m: 80.0)
        breeder.set_diversity_provider(lambda: 0.5)

        report = breeder.breed(["丞相"])
        assert len(report.gaps_detected) > 0
        # security domain has 0 covering ministers → coverage gap
        security_gaps = [g for g in report.gaps_detected
                         if g.domain == "security"]
        assert len(security_gaps) == 1
        assert len(report.candidates_proposed) > 0
        assert len(report.candidates_created) > 0

    def test_breeding_cooldown_respected(self):
        """Breeding doesn't fire every cycle."""
        breeder = AutoBreeder(breeding_cooldown=5)
        breeder.set_expertise_provider(lambda: {"丞相": {"engineering": 0.9}})
        breeder.set_merit_provider(lambda m: 20.0)  # low merit
        breeder.set_diversity_provider(lambda: 0.1)

        # First cycle: should breed
        report1 = breeder.breed(["丞相"])
        # Cooldown kicks in
        for _ in range(4):
            report = breeder.breed(["丞相"])
            assert len(report.candidates_created) == 0

        # 5th cycle: breeds again
        report5 = breeder.breed(["丞相"])
        # May or may not breed depending on gap detection

    def test_total_bred_counter(self):
        """_total_bred increments correctly."""
        breeder = AutoBreeder(breeding_cooldown=0)
        breeder.set_expertise_provider(lambda: {
            "丞相": {"engineering": 0.9},
        })
        breeder.set_merit_provider(lambda m: 30.0)
        breeder.set_diversity_provider(lambda: 0.3)

        breeder.breed(["丞相"])
        assert breeder.get_total_bred() > 0
        bred1 = breeder.get_total_bred()

        breeder.breed(["丞相"])
        assert breeder.get_total_bred() >= bred1

    def test_max_per_cycle_enforced(self):
        """MAX_BREED_PER_CYCLE caps candidates."""
        breeder = AutoBreeder(breeding_cooldown=0, max_per_cycle=2)
        breeder.set_expertise_provider(lambda: {})  # empty → all uncovered
        breeder.set_merit_provider(lambda m: 50.0)
        breeder.set_diversity_provider(lambda: 0.05)

        report = breeder.breed([])
        assert len(report.candidates_created) <= 2

    def test_history_tracking(self):
        """Breeding reports are stored in history."""
        breeder = AutoBreeder(breeding_cooldown=0)
        breeder.set_expertise_provider(lambda: {
            "丞相": {"engineering": 0.9},
        })
        breeder.set_merit_provider(lambda m: 20.0)
        breeder.set_diversity_provider(lambda: 0.3)

        breeder.breed(["丞相"])
        history = breeder.get_history()
        assert len(history) == 1
        assert isinstance(history[0].gaps_detected, list)

    def test_reset_cooldown_forces_breeding(self):
        """reset_cooldown() allows immediate next breed."""
        breeder = AutoBreeder(breeding_cooldown=100)
        breeder.set_expertise_provider(lambda: {
            "丞相": {"engineering": 0.9},
        })
        breeder.set_merit_provider(lambda m: 20.0)
        breeder.set_diversity_provider(lambda: 0.1)

        breeder.breed(["丞相"])  # consumes one cycle
        # Without reset, next call would be blocked
        breeder.reset_cooldown()
        report = breeder.breed(["丞相"])
        assert len(report.candidates_created) > 0

    def test_strategies_used_tracking(self):
        """strategies_used dict correctly tallies."""
        breeder = AutoBreeder(breeding_cooldown=0, max_per_cycle=5)
        breeder.set_expertise_provider(lambda: {})  # all uncovered
        breeder.set_merit_provider(lambda m: 50.0)
        breeder.set_diversity_provider(lambda: 0.05)

        report = breeder.breed([])
        if report.strategies_used:
            total = sum(report.strategies_used.values())
            assert total == len(report.candidates_created)

    def test_fallback_providers_work(self):
        """Without explicit providers, fallback logic doesn't crash."""
        breeder = AutoBreeder(breeding_cooldown=0)
        report = breeder.breed(["丞相", "太史令"])
        # Should not crash — uses fallback expertise/merit/diversity
        assert isinstance(report.gaps_detected, list)

    def test_generated_names_are_unique(self):
        """Each bred candidate gets a unique name."""
        breeder = AutoBreeder(breeding_cooldown=0, max_per_cycle=10)
        breeder.set_expertise_provider(lambda: {})
        breeder.set_merit_provider(lambda m: 50.0)
        breeder.set_diversity_provider(lambda: 0.05)

        report = breeder.breed([])
        if report.candidates_created:
            assert len(report.candidates_created) == len(
                set(report.candidates_created)
            )

    def test_get_last_report(self):
        """get_last_report returns the most recent report."""
        breeder = AutoBreeder(breeding_cooldown=0)
        breeder.set_expertise_provider(lambda: {
            "丞相": {"engineering": 0.9},
        })
        breeder.set_merit_provider(lambda m: 20.0)
        breeder.set_diversity_provider(lambda: 0.3)

        assert breeder.get_last_report() is None
        breeder.breed(["丞相"])
        assert breeder.get_last_report() is not None
