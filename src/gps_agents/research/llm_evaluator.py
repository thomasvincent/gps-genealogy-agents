"""LLM-enhanced relevance evaluator using LangChain and GPTCache.

This module provides intelligent record matching using:
- LangChain for LLM orchestration
- GPTCache for caching responses (cost savings)
- spaCy for entity extraction
- nameparser for name parsing
- rapidfuzz/jellyfish for string similarity
- dateparser for flexible date parsing
- usaddress for address parsing
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from gps_agents.models.search import RawRecord
from gps_agents.research.evaluator import (
    MatchConfidence,
    MatchScore,
    PersonProfile,
)

logger = logging.getLogger(__name__)

# Optional imports with fallbacks
try:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.debug("LangChain not available")

try:
    from gptcache import Cache
    from gptcache.adapter.langchain_models import LangChainChat
    from gptcache.embedding import Onnx
    from gptcache.manager import CacheBase, VectorBase, get_data_manager
    from gptcache.similarity_evaluation.distance import SearchDistanceEvaluation
    GPTCACHE_AVAILABLE = True
except ImportError:
    GPTCACHE_AVAILABLE = False
    logger.debug("GPTCache not available")

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logger.debug("spaCy not available")

try:
    from nameparser import HumanName
    NAMEPARSER_AVAILABLE = True
except ImportError:
    NAMEPARSER_AVAILABLE = False
    logger.debug("nameparser not available")

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.debug("rapidfuzz not available")

try:
    import jellyfish
    JELLYFISH_AVAILABLE = True
except ImportError:
    JELLYFISH_AVAILABLE = False
    logger.debug("jellyfish not available")

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False
    logger.debug("dateparser not available")

try:
    import usaddress
    USADDRESS_AVAILABLE = True
except ImportError:
    USADDRESS_AVAILABLE = False
    logger.debug("usaddress not available")


class LLMMatchResult(BaseModel):
    """Structured result from LLM evaluation."""

    is_same_person: bool = Field(description="Whether the record is about the same person")
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    reasoning: str = Field(description="Brief explanation of the decision")
    matching_facts: list[str] = Field(default_factory=list, description="Facts that match")
    conflicting_facts: list[str] = Field(default_factory=list, description="Facts that conflict")


@dataclass
class EnhancedMatchScore(MatchScore):
    """Extended match score with LLM reasoning."""

    llm_reasoning: str = ""
    llm_used: bool = False
    cache_hit: bool = False
    extracted_entities: dict[str, list[str]] | None = None


class LLMRelevanceEvaluator:
    """LLM-enhanced relevance evaluator with caching and NLP.

    This evaluator combines:
    1. Rule-based scoring (fast, cheap)
    2. NLP-based entity extraction (spaCy)
    3. Fuzzy string matching (rapidfuzz, jellyfish)
    4. LLM evaluation for ambiguous cases (LangChain + GPTCache)

    The LLM is only called when rule-based scoring is uncertain (0.4-0.6).
    GPTCache reduces costs by caching similar queries.
    """

    # LLM evaluation prompt
    EVALUATION_PROMPT = """You are a genealogy expert determining if a historical record is about a specific person.

TARGET PERSON PROFILE:
- Name: {name}
- Birth: {birth_info}
- Death: {death_info}
- Locations: {locations}
- Family: {family_info}

RECORD TO EVALUATE:
{record_text}

Determine if this record is about the same person as the target profile.
Consider:
- Name matches (including nicknames, initials, spelling variations)
- Date alignment (birth/death years within reasonable range)
- Location consistency
- Family member matches

