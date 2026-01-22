"""Splink Entity Resolver for GPS-compliant entity resolution.

Implements high-scale probabilistic record linkage using Splink library.
Supports DuckDB backend for local processing and Spark for large datasets.

Used by the Australian Bureau of Statistics for 2026 Census linking.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from .configs import BaseComparisonConfig, CensusComparisonConfig
from .models import (
    ClusterDecision,
    EntityCluster,
    FeatureComparison,
    LinkageDecision,
    LinkageProvenance,
    LinkageResult,
    MatchCandidate,
    MatchConfidence,
    ComparisonType,
)

if TYPE_CHECKING:
    import pandas as pd
    from splink import DuckDBAPI, Linker

logger = logging.getLogger(__name__)


class SplinkEntityResolver:
    """High-scale entity resolver using Splink probabilistic linkage.

    Implements Fellegi-Sunter model for record deduplication:
    1. Blocking: Reduce comparison space using indexed keys
    2. Comparison: Calculate match weights for field pairs
    3. Scoring: Combine weights into match probability
    4. Clustering: Group records into entity clusters

    Example:
        >>> resolver = SplinkEntityResolver(
        ...     comparison_config=CensusComparisonConfig(),
        ...     threshold=0.85,
        ... )
        >>> result = await resolver.resolve(persons_df)
        >>> for cluster in result.clusters:
        ...     print(f"{cluster.canonical_name}: {cluster.size} records")
    """

    def __init__(
        self,
        comparison_config: BaseComparisonConfig | None = None,
        threshold: float = 0.85,
        review_threshold: float = 0.50,
        use_training: bool = True,
        backend: str = "duckdb",
    ) -> None:
        """Initialize the Splink resolver.

        Args:
            comparison_config: Configuration for field comparisons
            threshold: Match probability threshold for automatic merge
            review_threshold: Threshold below which to flag for review
            use_training: Whether to train model using EM algorithm
            backend: Splink backend ("duckdb" or "spark")
        """
        self.config = comparison_config or CensusComparisonConfig()
        self.threshold = threshold
        self.review_threshold = review_threshold
        self.use_training = use_training
        self.backend = backend

        self._linker: "Linker | None" = None

    async def resolve(
        self,
        records: "pd.DataFrame | list[dict[str, Any]] | list[BaseModel]",
        training_labels: "pd.DataFrame | None" = None,
    ) -> LinkageResult:
        """Resolve entities from input records.

        Args:
            records: Input records as DataFrame, list of dicts, or Pydantic models
            training_labels: Optional labeled pairs for supervised training

        Returns:
            LinkageResult with clusters and provenance
        """
        provenance = LinkageProvenance(
            algorithm="splink",
            match_threshold=self.threshold,
            review_threshold=self.review_threshold,
            blocking_rules=self.config.blocking_rules,
            started_at=datetime.now(UTC),
        )

        try:
            # Import here to make Splink optional
            import pandas as pd
            from splink import DuckDBAPI, Linker, SettingsCreator, block_on
            import splink.comparison_library as cl

            # Convert to DataFrame if needed
            df = self._to_dataframe(records)
            provenance.records_compared = len(df)

            # Prepare data with computed columns
            df = self._prepare_dataframe(df)

            # Build Splink settings
            settings = self._build_settings()

            # Initialize linker
            db_api = DuckDBAPI()
            linker = Linker(df, settings, db_api)
            self._linker = linker

            # Train model if requested
            if self.use_training:
                provenance.em_iterations = self._train_model(
                    linker, training_labels
                )

            # Generate predictions
            predictions_df = linker.inference.predict(
                threshold_match_probability=self.review_threshold
            ).as_pandas_dataframe()

            provenance.candidates_generated = len(predictions_df)

            # Cluster predictions
            clusters_df = linker.clustering.cluster_pairwise_predictions_at_threshold(
                predictions_df,
                threshold_match_probability=self.threshold,
            ).as_pandas_dataframe()

            # Build output clusters
            clusters, needs_review = self._build_clusters(
                df, predictions_df, clusters_df
            )

            return LinkageResult.success_result(
                clusters=clusters,
                provenance=provenance,
                needs_review=needs_review,
            )

        except ImportError:
            return LinkageResult.failure_result(
                error="Splink not installed. Run: pip install splink",
                provenance=provenance,
            )
        except Exception as e:
            logger.exception("Entity resolution failed")
            return LinkageResult.failure_result(
                error=str(e),
                provenance=provenance,
            )

    def _to_dataframe(
        self,
        records: "pd.DataFrame | list[dict[str, Any]] | list[BaseModel]",
    ) -> "pd.DataFrame":
        """Convert input records to pandas DataFrame."""
        import pandas as pd

        if isinstance(records, pd.DataFrame):
            return records

        if not records:
            return pd.DataFrame()

        # Handle Pydantic models
        if hasattr(records[0], "model_dump"):
            data = [r.model_dump() for r in records]
        else:
            data = records

        return pd.DataFrame(data)

    def _prepare_dataframe(self, df: "pd.DataFrame") -> "pd.DataFrame":
        """Prepare DataFrame with computed columns for blocking."""
        import pandas as pd

        # Add ID if not present
        if "id" not in df.columns:
            df["id"] = [str(uuid4()) for _ in range(len(df))]

        # Add blocking helper columns
        if "surname" in df.columns:
            df["surname_first_letter"] = df["surname"].str[0].str.upper()
            df["surname_soundex"] = df["surname"].apply(self._soundex)

        if "given_name" in df.columns:
            df["given_name_first_letter"] = df["given_name"].str[0].str.upper()

        if "birth_place" in df.columns:
            # Extract state from birth place (assumes "City, State" or "State")
            df["birth_place_state"] = df["birth_place"].apply(
                lambda x: x.split(",")[-1].strip() if pd.notna(x) and "," in str(x) else x
            )

        return df

    def _soundex(self, name: str | None) -> str | None:
        """Compute Soundex code for a name."""
        if not name:
            return None

        # Simple Soundex implementation
        name = name.upper()
        soundex = name[0]

        # Consonant mapping
        mapping = {
            "B": "1", "F": "1", "P": "1", "V": "1",
            "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
            "D": "3", "T": "3",
            "L": "4",
            "M": "5", "N": "5",
            "R": "6",
        }

        prev = ""
        for char in name[1:]:
            code = mapping.get(char, "")
            if code and code != prev:
                soundex += code
                prev = code
            if len(soundex) >= 4:
                break

        return soundex.ljust(4, "0")[:4]

    def _build_settings(self) -> dict[str, Any]:
        """Build Splink settings from configuration."""
        return self.config.get_splink_settings()

    def _train_model(
        self,
        linker: "Linker",
        training_labels: "pd.DataFrame | None" = None,
    ) -> int:
        """Train Splink model using EM algorithm.

        Returns number of EM iterations.
        """
        # If we have labeled training data, use supervised learning
        if training_labels is not None:
            linker.training.estimate_probability_two_random_records_match(
                training_labels,
                recall=0.7,
            )

        # Estimate u-probabilities from data
        linker.training.estimate_u_using_random_sampling(max_pairs=1e6)

        # Estimate m-probabilities using EM
        em_iterations = 0
        for blocking_rule in self.config.blocking_rules[:2]:  # Use first 2 rules
            try:
                training_session = linker.training.estimate_parameters_using_expectation_maximisation(
                    blocking_rule,
                    fix_u_probabilities=False,
                )
                em_iterations += training_session.n_em_iterations
            except Exception as e:
                logger.warning("EM training failed for rule %s: %s", blocking_rule, e)

        return em_iterations

    def _build_clusters(
        self,
        original_df: "pd.DataFrame",
        predictions_df: "pd.DataFrame",
        clusters_df: "pd.DataFrame",
    ) -> tuple[list[EntityCluster], list[MatchCandidate]]:
        """Build EntityCluster objects from Splink output."""
        clusters = []
        needs_review = []

        # Group by cluster ID
        if "cluster_id" not in clusters_df.columns:
            # Single-record clusters (no matches)
            for _, row in original_df.iterrows():
                cluster = EntityCluster(
                    canonical_id=UUID(str(row["id"])),
                    canonical_name=self._get_canonical_name(row),
                    member_ids=[UUID(str(row["id"]))],
                    internal_cohesion=1.0,
                )
                clusters.append(cluster)
            return clusters, needs_review

        # Build clusters from grouped data
        grouped = clusters_df.groupby("cluster_id")
        for cluster_id, group in grouped:
            member_ids = [UUID(str(id_)) for id_ in group["id"].unique()]

            # Get canonical record (highest confidence or first)
            canonical_row = group.iloc[0]
            canonical_id = UUID(str(canonical_row["id"]))

            # Get linkage decisions for this cluster
            cluster_predictions = predictions_df[
                (predictions_df["id_l"].isin(group["id"])) |
                (predictions_df["id_r"].isin(group["id"]))
            ]

            decisions = []
            for _, pred_row in cluster_predictions.iterrows():
                prob = pred_row.get("match_probability", 0.5)

                # Determine confidence level
                if prob >= 0.95:
                    confidence = MatchConfidence.DEFINITE_MATCH
                elif prob >= 0.85:
                    confidence = MatchConfidence.PROBABLE_MATCH
                elif prob >= 0.70:
                    confidence = MatchConfidence.POSSIBLE_MATCH
                else:
                    confidence = MatchConfidence.UNCERTAIN

                decision = LinkageDecision(
                    record_id_left=UUID(str(pred_row["id_l"])),
                    record_id_right=UUID(str(pred_row["id_r"])),
                    decision=ClusterDecision.MERGE if prob >= self.threshold else ClusterDecision.NEEDS_REVIEW,
                    probability=prob,
                    confidence=confidence,
                )
                decisions.append(decision)

                # Add to review queue if uncertain
                if self.review_threshold <= prob < self.threshold:
                    candidate = self._create_match_candidate(pred_row, original_df)
                    if candidate:
                        needs_review.append(candidate)

            # Calculate cluster cohesion
            if cluster_predictions.empty:
                cohesion = 1.0
            else:
                cohesion = cluster_predictions["match_probability"].mean()

            cluster = EntityCluster(
                cluster_id=UUID(str(cluster_id)) if isinstance(cluster_id, str) else uuid4(),
                canonical_id=canonical_id,
                canonical_name=self._get_canonical_name(canonical_row),
                member_ids=member_ids,
                linkage_decisions=decisions,
                internal_cohesion=cohesion,
                has_conflicts=any(d.confidence == MatchConfidence.UNCERTAIN for d in decisions),
            )
            clusters.append(cluster)

        return clusters, needs_review

    def _get_canonical_name(self, row: "pd.Series") -> str:
        """Get canonical name from a record row."""
        given = row.get("given_name", "")
        surname = row.get("surname", "")
        return f"{given} {surname}".strip() or str(row.get("id", "Unknown"))

    def _create_match_candidate(
        self,
        pred_row: "pd.Series",
        original_df: "pd.DataFrame",
    ) -> MatchCandidate | None:
        """Create a MatchCandidate from prediction row."""
        try:
            # Get original records
            left_record = original_df[original_df["id"] == pred_row["id_l"]].iloc[0]
            right_record = original_df[original_df["id"] == pred_row["id_r"]].iloc[0]

            # Build feature comparisons
            comparisons = []
            for col in ["surname", "given_name", "birth_year", "birth_place"]:
                if col in left_record.index and col in right_record.index:
                    left_val = left_record[col]
                    right_val = right_record[col]

                    # Calculate similarity
                    if col in ["surname", "given_name", "birth_place"]:
                        similarity = self._jaro_winkler(str(left_val), str(right_val))
                        comp_type = ComparisonType.JARO_WINKLER
                    else:
                        # Numeric comparison for birth_year
                        if left_val and right_val:
                            diff = abs(int(left_val) - int(right_val))
                            similarity = max(0, 1 - diff / 10)
                        else:
                            similarity = 0.5
                        comp_type = ComparisonType.NUMERIC_DISTANCE

                    comparisons.append(FeatureComparison(
                        feature_name=col,
                        comparison_type=comp_type,
                        value_left=left_val,
                        value_right=right_val,
                        similarity_score=similarity,
                        match_weight=1.0 if similarity > 0.8 else -1.0,
                        non_match_weight=-1.0 if similarity > 0.8 else 1.0,
                    ))

            prob = pred_row.get("match_probability", 0.5)
            if prob >= 0.85:
                confidence = MatchConfidence.PROBABLE_MATCH
            elif prob >= 0.70:
                confidence = MatchConfidence.POSSIBLE_MATCH
            else:
                confidence = MatchConfidence.UNCERTAIN

            return MatchCandidate(
                record_id_left=UUID(str(pred_row["id_l"])),
                record_id_right=UUID(str(pred_row["id_r"])),
                name_left=self._get_canonical_name(left_record),
                name_right=self._get_canonical_name(right_record),
                feature_comparisons=comparisons,
                overall_probability=prob,
                confidence=confidence,
            )
        except Exception as e:
            logger.warning("Failed to create match candidate: %s", e)
            return None

    def _jaro_winkler(self, s1: str, s2: str) -> float:
        """Calculate Jaro-Winkler similarity between two strings."""
        if not s1 or not s2:
            return 0.0

        s1 = s1.lower()
        s2 = s2.lower()

        if s1 == s2:
            return 1.0

        len1, len2 = len(s1), len(s2)
        match_distance = max(len1, len2) // 2 - 1
        match_distance = max(0, match_distance)

        s1_matches = [False] * len1
        s2_matches = [False] * len2
        matches = 0
        transpositions = 0

        for i in range(len1):
            start = max(0, i - match_distance)
            end = min(i + match_distance + 1, len2)

            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1

        jaro = (
            matches / len1 +
            matches / len2 +
            (matches - transpositions / 2) / matches
        ) / 3

        # Winkler modification
        prefix = 0
        for i in range(min(len1, len2, 4)):
            if s1[i] == s2[i]:
                prefix += 1
            else:
                break

        return jaro + prefix * 0.1 * (1 - jaro)

    def get_model_parameters(self) -> dict[str, Any] | None:
        """Get trained model parameters for inspection."""
        if self._linker is None:
            return None

        try:
            return self._linker.misc.save_model_to_json()
        except Exception:
            return None
