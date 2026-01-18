"""Semantic Kernel plugin for GPS (Genealogical Proof Standard) evaluation."""

import json
from typing import Annotated
from uuid import UUID

from semantic_kernel.functions import kernel_function

from gps_agents.ledger.fact_ledger import FactLedger
from gps_agents.models.fact import Fact, FactStatus
from gps_agents.models.gps import GPSEvaluation, PillarStatus, Conflict
from gps_agents.models.confidence import ConfidenceDelta


class GPSPlugin:
    """Plugin for GPS (Genealogical Proof Standard) compliance.

    Provides functions to evaluate facts against the 5 GPS pillars:
    1. Reasonably exhaustive search
    2. Complete and accurate citations
    3. Analysis and correlation of evidence
    4. Resolution of conflicting evidence
    5. Soundly reasoned, coherently written conclusion
    """

    def __init__(self, ledger: FactLedger):
        self.ledger = ledger

    @kernel_function(
        name="evaluate_pillar_1",
        description="Evaluate GPS Pillar 1: Was a reasonably exhaustive search conducted?",
    )
    def evaluate_pillar_1(
        self,
        fact_json: Annotated[str, "JSON representation of the Fact"],
        sources_searched: Annotated[str, "JSON array of source names that were searched"],
    ) -> Annotated[str, "JSON evaluation result with status and notes"]:
        """Evaluate Pillar 1: Reasonably Exhaustive Search."""
        fact = Fact.model_validate_json(fact_json)
        searched = json.loads(sources_searched)

        required_sources = ["familysearch", "wikitree"]
        recommended_sources = [
            "findmypast",
            "myheritage",
            "accessgenealogy",
            "jerripedia",
        ]

        searched_lower = [s.lower() for s in searched]
        required_met = all(r in searched_lower for r in required_sources)
        recommended_count = sum(1 for r in recommended_sources if r in searched_lower)

        if required_met and recommended_count >= 2:
            status = PillarStatus.SATISFIED
            notes = f"Exhaustive search: {len(searched)} sources checked"
        elif required_met:
            status = PillarStatus.PARTIAL
            notes = f"Core sources checked, recommend {3 - recommended_count} more specialized sources"
        else:
            status = PillarStatus.FAILED
            missing = [r for r in required_sources if r not in searched_lower]
            notes = f"Missing required sources: {', '.join(missing)}"

        return json.dumps({
            "pillar": 1,
            "status": status.value,
            "notes": notes,
            "sources_searched": searched,
            "source_count": len(fact.sources),
        })

    @kernel_function(
        name="evaluate_pillar_2",
        description="Evaluate GPS Pillar 2: Are citations complete and accurate?",
    )
    def evaluate_pillar_2(
        self,
        fact_json: Annotated[str, "JSON representation of the Fact"],
    ) -> Annotated[str, "JSON evaluation result"]:
        """Evaluate Pillar 2: Complete and Accurate Citations."""
        fact = Fact.model_validate_json(fact_json)

        if not fact.sources:
            return json.dumps({
                "pillar": 2,
                "status": PillarStatus.FAILED.value,
                "notes": "No sources cited",
            })

        issues = []
        for i, source in enumerate(fact.sources):
            if not source.repository:
                issues.append(f"Source {i + 1}: Missing repository")
            if not source.record_id:
                issues.append(f"Source {i + 1}: Missing record ID")
            if not source.evidence_type:
                issues.append(f"Source {i + 1}: Missing evidence type classification")

        if not issues:
            status = PillarStatus.SATISFIED
            notes = f"All {len(fact.sources)} citations complete"
        elif len(issues) <= len(fact.sources) // 2:
            status = PillarStatus.PARTIAL
            notes = f"Minor issues: {'; '.join(issues[:3])}"
        else:
            status = PillarStatus.FAILED
            notes = f"Citation issues: {'; '.join(issues[:5])}"

        return json.dumps({
            "pillar": 2,
            "status": status.value,
            "notes": notes,
            "source_count": len(fact.sources),
            "issues": issues,
        })

    @kernel_function(
        name="evaluate_pillar_3",
        description="Evaluate GPS Pillar 3: Has evidence been analyzed and correlated?",
    )
    def evaluate_pillar_3(
        self,
        fact_json: Annotated[str, "JSON representation of the Fact"],
        analysis_notes: Annotated[str, "Notes about evidence analysis performed"],
    ) -> Annotated[str, "JSON evaluation result"]:
        """Evaluate Pillar 3: Analysis and Correlation."""
        fact = Fact.model_validate_json(fact_json)

        direct_count = sum(1 for s in fact.sources if s.evidence_type.value == "direct")
        indirect_count = sum(1 for s in fact.sources if s.evidence_type.value == "indirect")
        negative_count = sum(1 for s in fact.sources if s.evidence_type.value == "negative")

        has_analysis = len(analysis_notes) > 50
        has_multiple_evidence_types = (direct_count > 0) + (indirect_count > 0) + (negative_count > 0) >= 2

        if has_analysis and has_multiple_evidence_types and direct_count > 0:
            status = PillarStatus.SATISFIED
            notes = "Evidence thoroughly analyzed with multiple evidence types"
        elif has_analysis and direct_count > 0:
            status = PillarStatus.PARTIAL
            notes = "Analysis present but limited evidence correlation"
        else:
            status = PillarStatus.FAILED
            notes = "Insufficient evidence analysis"

        return json.dumps({
            "pillar": 3,
            "status": status.value,
            "notes": notes,
            "evidence_breakdown": {
                "direct": direct_count,
                "indirect": indirect_count,
                "negative": negative_count,
            },
        })

    @kernel_function(
        name="evaluate_pillar_4",
        description="Evaluate GPS Pillar 4: Have conflicts been identified and resolved?",
    )
    def evaluate_pillar_4(
        self,
        fact_json: Annotated[str, "JSON representation of the Fact"],
        conflicts_json: Annotated[str, "JSON array of identified Conflicts"],
    ) -> Annotated[str, "JSON evaluation result"]:
        """Evaluate Pillar 4: Conflict Resolution."""
        fact = Fact.model_validate_json(fact_json)
        conflicts_data = json.loads(conflicts_json)

        if not conflicts_data:
            return json.dumps({
                "pillar": 4,
                "status": PillarStatus.SATISFIED.value,
                "notes": "No conflicts identified",
                "conflicts_count": 0,
            })

        conflicts = [Conflict.model_validate(c) for c in conflicts_data]
        resolved = [c for c in conflicts if c.resolved]
        unresolved = [c for c in conflicts if not c.resolved]

        if not unresolved:
            status = PillarStatus.SATISFIED
            notes = f"All {len(resolved)} conflicts resolved"
        elif len(resolved) > len(unresolved):
            status = PillarStatus.PARTIAL
            notes = f"{len(unresolved)} of {len(conflicts)} conflicts unresolved"
        else:
            status = PillarStatus.FAILED
            notes = f"Too many unresolved conflicts ({len(unresolved)})"

        return json.dumps({
            "pillar": 4,
            "status": status.value,
            "notes": notes,
            "resolved_count": len(resolved),
            "unresolved_count": len(unresolved),
        })

    @kernel_function(
        name="evaluate_pillar_5",
        description="Evaluate GPS Pillar 5: Is the conclusion soundly reasoned?",
    )
    def evaluate_pillar_5(
        self,
        fact_json: Annotated[str, "JSON representation of the Fact"],
        proof_argument: Annotated[str, "Written proof argument/conclusion"],
    ) -> Annotated[str, "JSON evaluation result"]:
        """Evaluate Pillar 5: Soundly Reasoned Conclusion."""
        fact = Fact.model_validate_json(fact_json)

        has_proof = len(proof_argument) > 200
        cites_sources = any(
            str(s.record_id) in proof_argument or s.repository in proof_argument
            for s in fact.sources
        )
        states_conclusion = fact.statement.lower() in proof_argument.lower()

        if has_proof and cites_sources and states_conclusion:
            status = PillarStatus.SATISFIED
            notes = "Proof argument is complete and well-reasoned"
        elif has_proof:
            status = PillarStatus.PARTIAL
            notes = "Proof argument present but may need refinement"
        else:
            status = PillarStatus.FAILED
            notes = "Insufficient proof argument"

        return json.dumps({
            "pillar": 5,
            "status": status.value,
            "notes": notes,
            "proof_length": len(proof_argument),
        })

    @kernel_function(
        name="get_full_evaluation",
        description="Get complete GPS evaluation for a fact.",
    )
    def get_full_evaluation(
        self,
        fact_id: Annotated[str, "UUID of the fact"],
    ) -> Annotated[str, "JSON with full GPS evaluation"]:
        """Get the current GPS evaluation for a fact."""
        fact = self.ledger.get(UUID(fact_id))
        if fact is None:
            return json.dumps({"error": "Fact not found"})

        if fact.gps_evaluation is None:
            return json.dumps({
                "fact_id": fact_id,
                "evaluated": False,
                "message": "No GPS evaluation performed yet",
            })

        return json.dumps({
            "fact_id": fact_id,
            "evaluated": True,
            "pillars": {
                "1_exhaustive_search": fact.gps_evaluation.pillar_1.value,
                "2_complete_citations": fact.gps_evaluation.pillar_2.value,
                "3_analysis_correlation": fact.gps_evaluation.pillar_3.value,
                "4_conflict_resolution": fact.gps_evaluation.pillar_4.value,
                "5_sound_conclusion": fact.gps_evaluation.pillar_5.value,
            },
            "all_satisfied": fact.gps_evaluation.all_satisfied(),
            "failed_pillars": fact.gps_evaluation.get_failed_pillars(),
            "suggested_confidence_delta": fact.gps_evaluation.suggest_confidence_delta(),
        })

    @kernel_function(
        name="can_accept_fact",
        description="Check if a fact meets all criteria for acceptance.",
    )
    def can_accept_fact(
        self,
        fact_id: Annotated[str, "UUID of the fact"],
    ) -> Annotated[str, "JSON with acceptance decision"]:
        """Check if fact can be accepted."""
        fact = self.ledger.get(UUID(fact_id))
        if fact is None:
            return json.dumps({"error": "Fact not found"})

        can_accept = fact.can_accept()
        reasons = []

        if fact.confidence_score < 0.7:
            reasons.append(f"Confidence too low ({fact.confidence_score:.2f} < 0.70)")

        if fact.gps_evaluation is None:
            reasons.append("No GPS evaluation performed")
        elif not fact.gps_evaluation.all_satisfied():
            failed = fact.gps_evaluation.get_failed_pillars()
            reasons.append(f"GPS pillars not satisfied: {failed}")

        return json.dumps({
            "fact_id": fact_id,
            "can_accept": can_accept,
            "confidence_score": fact.confidence_score,
            "reasons": reasons if not can_accept else ["All criteria met"],
        })

    @kernel_function(
        name="apply_confidence_adjustment",
        description="Apply a confidence score adjustment to a fact based on GPS evaluation.",
    )
    def apply_confidence_adjustment(
        self,
        fact_id: Annotated[str, "UUID of the fact"],
        delta: Annotated[float, "Confidence adjustment (-1.0 to 1.0)"],
        reason: Annotated[str, "Reason for the adjustment"],
        agent_name: Annotated[str, "Name of the agent making the adjustment"],
    ) -> Annotated[str, "JSON with updated fact information"]:
        """Apply confidence adjustment to a fact."""
        fact = self.ledger.get(UUID(fact_id))
        if fact is None:
            return json.dumps({"error": "Fact not found"})

        new_score = max(0.0, min(1.0, fact.confidence_score + delta))

        confidence_delta = ConfidenceDelta(
            agent=agent_name,
            delta=delta,
            reason=reason,
            previous_score=fact.confidence_score,
            new_score=new_score,
        )

        new_fact = fact.apply_confidence_delta(confidence_delta)

        return json.dumps({
            "fact_id": fact_id,
            "previous_score": fact.confidence_score,
            "new_score": new_score,
            "delta_applied": delta,
            "new_version": new_fact.version,
            "fact_json": new_fact.model_dump_json(),
        })
