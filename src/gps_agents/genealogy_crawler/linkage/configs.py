"""Comparison configurations for Splink entity resolution.

Defines GPS-compliant comparison rules for different record types:
- Census records (household members, ages, locations)
- Vital records (births, deaths, marriages)
- Immigration records (name variants, alternate spellings)

These configs are designed for historical genealogical data with:
- Name variants (Eafrom ↔ Eaf, Archie ↔ Archer)
- OCR errors (Durham ↔ Denham)
- Missing data (null handling)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from .models import ComparisonType


class ComparisonLevel(BaseModel):
    """A single level in a comparison hierarchy.

    Splink uses comparison levels to assign different weights
    based on the degree of similarity.
    """

    level_name: str = Field(description="Human-readable level name")
    sql_condition: str = Field(description="SQL condition for this level")
    m_probability: float = Field(
        ge=0.0, le=1.0,
        description="P(match at this level | same person)",
    )
    u_probability: float = Field(
        ge=0.0, le=1.0,
        description="P(match at this level | different people)",
    )
    is_null_level: bool = Field(
        default=False,
        description="Whether this handles null values",
    )


class FieldComparison(BaseModel):
    """Configuration for comparing a single field.

    Defines the comparison type, levels, and term frequency adjustment.
    """

    field_name: str = Field(description="Name of the field to compare")
    field_name_right: str | None = Field(
        default=None,
        description="Name on right table if different",
    )
    comparison_type: ComparisonType
    levels: list[ComparisonLevel] = Field(default_factory=list)

    # Term frequency adjustment
    use_term_frequency: bool = Field(
        default=False,
        description="Weight by how common the value is",
    )
    term_frequency_adjustments: bool = Field(
        default=False,
        description="Enable TF-IDF style weighting",
    )

    # GPS compliance
    is_critical: bool = Field(
        default=False,
        description="Whether mismatch blocks merge",
    )
    conflict_if_mismatch: bool = Field(
        default=True,
        description="Whether to flag mismatch as conflict",
    )

    def to_splink_dict(self) -> dict[str, Any]:
        """Convert to Splink comparison specification."""
        output_column = f"{self.field_name}"

        # Build comparison levels for Splink
        comparison_levels = []
        for level in self.levels:
            level_dict = {
                "sql_condition": level.sql_condition,
                "label_for_charts": level.level_name,
            }
            if level.m_probability:
                level_dict["m_probability"] = level.m_probability
            comparison_levels.append(level_dict)

        return {
            "output_column_name": output_column,
            "comparison_levels": comparison_levels,
        }


class BaseComparisonConfig(ABC, BaseModel):
    """Base class for comparison configurations."""

    config_name: str = Field(description="Name of this configuration")
    config_version: str = Field(default="1.0.0")

    # Default thresholds
    match_threshold: float = Field(
        default=0.85,
        ge=0.0, le=1.0,
        description="Probability threshold for automatic match",
    )
    review_threshold: float = Field(
        default=0.50,
        ge=0.0, le=1.0,
        description="Probability threshold for human review",
    )

    # Blocking rules (reduce comparisons)
    blocking_rules: list[str] = Field(
        default_factory=list,
        description="SQL-like blocking rules",
    )

    # Field comparisons
    field_comparisons: list[FieldComparison] = Field(default_factory=list)

    @abstractmethod
    def get_splink_settings(self) -> dict[str, Any]:
        """Generate Splink settings dictionary."""
        ...

    def get_blocking_rules_for_splink(self) -> list[str]:
        """Get blocking rules formatted for Splink."""
        return self.blocking_rules


class CensusComparisonConfig(BaseComparisonConfig):
    """Comparison configuration optimized for US Census records.

    Designed for linking individuals across census years with:
    - Name variations and misspellings
    - Age estimation (10-year intervals)
    - Location changes
    """

    config_name: str = "us_census_linkage"
    config_version: str = "1.0.0"

    # Census-specific settings
    max_year_difference: int = Field(
        default=3,
        description="Max difference in calculated birth year",
    )
    allow_name_variants: bool = Field(
        default=True,
        description="Match name variant arrays",
    )

    def __init__(self, **data):
        super().__init__(**data)

        # Set default blocking rules for census
        if not self.blocking_rules:
            self.blocking_rules = [
                # Block on first letter of surname + birth decade
                "l.surname_first_letter = r.surname_first_letter AND "
                "abs(l.birth_year - r.birth_year) <= 3",
                # Block on Soundex of surname
                "l.surname_soundex = r.surname_soundex",
                # Block on exact birth year + first letter of given name
                "l.birth_year = r.birth_year AND "
                "l.given_name_first_letter = r.given_name_first_letter",
            ]

        # Set default field comparisons for census
        if not self.field_comparisons:
            self.field_comparisons = self._default_census_comparisons()

    def _default_census_comparisons(self) -> list[FieldComparison]:
        """Default comparison configuration for census records."""
        return [
            # Surname comparison with Jaro-Winkler
            FieldComparison(
                field_name="surname",
                comparison_type=ComparisonType.JARO_WINKLER,
                use_term_frequency=True,
                is_critical=True,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.surname = r.surname",
                        m_probability=0.95,
                        u_probability=0.01,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.9",
                        sql_condition="jaro_winkler_similarity(l.surname, r.surname) >= 0.9",
                        m_probability=0.85,
                        u_probability=0.02,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.8",
                        sql_condition="jaro_winkler_similarity(l.surname, r.surname) >= 0.8",
                        m_probability=0.60,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="Soundex match",
                        sql_condition="soundex(l.surname) = soundex(r.surname)",
                        m_probability=0.40,
                        u_probability=0.10,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.05,
                        u_probability=0.90,
                    ),
                ],
            ),
            # Given name comparison
            FieldComparison(
                field_name="given_name",
                comparison_type=ComparisonType.JARO_WINKLER,
                use_term_frequency=True,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.given_name = r.given_name",
                        m_probability=0.90,
                        u_probability=0.02,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.85",
                        sql_condition="jaro_winkler_similarity(l.given_name, r.given_name) >= 0.85",
                        m_probability=0.70,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="Nickname/diminutive match",
                        sql_condition=(
                            "l.given_name IN (SELECT unnest(r.name_variants)) OR "
                            "r.given_name IN (SELECT unnest(l.name_variants))"
                        ),
                        m_probability=0.65,
                        u_probability=0.03,
                    ),
                    ComparisonLevel(
                        level_name="First letter match",
                        sql_condition="left(l.given_name, 1) = left(r.given_name, 1)",
                        m_probability=0.30,
                        u_probability=0.15,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.05,
                        u_probability=0.80,
                    ),
                ],
            ),
            # Birth year comparison
            FieldComparison(
                field_name="birth_year",
                comparison_type=ComparisonType.NUMERIC_DISTANCE,
                is_critical=False,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.birth_year = r.birth_year",
                        m_probability=0.85,
                        u_probability=0.01,
                    ),
                    ComparisonLevel(
                        level_name="±1 year",
                        sql_condition="abs(l.birth_year - r.birth_year) <= 1",
                        m_probability=0.75,
                        u_probability=0.02,
                    ),
                    ComparisonLevel(
                        level_name="±3 years",
                        sql_condition="abs(l.birth_year - r.birth_year) <= 3",
                        m_probability=0.50,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="±5 years",
                        sql_condition="abs(l.birth_year - r.birth_year) <= 5",
                        m_probability=0.30,
                        u_probability=0.10,
                    ),
                    ComparisonLevel(
                        level_name="Null",
                        sql_condition="l.birth_year IS NULL OR r.birth_year IS NULL",
                        m_probability=0.50,
                        u_probability=0.50,
                        is_null_level=True,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.01,
                        u_probability=0.85,
                    ),
                ],
            ),
            # Birth place comparison (state level)
            FieldComparison(
                field_name="birth_place",
                comparison_type=ComparisonType.JARO_WINKLER,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.birth_place = r.birth_place",
                        m_probability=0.80,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="State matches",
                        sql_condition=(
                            "l.birth_place_state = r.birth_place_state"
                        ),
                        m_probability=0.60,
                        u_probability=0.10,
                    ),
                    ComparisonLevel(
                        level_name="Null",
                        sql_condition="l.birth_place IS NULL OR r.birth_place IS NULL",
                        m_probability=0.50,
                        u_probability=0.50,
                        is_null_level=True,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.10,
                        u_probability=0.75,
                    ),
                ],
            ),
            # Sex comparison (very discriminating if different)
            FieldComparison(
                field_name="sex",
                comparison_type=ComparisonType.EXACT,
                is_critical=True,  # Different sex = cannot be same person
                conflict_if_mismatch=True,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.sex = r.sex",
                        m_probability=0.99,
                        u_probability=0.50,
                    ),
                    ComparisonLevel(
                        level_name="Null",
                        sql_condition="l.sex IS NULL OR r.sex IS NULL",
                        m_probability=0.50,
                        u_probability=0.50,
                        is_null_level=True,
                    ),
                    ComparisonLevel(
                        level_name="Mismatch",
                        sql_condition="ELSE",
                        m_probability=0.001,  # Very rare for same person
                        u_probability=0.50,
                    ),
                ],
            ),
        ]

    def get_splink_settings(self) -> dict[str, Any]:
        """Generate Splink settings dictionary."""
        return {
            "link_type": "dedupe_only",
            "unique_id_column_name": "id",
            "blocking_rules_to_generate_predictions": self.blocking_rules,
            "comparisons": [
                fc.to_splink_dict() for fc in self.field_comparisons
            ],
            "retain_matching_columns": True,
            "retain_intermediate_calculation_columns": True,
            "additional_columns_to_retain": [
                "name_as_recorded",
                "census_year",
                "source_url",
            ],
        }


class VitalRecordComparisonConfig(BaseComparisonConfig):
    """Comparison configuration for vital records (birth, death, marriage).

    Vital records have higher data quality but less context than census.
    """

    config_name: str = "vital_records_linkage"
    config_version: str = "1.0.0"

    def __init__(self, **data):
        super().__init__(**data)

        # Vital records blocking rules
        if not self.blocking_rules:
            self.blocking_rules = [
                # Block on surname + birth year
                "l.surname = r.surname AND l.birth_year = r.birth_year",
                # Block on Soundex + birth decade
                "soundex(l.surname) = soundex(r.surname) AND "
                "floor(l.birth_year / 10) = floor(r.birth_year / 10)",
            ]

        if not self.field_comparisons:
            self.field_comparisons = self._default_vital_comparisons()

    def _default_vital_comparisons(self) -> list[FieldComparison]:
        """Default comparisons for vital records."""
        return [
            # Full name as single field
            FieldComparison(
                field_name="full_name",
                comparison_type=ComparisonType.JARO_WINKLER,
                is_critical=True,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.full_name = r.full_name",
                        m_probability=0.98,
                        u_probability=0.001,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.92",
                        sql_condition="jaro_winkler_similarity(l.full_name, r.full_name) >= 0.92",
                        m_probability=0.85,
                        u_probability=0.01,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.85",
                        sql_condition="jaro_winkler_similarity(l.full_name, r.full_name) >= 0.85",
                        m_probability=0.60,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.05,
                        u_probability=0.90,
                    ),
                ],
            ),
            # Birth date (full date for vital records)
            FieldComparison(
                field_name="birth_date",
                comparison_type=ComparisonType.EXACT,
                is_critical=True,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.birth_date = r.birth_date",
                        m_probability=0.95,
                        u_probability=0.001,
                    ),
                    ComparisonLevel(
                        level_name="Year-month match",
                        sql_condition=(
                            "date_trunc('month', l.birth_date) = "
                            "date_trunc('month', r.birth_date)"
                        ),
                        m_probability=0.80,
                        u_probability=0.01,
                    ),
                    ComparisonLevel(
                        level_name="Year match",
                        sql_condition="extract(year from l.birth_date) = extract(year from r.birth_date)",
                        m_probability=0.50,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.01,
                        u_probability=0.90,
                    ),
                ],
            ),
            # Parent names (strong discriminator)
            FieldComparison(
                field_name="father_name",
                comparison_type=ComparisonType.JARO_WINKLER,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.father_name = r.father_name",
                        m_probability=0.90,
                        u_probability=0.02,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.85",
                        sql_condition="jaro_winkler_similarity(l.father_name, r.father_name) >= 0.85",
                        m_probability=0.70,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="Null",
                        sql_condition="l.father_name IS NULL OR r.father_name IS NULL",
                        m_probability=0.50,
                        u_probability=0.50,
                        is_null_level=True,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.10,
                        u_probability=0.85,
                    ),
                ],
            ),
            FieldComparison(
                field_name="mother_name",
                comparison_type=ComparisonType.JARO_WINKLER,
                levels=[
                    ComparisonLevel(
                        level_name="Exact match",
                        sql_condition="l.mother_name = r.mother_name",
                        m_probability=0.90,
                        u_probability=0.02,
                    ),
                    ComparisonLevel(
                        level_name="Jaro-Winkler > 0.85",
                        sql_condition="jaro_winkler_similarity(l.mother_name, r.mother_name) >= 0.85",
                        m_probability=0.70,
                        u_probability=0.05,
                    ),
                    ComparisonLevel(
                        level_name="Null",
                        sql_condition="l.mother_name IS NULL OR r.mother_name IS NULL",
                        m_probability=0.50,
                        u_probability=0.50,
                        is_null_level=True,
                    ),
                    ComparisonLevel(
                        level_name="Else",
                        sql_condition="ELSE",
                        m_probability=0.10,
                        u_probability=0.85,
                    ),
                ],
            ),
        ]

    def get_splink_settings(self) -> dict[str, Any]:
        """Generate Splink settings dictionary."""
        return {
            "link_type": "dedupe_only",
            "unique_id_column_name": "id",
            "blocking_rules_to_generate_predictions": self.blocking_rules,
            "comparisons": [
                fc.to_splink_dict() for fc in self.field_comparisons
            ],
            "retain_matching_columns": True,
            "retain_intermediate_calculation_columns": True,
        }
