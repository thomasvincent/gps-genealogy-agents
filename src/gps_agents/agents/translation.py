"""Translation Agent - translates foreign-language records."""

import json
from typing import Any

from .base import BaseAgent


class TranslationAgent(BaseAgent):
    """Translation Agent for foreign-language genealogical records.

    Preserves ambiguity and notes archaic terms.

    Does NOT:
    - Infer relationships
    - Create Facts
    - Resolve discrepancies
    """

    name = "translation"
    prompt_file = "translation_agent.txt"
    default_provider = "openai"  # GPT-4 for translation tasks

    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Process records needing translation.

        Args:
            state: Current workflow state

        Returns:
            Updated state with translations
        """
        raw_records = state.get("raw_records", [])
        translations = []

        for record in raw_records:
            if record.get("needs_translation", False):
                translation = await self._translate_record(record)
                translations.append(translation)

        state["translations"] = translations
        return state

    async def _translate_record(self, record: dict) -> dict:
        """Translate a single record.

        Args:
            record: Record data with text to translate

        Returns:
            Translation result
        """
        language = record.get("language", "unknown")
        text = record.get("extracted_fields", {})

        prompt = f"""
        Translate this genealogical record from {language} to English.

        Record Fields:
        {json.dumps(text, indent=2, ensure_ascii=False)}

        Rules:
        1. Preserve ambiguity - don't resolve unclear text
        2. Mark archaic or unclear terms with [?]
        3. Keep original terms in parentheses for important words
        4. Do NOT interpret relationships or make inferences
        5. Translate literally, then note if meaning is uncertain

        Return JSON:
        {{
            "translated_fields": {{
                "field_name": "translated value",
                ...
            }},
            "uncertain_terms": [
                {{"original": "term", "translation": "best guess", "note": "why uncertain"}}
            ],
            "archaic_terms": [
                {{"term": "original", "meaning": "explanation"}}
            ],
            "translation_notes": "any important context"
        }}
        """

        response = await self.invoke(prompt)

        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return {
                    "record_id": record.get("record_id"),
                    "source": record.get("source"),
                    "original_language": language,
                    **result,
                }
        except json.JSONDecodeError:
            pass

        return {
            "record_id": record.get("record_id"),
            "source": record.get("source"),
            "error": "Translation failed",
        }
