#!/usr/bin/env python3
"""Research script for Sorrell family genealogy using GPS Agents sources.

Traces Archer Durham's maternal lineage (Sorrell family) in Oklahoma
using primary sources for GPS-compliant validation.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from gps_agents.models.search import SearchQuery, RawRecord
from gps_agents.sources.familysearch import FamilySearchNoLoginSource
from gps_agents.sources.free_census import FreeCensusSource, normalize_census_race
from gps_agents.sources.nara_census import NARACensusSource
from gps_agents.sources.headless import HeadlessBrowser, HeadlessConfig, run_headless_search
from gps_agents.sources.oklahoma import (
    OklahomaGenealogySource,
    OklahomaNativeAmericanSource,
    OklahomaVitalRecordsSource,
)


async def search_familysearch_records(surname: str, given_name: str | None = None,
                                       birth_year: int | None = None,
                                       birth_place: str | None = None) -> list[RawRecord]:
    """Search FamilySearch for records without login."""
    source = FamilySearchNoLoginSource()

    query = SearchQuery(
        surname=surname,
        given_name=given_name,
        birth_year=birth_year,
        birth_year_range=5,
        birth_place=birth_place,
        state="Oklahoma" if "Oklahoma" in (birth_place or "") else None,
    )

    print(f"\n{'='*60}")
    print(f"FamilySearch Search: {given_name or ''} {surname}")
    print(f"Birth: {birth_year or 'unknown'}, {birth_place or 'unknown'}")
    print(f"{'='*60}")

    try:
        records = await source.search(query)
        print(f"Found {len(records)} record(s)")
        for i, record in enumerate(records[:10], 1):
            print(f"\n  [{i}] {record.record_type}")
            print(f"      Source: {record.source}")
            if record.url:
                print(f"      URL: {record.url}")
            for key, val in record.extracted_fields.items():
                if val:
                    print(f"      {key}: {val}")
        return records
    except Exception as e:
        print(f"Error: {e}")
        return []


async def search_census_records(surname: str, given_name: str | None = None,
                                birth_year: int | None = None,
                                state: str = "Oklahoma") -> list[RawRecord]:
    """Search free census sources."""
    source = FreeCensusSource()

    query = SearchQuery(
        surname=surname,
        given_name=given_name,
        birth_year=birth_year,
        birth_year_range=10,
        state=state,
    )

    print(f"\n{'='*60}")
    print(f"Census Search: {given_name or ''} {surname}")
    print(f"State: {state}, Birth Year: {birth_year or 'unknown'}")
    print(f"{'='*60}")

    try:
        records = await source.search(query)
        print(f"Found {len(records)} record(s)")
        for i, record in enumerate(records[:10], 1):
            print(f"\n  [{i}] {record.record_type}")
            print(f"      Source: {record.source}")
            if record.url:
                print(f"      URL: {record.url}")
            for key, val in record.extracted_fields.items():
                if val:
                    print(f"      {key}: {val}")
        return records
    except Exception as e:
        print(f"Error: {e}")
        return []


async def search_oklahoma_native_american(surname: str) -> list[RawRecord]:
    """Search Oklahoma Native American records including Dawes Rolls."""
    source = OklahomaNativeAmericanSource()

    query = SearchQuery(surname=surname)

    print(f"\n{'='*60}")
    print(f"Oklahoma Native American Records: {surname}")
    print(f"(Dawes Rolls, Indian Census Rolls, Land Allotments)")
    print(f"{'='*60}")

    try:
        records = await source.search(query)
        print(f"Found {len(records)} resource(s)")
        for i, record in enumerate(records[:10], 1):
            print(f"\n  [{i}] {record.record_type}")
            print(f"      Source: {record.source}")
            if record.url:
                print(f"      URL: {record.url}")
            for key, val in record.extracted_fields.items():
                if val:
                    print(f"      {key}: {val}")
        return records
    except Exception as e:
        print(f"Error: {e}")
        return []


async def search_oklahoma_vital_records(surname: str, given_name: str | None = None) -> list[RawRecord]:
    """Search Oklahoma vital records (death index, marriages)."""
    source = OklahomaVitalRecordsSource()

    query = SearchQuery(surname=surname, given_name=given_name)

    print(f"\n{'='*60}")
    print(f"Oklahoma Vital Records: {given_name or ''} {surname}")
    print(f"(Death Index 1908-1969, Marriage Records)")
    print(f"{'='*60}")

    try:
        records = await source.search(query)
        print(f"Found {len(records)} resource(s)")
        for i, record in enumerate(records[:10], 1):
            print(f"\n  [{i}] {record.record_type}")
            print(f"      Source: {record.source}")
            if record.url:
                print(f"      URL: {record.url}")
            for key, val in record.extracted_fields.items():
                if val:
                    print(f"      {key}: {val}")
        return records
    except Exception as e:
        print(f"Error: {e}")
        return []


async def search_nara_census(surname: str, state: str = "Oklahoma") -> list[RawRecord]:
    """Search NARA census resources."""
    source = NARACensusSource()

    query = SearchQuery(
        surname=surname,
        state=state,
    )

    print(f"\n{'='*60}")
    print(f"NARA Census Search: {surname}")
    print(f"State: {state}")
    print(f"{'='*60}")

    try:
        records = await source.search(query)
        print(f"Found {len(records)} resource(s)")
        for i, record in enumerate(records[:10], 1):
            print(f"\n  [{i}] {record.record_type}")
            print(f"      Source: {record.source}")
            if record.url:
                print(f"      URL: {record.url}")
            for key, val in record.extracted_fields.items():
                if val:
                    print(f"      {key}: {val}")
        return records
    except Exception as e:
        print(f"Error: {e}")
        return []


async def search_headless_sources(surname: str, given_name: str | None = None,
                                   location: str | None = None) -> dict:
    """Search sources requiring headless browser."""
    results = {}

    print(f"\n{'='*60}")
    print(f"Headless Browser Searches: {given_name or ''} {surname}")
    print(f"Location: {location or 'any'}")
    print(f"{'='*60}")

    # Chronicling America (historic newspapers)
    try:
        print("\n  Searching Chronicling America...")
        ca_results = await run_headless_search(
            "chronicling_america",
            surname=surname,
            given_name=given_name,
            location=location,
            limit=10
        )
        results["chronicling_america"] = ca_results
        print(f"  Found {len(ca_results)} newspaper mention(s)")
        for r in ca_results[:3]:
            print(f"    - {r.title}: {r.snippet[:80]}...")
    except Exception as e:
        print(f"  Chronicling America error: {e}")

    # Find A Grave
    try:
        print("\n  Searching Find A Grave...")
        fag_results = await run_headless_search(
            "find_a_grave",
            surname=surname,
            given_name=given_name,
            location=location,
            limit=10
        )
        results["find_a_grave"] = fag_results
        print(f"  Found {len(fag_results)} burial record(s)")
        for r in fag_results[:3]:
            print(f"    - {r.title}: {r.snippet}")
    except Exception as e:
        print(f"  Find A Grave error: {e}")

    # FamilySearch (headless)
    try:
        print("\n  Searching FamilySearch (headless)...")
        fs_results = await run_headless_search(
            "familysearch",
            surname=surname,
            given_name=given_name,
            location=location,
            limit=10
        )
        results["familysearch_headless"] = fs_results
        print(f"  Found {len(fs_results)} record(s)")
        for r in fs_results[:3]:
            print(f"    - {r.title}: {r.snippet[:80]}...")
    except Exception as e:
        print(f"  FamilySearch headless error: {e}")

    return results


async def research_sorrell_family():
    """Main research function for Sorrell family lineage."""

    print("\n" + "="*70)
    print(" SORRELL FAMILY GENEALOGY RESEARCH")
    print(" GPS-Compliant Primary Source Validation")
    print("="*70)

    # Research subjects based on our earlier findings
    subjects = [
        {
            "name": "Ruby Zenobia Sorrell",
            "given_name": "Ruby",
            "surname": "Sorrell",
            "birth_year": 1903,
            "birth_place": "Vinita, Cherokee, Oklahoma",
            "notes": "Archer Durham's mother. Middle name: Zenobia"
        },
        {
            "name": "Maurice/Morris Sorrell",
            "given_name": "Morris",
            "surname": "Sorrell",
            "birth_year": 1874,
            "birth_place": "Oklahoma",
            "notes": "Ruby's father. Name variants: Maurice, Morris A."
        },
        {
            "name": "Ida Madden",
            "given_name": "Ida",
            "surname": "Madden",
            "birth_year": None,
            "birth_place": "Oklahoma",
            "notes": "Ruby's mother. Possible variants: Manley"
        },
        {
            "name": "Dicey Tinnon",
            "given_name": "Dicey",
            "surname": "Tinnon",
            "birth_year": 1854,
            "birth_place": "Oklahoma",
            "notes": "Morris Sorrell Sr.'s wife, Ruby's grandmother"
        },
    ]

    all_results = {}

    for subject in subjects:
        print(f"\n\n{'#'*70}")
        print(f" RESEARCHING: {subject['name']}")
        print(f" Notes: {subject['notes']}")
        print(f"{'#'*70}")

        subject_results = {
            "subject": subject,
            "familysearch": [],
            "census": [],
            "nara": [],
            "oklahoma_native": [],
            "oklahoma_vital": [],
            "headless": {},
        }

        # FamilySearch records
        fs_records = await search_familysearch_records(
            surname=subject["surname"],
            given_name=subject["given_name"],
            birth_year=subject["birth_year"],
            birth_place=subject["birth_place"]
        )
        subject_results["familysearch"] = [r.model_dump() for r in fs_records]

        # Census records
        census_records = await search_census_records(
            surname=subject["surname"],
            given_name=subject["given_name"],
            birth_year=subject["birth_year"],
            state="Oklahoma"
        )
        subject_results["census"] = [r.model_dump() for r in census_records]

        # NARA Census
        nara_records = await search_nara_census(
            surname=subject["surname"],
            state="Oklahoma"
        )
        subject_results["nara"] = [r.model_dump() for r in nara_records]

        # Oklahoma Native American Records (Dawes Rolls - critical for GPS validation)
        ok_native_records = await search_oklahoma_native_american(
            surname=subject["surname"]
        )
        subject_results["oklahoma_native"] = [r.model_dump() for r in ok_native_records]

        # Oklahoma Vital Records (Death Index, Marriages)
        ok_vital_records = await search_oklahoma_vital_records(
            surname=subject["surname"],
            given_name=subject["given_name"]
        )
        subject_results["oklahoma_vital"] = [r.model_dump() for r in ok_vital_records]

        all_results[subject["name"]] = subject_results

        # Brief pause between subjects
        await asyncio.sleep(1)

    # Try headless browser for key subjects (Ruby and Morris)
    print("\n\n" + "#"*70)
    print(" HEADLESS BROWSER SEARCHES")
    print("#"*70)

    try:
        headless_ruby = await search_headless_sources(
            surname="Sorrell",
            given_name="Ruby",
            location="Oklahoma"
        )
        all_results["Ruby Zenobia Sorrell"]["headless"] = {
            k: [r.__dict__ for r in v] for k, v in headless_ruby.items()
        }
    except Exception as e:
        print(f"Headless search error: {e}")

    # Save results
    output_dir = Path("data/research")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"sorrell_family_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # Convert datetime objects for JSON serialization
    def serialize(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=serialize)

    print(f"\n\nResults saved to: {output_file}")

    # Summary
    print("\n\n" + "="*70)
    print(" RESEARCH SUMMARY")
    print("="*70)

    for name, results in all_results.items():
        fs_count = len(results.get("familysearch", []))
        census_count = len(results.get("census", []))
        nara_count = len(results.get("nara", []))
        ok_native_count = len(results.get("oklahoma_native", []))
        ok_vital_count = len(results.get("oklahoma_vital", []))
        print(f"\n{name}:")
        print(f"  FamilySearch records: {fs_count}")
        print(f"  Census resources: {census_count}")
        print(f"  NARA resources: {nara_count}")
        print(f"  Oklahoma Native American (Dawes Rolls): {ok_native_count}")
        print(f"  Oklahoma Vital Records: {ok_vital_count}")


if __name__ == "__main__":
    asyncio.run(research_sorrell_family())