Respond with JSON:
{{
    "is_same_person": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "matching_facts": ["list of matching details"],
    "conflicting_facts": ["list of conflicts"]
}}"""

    def __init__(
        self,
        profile: PersonProfile,
        use_llm: bool = True,
        use_cache: bool = True,
        cache_dir: str | Path | None = None,
        model: str = "claude-3-haiku-20240307",
        llm_threshold_low: float = 0.4,
        llm_threshold_high: float = 0.6,
    ) -> None:
        """Initialize the LLM-enhanced evaluator.

        Args:
            profile: Person profile to match against
            use_llm: Whether to use LLM for ambiguous cases
            use_cache: Whether to cache LLM responses
            cache_dir: Directory for GPTCache storage
            model: Anthropic model to use
            llm_threshold_low: Below this, don't bother with LLM (clearly not a match)
            llm_threshold_high: Above this, don't need LLM (clearly a match)
        """
        self.profile = profile
        self.use_llm = use_llm and LANGCHAIN_AVAILABLE
        self.use_cache = use_cache and GPTCACHE_AVAILABLE
        self.model = model
        self.llm_threshold_low = llm_threshold_low
        self.llm_threshold_high = llm_threshold_high

        # Initialize components
        self._llm = None
        self._cache = None
        self._nlp = None
        self._name_variants = self._build_name_variants()

        # Setup cache directory
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = Path.home() / ".cache" / "gps-genealogy" / "llm-cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize LLM if available
        if self.use_llm:
            self._setup_llm()

        # Initialize spaCy if available
        if SPACY_AVAILABLE:
            try:
                self._nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.warning("spaCy model not found, NER disabled")

    def _setup_llm(self) -> None:
        """Setup LangChain LLM with optional GPTCache."""
        if not LANGCHAIN_AVAILABLE:
            return

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, LLM evaluation disabled")
            self.use_llm = False
            return

        self._llm = ChatAnthropic(
            model=self.model,
            temperature=0,
            max_tokens=500,
        )

        # Setup GPTCache if available
        if self.use_cache and GPTCACHE_AVAILABLE:
            try:
                self._cache = Cache()

                # Simple string-based caching
                def get_hashed_name(data: str, **kwargs) -> str:
                    return hashlib.md5(data.encode()).hexdigest()

                self._cache.init(
                    pre_embedding_func=get_hashed_name,
                    data_manager=get_data_manager(
                        CacheBase("sqlite", sql_url=f"sqlite:///{self._cache_dir}/cache.db"),
                    ),
                )
                logger.info("GPTCache initialized at %s", self._cache_dir)
            except Exception as e:
                logger.warning("Failed to initialize GPTCache: %s", e)
                self._cache = None

    def _build_name_variants(self) -> set[str]:
        """Build set of acceptable name variants using nameparser."""
        variants = {self.profile.surname.lower()}
        variants.update(v.lower() for v in self.profile.surname_variants)

        # Add phonetic variants if jellyfish available
        if JELLYFISH_AVAILABLE:
            soundex = jellyfish.soundex(self.profile.surname)
            metaphone = jellyfish.metaphone(self.profile.surname)
            # Store for comparison, not as variants
            self._soundex = soundex
            self._metaphone = metaphone

        return variants

    def evaluate(self, record: RawRecord) -> EnhancedMatchScore:
        """Evaluate if a record matches the target person.

        Args:
            record: The record to evaluate

        Returns:
            EnhancedMatchScore with detailed scoring
        """
        # 1. Extract entities from record
        entities = self._extract_entities(record)

        # 2. Rule-based scoring (fast)
        rule_score = self._rule_based_score(record, entities)

        # 3. If uncertain, use LLM
        llm_used = False
        cache_hit = False
        llm_reasoning = ""

        if (self.use_llm and
            self.llm_threshold_low <= rule_score.overall_score <= self.llm_threshold_high):

            llm_result, cache_hit = self._llm_evaluate(record, entities)
            if llm_result:
                llm_used = True
                llm_reasoning = llm_result.reasoning

                # Blend rule-based and LLM scores
                blended_score = (rule_score.overall_score * 0.4) + (llm_result.confidence * 0.6)

                rule_score = EnhancedMatchScore(
                    overall_score=blended_score,
                    confidence=self._score_to_confidence(blended_score),
                    name_score=rule_score.name_score,
                    date_score=rule_score.date_score,
                    location_score=rule_score.location_score,
                    relationship_score=rule_score.relationship_score,
                    match_reasons=rule_score.match_reasons + llm_result.matching_facts,
                    conflict_reasons=rule_score.conflict_reasons + llm_result.conflicting_facts,
                    llm_reasoning=llm_reasoning,
                    llm_used=llm_used,
                    cache_hit=cache_hit,
                    extracted_entities=entities,
                )
                return rule_score

        # Return rule-based score with entity info
        return EnhancedMatchScore(
            overall_score=rule_score.overall_score,
            confidence=rule_score.confidence,
            name_score=rule_score.name_score,
            date_score=rule_score.date_score,
            location_score=rule_score.location_score,
            relationship_score=rule_score.relationship_score,
            match_reasons=rule_score.match_reasons,
            conflict_reasons=rule_score.conflict_reasons,
            llm_reasoning=llm_reasoning,
            llm_used=llm_used,
            cache_hit=cache_hit,
            extracted_entities=entities,
        )

    def _extract_entities(self, record: RawRecord) -> dict[str, list[str]]:
        """Extract named entities from record using spaCy and other tools."""
        entities: dict[str, list[str]] = {
            "names": [],
            "dates": [],
            "locations": [],
            "addresses": [],
        }

        # Combine all text from record
        text_parts = []
        for key in ["name", "full_name", "text", "content", "snippet"]:
            val = record.extracted_fields.get(key) or record.raw_data.get(key)
            if val:
                text_parts.append(str(val))

        text = " ".join(text_parts)
        if not text:
            return entities

        # spaCy NER
        if self._nlp:
            doc = self._nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    entities["names"].append(ent.text)
                elif ent.label_ == "DATE":
                    entities["dates"].append(ent.text)
                elif ent.label_ in ("GPE", "LOC"):
                    entities["locations"].append(ent.text)

        # nameparser for better name parsing
        if NAMEPARSER_AVAILABLE:
            for name in entities["names"]:
                try:
                    parsed = HumanName(name)
                    if parsed.last:
                        entities["names"].append(parsed.last)
                except Exception:
                    pass

        # dateparser for flexible date parsing
        if DATEPARSER_AVAILABLE:
            for field in ["birth_date", "death_date", "date"]:
                val = record.extracted_fields.get(field) or record.raw_data.get(field)
                if val:
                    try:
                        parsed = dateparser.parse(str(val))
                        if parsed:
                            entities["dates"].append(parsed.strftime("%Y-%m-%d"))
                    except Exception:
                        pass

        # usaddress for address parsing
        if USADDRESS_AVAILABLE:
            for field in ["address", "location", "residence"]:
                val = record.extracted_fields.get(field) or record.raw_data.get(field)
                if val:
                    try:
                        parsed, _ = usaddress.tag(str(val))
                        if "PlaceName" in parsed:
                            entities["locations"].append(parsed["PlaceName"])
                        if "StateName" in parsed:
                            entities["locations"].append(parsed["StateName"])
                    except Exception:
                        pass

        return entities

    def _rule_based_score(
        self, record: RawRecord, entities: dict[str, list[str]]
    ) -> MatchScore:
        """Calculate rule-based score using fuzzy matching."""
        reasons = []
        conflicts = []

        # Name scoring with fuzzy matching
        name_score = self._score_name_fuzzy(record, entities, reasons, conflicts)

        # Date scoring with dateparser
        date_score = self._score_dates(record, entities, reasons, conflicts)

        # Location scoring
        location_score = self._score_location(record, entities, reasons, conflicts)

        # Relationship scoring
        rel_score = self._score_relationships(record, reasons, conflicts)

        # Weighted score
        overall = (
            name_score * 0.40 +
            date_score * 0.30 +
            location_score * 0.20 +
            rel_score * 0.10
        )

        # Conflict penalty
        conflict_penalty = len(conflicts) * 0.15
        overall = max(0.0, overall - conflict_penalty)

        return MatchScore(
            overall_score=overall,
            confidence=self._score_to_confidence(overall),
            name_score=name_score,
            date_score=date_score,
            location_score=location_score,
            relationship_score=rel_score,
            match_reasons=reasons,
            conflict_reasons=conflicts,
        )

    def _score_name_fuzzy(
        self,
        record: RawRecord,
        entities: dict[str, list[str]],
        reasons: list[str],
        conflicts: list[str],
    ) -> float:
        """Score name match using fuzzy matching."""
        score = 0.0

        # Get names from record
        record_names = entities.get("names", [])
        record_surname = record.extracted_fields.get("surname") or ""
        record_given = record.extracted_fields.get("given_name") or ""

        if record_surname:
            record_names.append(record_surname)

        if not record_names and not record_surname:
            return 0.5  # Neutral

        # Check surname matches
        profile_surname = self.profile.surname.lower()

        for name in record_names:
            name_lower = name.lower()

            # Exact match
            if profile_surname in name_lower or name_lower in self._name_variants:
                score = max(score, 0.6)
                reasons.append(f"Surname match: {name}")
                continue

            # Fuzzy match with rapidfuzz
            if RAPIDFUZZ_AVAILABLE:
                ratio = fuzz.ratio(profile_surname, name_lower) / 100
                if ratio > 0.85:
                    score = max(score, 0.5)
                    reasons.append(f"Surname fuzzy match ({ratio:.0%}): {name}")
                    continue

            # Phonetic match with jellyfish
            if JELLYFISH_AVAILABLE and hasattr(self, '_soundex'):
                if jellyfish.soundex(name) == self._soundex:
                    score = max(score, 0.4)
                    reasons.append(f"Surname phonetic match: {name}")
                    continue

        # Check given name
        if self.profile.given_name and record_given:
            profile_given = self.profile.given_name.lower()
            record_given_lower = record_given.lower()

            if profile_given == record_given_lower:
                score += 0.4
                reasons.append(f"Given name exact: {record_given}")
            elif RAPIDFUZZ_AVAILABLE:
                ratio = fuzz.ratio(profile_given, record_given_lower) / 100
                if ratio > 0.8:
                    score += 0.3
                    reasons.append(f"Given name fuzzy ({ratio:.0%}): {record_given}")

        return min(score, 1.0)

    def _score_dates(
        self,
        record: RawRecord,
        entities: dict[str, list[str]],
        reasons: list[str],
        conflicts: list[str],
    ) -> float:
        """Score date match using flexible parsing."""
        score = 0.0
        comparisons = 0

        # Extract years from record
        record_birth = self._extract_year(
            record.extracted_fields.get("birth_year") or
            record.extracted_fields.get("birth_date")
        )
        record_death = self._extract_year(
            record.extracted_fields.get("death_year") or
            record.extracted_fields.get("death_date")
        )

        # Also check dateparser-extracted dates
        for date_str in entities.get("dates", []):
            if DATEPARSER_AVAILABLE:
                try:
                    parsed = dateparser.parse(date_str)
                    if parsed and not record_birth:
                        record_birth = parsed.year
                except Exception:
                    pass

        # Compare birth year
        if self.profile.birth_year and record_birth:
            comparisons += 1
            diff = abs(self.profile.birth_year - record_birth)

            if diff == 0:
                score += 0.5
                reasons.append(f"Birth year exact: {record_birth}")
            elif diff <= 2:
                score += 0.4
                reasons.append(f"Birth year close (±{diff}): {record_birth}")
            elif diff <= 5:
                score += 0.3
                reasons.append(f"Birth year in range (±{diff}): {record_birth}")
            elif diff > 20:
                conflicts.append(
                    f"Birth year conflict: {record_birth} vs expected {self.profile.birth_year}"
                )

        # Compare death year
        if self.profile.death_year and record_death:
            comparisons += 1
            diff = abs(self.profile.death_year - record_death)

            if diff == 0:
                score += 0.5
                reasons.append(f"Death year exact: {record_death}")
            elif diff <= 5:
                score += 0.3
                reasons.append(f"Death year close (±{diff}): {record_death}")
            elif diff > 20:
                conflicts.append(
                    f"Death year conflict: {record_death} vs expected {self.profile.death_year}"
                )

        return score if comparisons > 0 else 0.5

    def _score_location(
        self,
        record: RawRecord,
        entities: dict[str, list[str]],
        reasons: list[str],
        conflicts: list[str],
    ) -> float:
        """Score location match."""
        score = 0.0

        # Get locations from record
        record_locations = entities.get("locations", [])
        for key in ["location", "residence", "birth_place", "death_place"]:
            val = record.extracted_fields.get(key)
            if val:
                record_locations.append(str(val).lower())

        if not record_locations:
            return 0.5  # Neutral

        # Build profile locations
        profile_locations = []
        if self.profile.birth_place:
            profile_locations.append(self.profile.birth_place.lower())
        if self.profile.death_place:
            profile_locations.append(self.profile.death_place.lower())
        profile_locations.extend(p.lower() for p in self.profile.residence_places)

        if not profile_locations:
            return 0.5  # Neutral

        # Check for matches
        for rec_loc in record_locations:
            rec_loc_lower = rec_loc.lower()
            for prof_loc in profile_locations:
                if prof_loc in rec_loc_lower or rec_loc_lower in prof_loc:
                    score += 0.3
                    reasons.append(f"Location match: {rec_loc}")
                    break

        return min(score, 1.0)

    def _score_relationships(
        self,
        record: RawRecord,
        reasons: list[str],
        conflicts: list[str],
    ) -> float:
        """Score relationship matches."""
        score = 0.0

        # Check spouse
        record_spouse = record.extracted_fields.get("spouse") or record.raw_data.get("spouse")
        if record_spouse and self.profile.spouse_names:
            spouse_lower = str(record_spouse).lower()
            for spouse in self.profile.spouse_names:
                if spouse.lower() in spouse_lower or spouse_lower in spouse.lower():
                    score += 0.5
                    reasons.append(f"Spouse match: {record_spouse}")
                    break

        # Check parents
        for field in ["father", "mother"]:
            val = record.extracted_fields.get(field) or record.raw_data.get(field)
            if val and self.profile.parent_names:
                val_lower = str(val).lower()
                for parent in self.profile.parent_names:
                    if parent.lower() in val_lower:
                        score += 0.3
                        reasons.append(f"Parent match: {val}")
                        break

        return min(score, 1.0) if score > 0 else 0.5

    def _llm_evaluate(
        self, record: RawRecord, entities: dict[str, list[str]]
    ) -> tuple[LLMMatchResult | None, bool]:
        """Use LLM to evaluate ambiguous record.

        Returns:
            (LLMMatchResult or None, cache_hit bool)
        """
        if not self._llm:
            return None, False

        # Build prompt
        prompt = self.EVALUATION_PROMPT.format(
            name=f"{self.profile.given_name or ''} {self.profile.surname}".strip(),
            birth_info=f"{self.profile.birth_year or 'unknown'}, {self.profile.birth_place or 'unknown'}",
            death_info=f"{self.profile.death_year or 'unknown'}, {self.profile.death_place or 'unknown'}",
            locations=", ".join(self.profile.residence_places) or "unknown",
            family_info=f"Spouse: {', '.join(self.profile.spouse_names) or 'unknown'}; Parents: {', '.join(self.profile.parent_names) or 'unknown'}",
            record_text=self._format_record_for_llm(record, entities),
        )

        cache_hit = False

        try:
            # Check cache first
            if self._cache:
                cache_key = hashlib.md5(prompt.encode()).hexdigest()
                cached = self._cache.get(cache_key)
                if cached:
                    cache_hit = True
                    return LLMMatchResult(**json.loads(cached)), cache_hit

            # Call LLM
            messages = [
                SystemMessage(content="You are a genealogy expert. Respond only with valid JSON."),
                HumanMessage(content=prompt),
            ]

            response = self._llm.invoke(messages)
            response_text = response.content

            # Parse JSON response
            # Handle markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            result_dict = json.loads(response_text.strip())
            result = LLMMatchResult(**result_dict)

            # Store in cache
            if self._cache:
                self._cache.set(cache_key, json.dumps(result_dict))

            return result, cache_hit

        except Exception as e:
            logger.warning("LLM evaluation failed: %s", e)
            return None, False

    def _format_record_for_llm(
        self, record: RawRecord, entities: dict[str, list[str]]
    ) -> str:
        """Format record for LLM prompt."""
        parts = [f"Source: {record.source}", f"Type: {record.record_type}"]

        for key, val in record.extracted_fields.items():
            if val:
                parts.append(f"{key}: {val}")

        if entities.get("names"):
            parts.append(f"Extracted names: {', '.join(entities['names'])}")
        if entities.get("dates"):
            parts.append(f"Extracted dates: {', '.join(entities['dates'])}")
        if entities.get("locations"):
            parts.append(f"Extracted locations: {', '.join(entities['locations'])}")

        return "\n".join(parts)

    def _extract_year(self, value: Any) -> int | None:
        """Extract year from various formats."""
        if value is None:
            return None
        if isinstance(value, int):
            return value if 1500 <= value <= 2100 else None

        text = str(value)

        # Try dateparser first
        if DATEPARSER_AVAILABLE:
            try:
                parsed = dateparser.parse(text)
                if parsed:
                    return parsed.year
            except Exception:
                pass

        # Fallback to regex
        import re
        match = re.search(r"\b(1[789]\d{2}|20[0-2]\d)\b", text)
        return int(match.group(1)) if match else None

    def _score_to_confidence(self, score: float) -> MatchConfidence:
        """Convert numeric score to confidence level."""
        if score >= 0.95:
            return MatchConfidence.DEFINITE
        elif score >= 0.75:
            return MatchConfidence.LIKELY
        elif score >= 0.50:
            return MatchConfidence.POSSIBLE
        elif score >= 0.25:
            return MatchConfidence.UNLIKELY
        else:
            return MatchConfidence.NOT_MATCH


def get_available_features() -> dict[str, bool]:
    """Return which features are available."""
    return {
        "langchain": LANGCHAIN_AVAILABLE,
        "gptcache": GPTCACHE_AVAILABLE,
        "spacy": SPACY_AVAILABLE,
        "nameparser": NAMEPARSER_AVAILABLE,
        "rapidfuzz": RAPIDFUZZ_AVAILABLE,
        "jellyfish": JELLYFISH_AVAILABLE,
        "dateparser": DATEPARSER_AVAILABLE,
        "usaddress": USADDRESS_AVAILABLE,
    }
