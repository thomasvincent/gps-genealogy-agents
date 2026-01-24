"""Base interface for genealogy data sources."""
from __future__ import annotations

import asyncio
import logging
import os
import random
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..models.search import RawRecord, SearchQuery


@runtime_checkable
class GenealogySource(Protocol):
    """Protocol defining the interface all data sources must implement."""

    name: str

    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search for records matching the query.

        Args:
            query: Search parameters

        Returns:
            List of raw records found
        """
        ...

    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific record by ID.

        Args:
            record_id: The record's unique identifier

        Returns:
            The record or None if not found
        """
        ...

    def requires_auth(self) -> bool:
        """Check if this source requires authentication.

        Returns:
            True if authentication is needed
        """
        ...


class BaseSource(ABC):
    """Abstract base class for genealogy data sources."""

    name: str = "base"
    base_url: str = ""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the source.

        Args:
            api_key: Optional API key for authenticated sources
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[RawRecord]:
        """Search for records matching the query."""

    @abstractmethod
    async def get_record(self, record_id: str) -> RawRecord | None:
        """Retrieve a specific record by ID."""

    @abstractmethod
    def requires_auth(self) -> bool:
        """Check if this source requires authentication."""

    def is_configured(self) -> bool:
        """Check if this source is properly configured."""
        if self.requires_auth():
            return self.api_key is not None
        return True

    def _build_name_variants(self, surname: str) -> list[str]:
        """Build common surname variants for searching.

        Args:
            surname: The base surname

        Returns:
            List of variant spellings
        """
        variants = [surname]
        surname_lower = surname.lower()

        # Common letter substitutions
        substitutions = [
            # Patronymic endings
            ("son", "sen"),  # Johnson/Johnsen (Scandinavian)
            ("sen", "son"),
            ("sson", "son"),  # Swedish Andersson/Anderson
            ("son", "sson"),
            # Irish/Scottish prefixes
            ("Mac", "Mc"),  # MacDonald/McDonald
            ("Mc", "Mac"),
            ("O'", "O"),  # O'Brien/OBrien
            ("O", "O'"),
            # German prefixes
            ("Von ", "von "),
            ("von ", "Von "),
            ("Van ", "van "),
            ("van ", "Van "),
            ("De ", "de "),
            ("de ", "De "),
            # Letter substitutions
            ("ck", "k"),  # Black/Blak
            ("k", "ck"),
            ("c", "k"),  # Clark/Klark
            ("k", "c"),
            ("ph", "f"),  # Stephen/Steven
            ("f", "ph"),
            ("y", "i"),  # Smyth/Smith
            ("i", "y"),
            ("ie", "y"),  # Davies/Davys
            ("y", "ie"),
            ("ae", "e"),  # Michaels/Michels
            ("e", "ae"),
            ("oe", "e"),  # Schroeder/Schreder
            ("e", "oe"),
            ("ue", "u"),  # Mueller/Muller
            ("u", "ue"),
            # Double letters
            ("ll", "l"),  # Miller/Miler
            ("l", "ll"),
            ("tt", "t"),  # Wyatt/Wyat
            ("t", "tt"),
            ("ss", "s"),  # Ross/Ros
            ("s", "ss"),
            ("nn", "n"),  # Mann/Man
            ("n", "nn"),
            ("rr", "r"),  # Farr/Far
            ("r", "rr"),
            ("ff", "f"),  # Griffith/Grifith
            ("f", "ff"),
            # Silent letters
            ("ght", "t"),  # Wright/Write
            ("gh", "g"),  # Vaughn/Vaun
            ("kn", "n"),  # Knight/Night
            ("wr", "r"),  # Wright/Right
            # Endings
            ("er", "or"),  # Schneider/Schneidur
            ("or", "er"),
            ("man", "mann"),  # Hoffman/Hoffmann
            ("mann", "man"),
            ("itz", "icz"),  # Horowitz/Horowicz (Slavic)
            ("icz", "itz"),
            ("ski", "sky"),  # Kowalski/Kowalsky
            ("sky", "ski"),
            ("wicz", "vich"),  # Slavic
            ("vich", "wicz"),
            ("off", "ov"),  # Russian
            ("ov", "off"),
            # German special characters
            ("ß", "ss"),  # Strauß/Strauss
            ("ss", "ß"),
            ("ä", "ae"),  # Bräuer/Braeuer
            ("ae", "a"),
            ("ö", "oe"),  # Schröder/Schroeder
            ("oe", "o"),
            ("ü", "ue"),  # Müller/Mueller
            ("ue", "u"),
        ]

        for old, new in substitutions:
            if old.lower() in surname_lower:
                # Preserve original case where possible
                variant = surname.replace(old, new)
                if variant not in variants:
                    variants.append(variant)
                # Also try lowercase match
                variant_lower = surname_lower.replace(old.lower(), new.lower())
                if variant_lower.title() not in variants:
                    variants.append(variant_lower.title())

        # Add common Anglicizations
        anglicizations = {
            # German
            "schmidt": ["smith"],
            "schneider": ["taylor", "snyder"],
            "mueller": ["miller", "muller"],
            "schwartz": ["black", "swartz"],
            "weiss": ["white", "wise"],
            "klein": ["small"],
            "gross": ["large", "big"],
            "braun": ["brown"],
            "jung": ["young"],
            # Jewish
            "cohen": ["cowen", "cohn", "kahn", "kohn"],
            "levy": ["levi", "levine", "levin"],
            "goldberg": ["goldenberg"],
            "rosenberg": ["rosenbaum"],
            # Italian
            "rossi": ["ross"],
            "bianchi": ["white"],
            "ferrari": ["smith"],
            # Polish
            "kowalski": ["smith"],
            "nowak": ["newman"],
            # Scandinavian
            "eriksson": ["erickson", "ericson"],
            "johansson": ["johnson", "johanson"],
            "larsson": ["larson", "larsen"],
            "andersson": ["anderson", "andersen"],
            "olsson": ["olson", "olsen"],
            "nilsson": ["nilson", "nielsen"],
            "petersson": ["peterson", "petersen"],
        }

        for foreign, english_list in anglicizations.items():
            if foreign == surname_lower:
                variants.extend(e.title() for e in english_list)
            for english in english_list:
                if english == surname_lower:
                    variants.append(foreign.title())

        return list(set(variants))

    def _build_given_name_variants(self, given_name: str) -> list[str]:
        """Build common given name variants (nicknames, diminutives).

        Args:
            given_name: The base given name

        Returns:
            List of variant names
        """
        variants = [given_name]
        name_lower = given_name.lower()

        # Common nickname mappings
        nicknames = {
            # Male names
            "william": ["will", "bill", "billy", "willy", "liam"],
            "robert": ["rob", "bob", "bobby", "robbie", "bert"],
            "richard": ["rick", "dick", "richie", "rich"],
            "james": ["jim", "jimmy", "jamie", "jem"],
            "john": ["jack", "johnny", "jon"],
            "michael": ["mike", "mickey", "mick"],
            "thomas": ["tom", "tommy", "thom"],
            "charles": ["charlie", "chuck", "chas"],
            "edward": ["ed", "eddie", "ned", "ted", "teddy"],
            "henry": ["harry", "hank", "hal"],
            "george": ["georgie"],
            "joseph": ["joe", "joey", "jos"],
            "samuel": ["sam", "sammy"],
            "benjamin": ["ben", "benny", "benji"],
            "nathaniel": ["nate", "nathan", "nat"],
            "nicholas": ["nick", "nicky"],
            "alexander": ["alex", "alec", "sandy", "xander"],
            "anthony": ["tony", "ant"],
            "andrew": ["andy", "drew"],
            "matthew": ["matt", "matty"],
            "daniel": ["dan", "danny"],
            "patrick": ["pat", "paddy"],
            "francis": ["frank", "fran"],
            "frederick": ["fred", "freddy", "fritz"],
            "lawrence": ["larry", "laurie"],
            "leonard": ["leo", "len", "lenny"],
            "theodore": ["theo", "ted", "teddy"],
            "walter": ["walt", "wally"],
            "albert": ["al", "bert", "bertie"],
            "alfred": ["alf", "alfie", "fred"],
            "arthur": ["art", "artie"],
            "clarence": ["clare"],
            "clifford": ["cliff"],
            "donald": ["don", "donny"],
            "douglas": ["doug", "dougie"],
            "eugene": ["gene"],
            "gerald": ["gerry", "jerry"],
            "harold": ["harry", "hal"],
            "jacob": ["jake", "jack"],
            "raymond": ["ray"],
            "ronald": ["ron", "ronny"],
            "stephen": ["steve", "stevie"],
            "vincent": ["vince", "vinny"],
            "zachary": ["zach", "zack"],
            # Female names
            "elizabeth": ["liz", "lizzy", "beth", "betty", "betsy", "eliza", "libby", "ellie"],
            "margaret": ["maggie", "peggy", "meg", "marge", "margie", "rita", "greta"],
            "catherine": ["cathy", "kate", "katie", "kitty", "cat"],
            "katherine": ["kathy", "kate", "katie", "kitty"],
            "mary": ["molly", "polly", "mae", "mamie", "maria"],
            "ann": ["annie", "anna", "nancy", "nan"],
            "anne": ["annie", "anna", "nancy"],
            "sarah": ["sally", "sadie"],
            "susan": ["sue", "suzy", "susie"],
            "patricia": ["pat", "patty", "tricia", "trish"],
            "jennifer": ["jenny", "jen"],
            "jessica": ["jess", "jessie"],
            "rebecca": ["becky", "becca"],
            "dorothy": ["dot", "dotty", "dottie"],
            "frances": ["fran", "frannie"],
            "virginia": ["ginny", "ginger"],
            "eleanor": ["ellie", "nell", "nelly", "nora"],
            "helen": ["nell", "nelly", "ellen"],
            "harriet": ["hattie", "hatty"],
            "henrietta": ["hettie", "etta", "hetty"],
            "josephine": ["jo", "josie"],
            "martha": ["marty", "mattie", "patty"],
            "abigail": ["abby", "gail"],
            "deborah": ["debbie", "deb"],
            "christina": ["chris", "tina", "christy"],
            "alexandra": ["alex", "sandy", "lexi"],
            "caroline": ["carrie", "carol"],
            "charlotte": ["charlie", "lottie"],
            "penelope": ["penny"],
            "priscilla": ["prissy", "cilla"],
            "theresa": ["terry", "tess", "tessie"],
            "victoria": ["vicky", "tori"],
            # German names
            "wilhelm": ["will", "willi", "william"],
            "friedrich": ["fritz", "fred", "frederick"],
            "heinrich": ["heinz", "henry"],
            "johann": ["john", "hans", "jan"],
            "johannes": ["john", "hans"],
            "karl": ["charles", "carl"],
            "maria": ["mary", "marie"],
            "elisabeth": ["elizabeth", "elise", "lisa"],
            "katharina": ["catherine", "kate"],
            "margarethe": ["margaret", "grete"],
            # Scandinavian names
            "erik": ["eric"],
            "olaf": ["olav"],
            "lars": ["laurence", "lawrence"],
            "anders": ["andrew"],
            "per": ["peter"],
            "nils": ["nicholas"],
        }

        # Check if name matches any known nickname
        for full_name, nicks in nicknames.items():
            if name_lower == full_name:
                variants.extend(n.title() for n in nicks)
            elif name_lower in nicks:
                variants.append(full_name.title())
                # Also add other nicknames
                for other_nick in nicks:
                    if other_nick != name_lower:
                        variants.append(other_nick.title())

        return list(set(variants))

    async def _make_request(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a polite HTTP request to the source API with rate limiting and circuit breaking."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)

        # Resolve per-source guard configs (env overrides or safe defaults)
        from gps_agents.net import GUARDS, RateLimitConfig

        key = getattr(self, "name", "source").lower()
        # Defaults: 1 req / 1.5s; window 5s
        rl_default = RateLimitConfig(
            max_calls=int(os.getenv(f"RATE_{key.upper()}_MAX", os.getenv("RATE_DEFAULT_MAX", "1"))),
            window_seconds=float(os.getenv(f"RATE_{key.upper()}_WINDOW", os.getenv("RATE_DEFAULT_WINDOW", "5"))),
            min_interval=float(os.getenv(f"RATE_{key.upper()}_MIN_INTERVAL", os.getenv("RATE_DEFAULT_MIN_INTERVAL", "1.5"))),
        )
        limiter = GUARDS.get_limiter(key, rl_default)
        breaker = GUARDS.get_breaker(
            key,
            max_failures=int(os.getenv(f"CB_{key.upper()}_THRESHOLD", os.getenv("CB_DEFAULT_THRESHOLD", "5"))),
            window_seconds=float(os.getenv(f"CB_{key.upper()}_WINDOW", os.getenv("CB_DEFAULT_WINDOW", "60"))),
            cooldown_seconds=float(os.getenv(f"CB_{key.upper()}_COOLDOWN", os.getenv("CB_DEFAULT_COOLDOWN", "300"))),
        )

        if not breaker.allow_call():
            raise httpx.HTTPError(f"circuit_open:{key}")

        await limiter.acquire()

        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=0.5, max=4.0),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError)),
        )
        async def _do() -> dict[str, Any]:
            # Small jitter to avoid herding
            await asyncio.sleep(random.uniform(0.05, 0.2))
            resp = await self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

        try:
            result = await _do()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise

    async def close(self) -> None:
        """Close HTTP client connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> BaseSource:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        """Async context manager exit - ensures connection cleanup."""
        await self.close()
        return False
