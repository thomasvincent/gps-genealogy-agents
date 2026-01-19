"""Semantic Kernel plugin for genealogy data sources."""

import json
from typing import Annotated

from semantic_kernel.functions import kernel_function

from gps_agents.models.search import SearchQuery
from gps_agents.sources.accessgenealogy import AccessGenealogySource
from gps_agents.sources.familysearch import FamilySearchSource
from gps_agents.sources.findmypast import FindMyPastSource
from gps_agents.sources.gedcom import GedcomSource
from gps_agents.sources.jerripedia import JerripediaSource
from gps_agents.sources.myheritage import MyHeritageSource
from gps_agents.sources.wikitree import WikiTreeSource


class SourcesPlugin:
    """Plugin for searching genealogical data sources.

    Provides access to multiple genealogy databases and record repositories
    to support reasonably exhaustive research (GPS Pillar 1).
    """

    def __init__(self):
        self._sources = {
            "familysearch": FamilySearchSource(),
            "wikitree": WikiTreeSource(),
            "findmypast": FindMyPastSource(),
            "myheritage": MyHeritageSource(),
            "accessgenealogy": AccessGenealogySource(),
            "jerripedia": JerripediaSource(),
        }
        self._gedcom_source = GedcomSource()

    @kernel_function(
        name="search_all_sources",
        description="Search all available genealogy sources for records matching the query.",
    )
    async def search_all_sources(
        self,
        query_json: Annotated[str, "JSON SearchQuery with name, dates, places"],
    ) -> Annotated[str, "JSON array of records from all sources"]:
        """Search all sources and aggregate results."""
        query = SearchQuery.model_validate_json(query_json)
        all_records = []

        for source_name, source in self._sources.items():
            try:
                records = await source.search(query)
                for record in records:
                    record_dict = record.model_dump(mode="json")
                    record_dict["_source"] = source_name
                    all_records.append(record_dict)
            except Exception as e:
                all_records.append({
                    "_source": source_name,
                    "_error": str(e),
                })

        return json.dumps(all_records)

    @kernel_function(
        name="search_familysearch",
        description="Search FamilySearch for historical records.",
    )
    async def search_familysearch(
        self,
        query_json: Annotated[str, "JSON SearchQuery"],
    ) -> Annotated[str, "JSON array of FamilySearch records"]:
        """Search FamilySearch specifically."""
        query = SearchQuery.model_validate_json(query_json)
        records = await self._sources["familysearch"].search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])

    @kernel_function(
        name="search_wikitree",
        description="Search WikiTree collaborative family tree.",
    )
    async def search_wikitree(
        self,
        query_json: Annotated[str, "JSON SearchQuery"],
    ) -> Annotated[str, "JSON array of WikiTree profiles"]:
        """Search WikiTree."""
        query = SearchQuery.model_validate_json(query_json)
        records = await self._sources["wikitree"].search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])

    @kernel_function(
        name="search_findmypast",
        description="Search FindMyPast UK/Ireland records (subscription required).",
    )
    async def search_findmypast(
        self,
        query_json: Annotated[str, "JSON SearchQuery"],
    ) -> Annotated[str, "JSON array of FindMyPast records"]:
        """Search FindMyPast."""
        query = SearchQuery.model_validate_json(query_json)
        records = await self._sources["findmypast"].search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])

    @kernel_function(
        name="search_myheritage",
        description="Search MyHeritage global records (subscription required).",
    )
    async def search_myheritage(
        self,
        query_json: Annotated[str, "JSON SearchQuery"],
    ) -> Annotated[str, "JSON array of MyHeritage records"]:
        """Search MyHeritage."""
        query = SearchQuery.model_validate_json(query_json)
        records = await self._sources["myheritage"].search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])

    @kernel_function(
        name="search_accessgenealogy",
        description="Search AccessGenealogy for Native American and early American records.",
    )
    async def search_accessgenealogy(
        self,
        query_json: Annotated[str, "JSON SearchQuery"],
    ) -> Annotated[str, "JSON array of AccessGenealogy records"]:
        """Search AccessGenealogy."""
        query = SearchQuery.model_validate_json(query_json)
        records = await self._sources["accessgenealogy"].search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])

    @kernel_function(
        name="search_jerripedia",
        description="Search Jerripedia for Channel Islands (Jersey, Guernsey) records.",
    )
    async def search_jerripedia(
        self,
        query_json: Annotated[str, "JSON SearchQuery"],
    ) -> Annotated[str, "JSON array of Jerripedia records"]:
        """Search Jerripedia."""
        query = SearchQuery.model_validate_json(query_json)
        records = await self._sources["jerripedia"].search(query)
        return json.dumps([r.model_dump(mode="json") for r in records])

    @kernel_function(
        name="load_gedcom",
        description="Load and parse a local GEDCOM file.",
    )
    async def load_gedcom(
        self,
        file_path: Annotated[str, "Path to the GEDCOM file"],
    ) -> Annotated[str, "JSON with load results"]:
        """Load a GEDCOM file."""
        count = self._gedcom_source.load_file(file_path)
        # Search with empty query to get all records
        records = await self._gedcom_source.search(SearchQuery())
        return json.dumps({
            "count": count,
            "records": [r.model_dump(mode="json") for r in records[:100]],  # Limit to 100
        })

    @kernel_function(
        name="get_record_details",
        description="Fetch full details for a specific record by ID.",
    )
    async def get_record_details(
        self,
        source_name: Annotated[str, "Name of the source (familysearch, wikitree, etc.)"],
        record_id: Annotated[str, "ID of the record to fetch"],
    ) -> Annotated[str, "JSON with full record details"]:
        """Get detailed record information."""
        source = self._sources.get(source_name.lower())
        if source is None:
            return json.dumps({"error": f"Unknown source: {source_name}"})

        try:
            record = await source.get_record(record_id)
            if record is None:
                return json.dumps({"error": "Record not found"})
            return record.model_dump_json()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @kernel_function(
        name="list_available_sources",
        description="List all available genealogy sources and their status.",
    )
    def list_available_sources(self) -> Annotated[str, "JSON object of sources and availability"]:
        """List available sources."""
        sources = {}
        for name, source in self._sources.items():
            sources[name] = {
                "available": source.is_available(),
                "requires_auth": source.requires_auth,
                "description": source.description,
            }
        return json.dumps(sources)

    @kernel_function(
        name="create_search_query",
        description="Helper to create a properly formatted SearchQuery JSON.",
    )
    def create_search_query(
        self,
        given_name: Annotated[str | None, "First/given name"] = None,
        surname: Annotated[str | None, "Family/surname"] = None,
        birth_year: Annotated[int | None, "Approximate birth year"] = None,
        birth_place: Annotated[str | None, "Birth location"] = None,
        death_year: Annotated[int | None, "Approximate death year"] = None,
        death_place: Annotated[str | None, "Death location"] = None,
        year_range: Annotated[int, "Years +/- to search around dates"] = 5,
    ) -> Annotated[str, "JSON SearchQuery ready for use"]:
        """Create a search query JSON."""
        query = SearchQuery(
            given_name=given_name,
            surname=surname,
            birth_year=birth_year,
            birth_place=birth_place,
            death_year=death_year,
            death_place=death_place,
            birth_year_range=year_range,
            death_year_range=year_range,
        )
        return query.model_dump_json()
