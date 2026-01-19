from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from gps_agents.gramps.client import GrampsClient
from gps_agents.gramps.models import Event, EventType, GrampsDate, Name, Person, Source
from gps_agents.gramps.upsert import upsert_event, upsert_person, upsert_source, upsert_citation
from gps_agents.idempotency.exceptions import IdempotencyBlock
from gps_agents.media.store import save_media_bytes
from gps_agents.projections.sqlite_projection import SQLiteProjection
from gps_agents.wikidata.idempotency import ensure_statement
from gps_agents.git_utils import safe_commit


# ---------------------- Test helpers ----------------------

def make_gramps_db(tmp: Path) -> Path:
    db = tmp / "gramps.db"
    conn = sqlite3.connect(db)
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE person (handle TEXT PRIMARY KEY, gramps_id TEXT, blob_data BLOB)")
        c.execute("CREATE TABLE event (handle TEXT PRIMARY KEY, gramps_id TEXT, blob_data BLOB)")
        c.execute("CREATE TABLE source (handle TEXT PRIMARY KEY, gramps_id TEXT, blob_data BLOB)")
        c.execute("CREATE TABLE citation (handle TEXT PRIMARY KEY, gramps_id TEXT, blob_data BLOB)")
        c.execute("CREATE TABLE family (handle TEXT PRIMARY KEY, gramps_id TEXT, blob_data BLOB)")
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture()
def env_tmp():
    d = Path(tempfile.mkdtemp(prefix="gps-idem-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------- Upsert tests ----------------------

def test_upsert_person_twice_produces_one_person(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    p = Person(names=[Name(given="John", surname="Doe")])

    r1 = upsert_person(gc, proj, p)
    r2 = upsert_person(gc, proj, p)

    assert r1.handle == r2.handle
    # Verify only one row in person
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
        assert n == 1


def test_upsert_event_twice_produces_one_event(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    e = Event(event_type=EventType.BIRTH, date=GrampsDate(year=1850))

    r1 = upsert_event(gc, proj, e)
    r2 = upsert_event(gc, proj, e)

    assert r1.handle == r2.handle
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        assert n == 1


def test_upsert_person_probable_match_blocks(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    p = Person(names=[Name(given="Jane", surname="Doe")])

    class FakeMatcher:
        def __init__(self, *_args, **_kwargs):
            pass
        def find_matches(self, person, threshold=50.0, limit=1):
            class M:
                match_score = 85.0
                matched_person = Person(names=[Name(given="Jane", surname="Doe")])
                matched_handle = "I0001"
            return [M()]

    with pytest.raises(IdempotencyBlock) as ei:
        upsert_person(gc, proj, p, matcher_factory=lambda c: FakeMatcher())
    assert "Probable" in str(ei.value)


def test_upsert_person_impossible_timeline_blocks(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    from gps_agents.gramps.models import GrampsDate, Event as GEvent, EventType as GEventType

    p = Person(
        names=[Name(given="Alex", surname="Smith")],
        birth=GEvent(event_type=GEventType.BIRTH, date=GrampsDate(year=1900)),
        death=GEvent(event_type=GEventType.DEATH, date=GrampsDate(year=1890)),
    )

    with pytest.raises(IdempotencyBlock) as ei:
        upsert_person(gc, proj, p)
    assert "Timeline impossible" in str(ei.value)


def test_parent_age_block(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    # Insert father (born 1900), child (born 1909) -> parent age 9 (block)
    father_handle = "FATH1"
    child_handle = "CHLD1"
    fam_handle = "FAM1"

    # Build blobs via client serializer
    father_blob = gc._serialize_blob({"handle": father_handle, "gramps_id": "I100", "primary_name": {}, "gender": 1, "parent_family_list": [], "family_list": [], "private": False, "event_ref_list": [], "alternate_names": [], "citation_list": [], "note_list": [], "media_list": [], "tag_list": [], "birth": None})
    # Embed birth year in blob_data JSON-like structure understood by _person_from_gramps
    father_blob = gc._serialize_blob({"gramps_id": "I100", "primary_name": {}, "gender": 1, "parent_family_list": [], "family_list": [], "private": False, "event_ref_list": [], "alternate_names": [], "citation_list": [], "note_list": [], "media_list": [], "tag_list": [], "birth": {"date": {"year": 1900}}})
    child_blob = gc._serialize_blob({"gramps_id": "I200", "primary_name": {}, "gender": 1, "parent_family_list": [fam_handle], "family_list": [], "private": False, "event_ref_list": [], "alternate_names": [], "citation_list": [], "note_list": [], "media_list": [], "tag_list": [], "birth": {"date": {"year": 1909}}})
    fam_blob = gc._serialize_blob({"gramps_id": "F1", "father_handle": father_handle, "mother_handle": None, "child_ref_list": [child_handle]})

    with gc.session():
        gc._conn.execute("INSERT INTO person (handle, gramps_id, blob_data) VALUES (?, ?, ?)", (father_handle, "I100", father_blob))
        gc._conn.execute("INSERT INTO person (handle, gramps_id, blob_data) VALUES (?, ?, ?)", (child_handle, "I200", child_blob))
        gc._conn.execute("INSERT INTO family (handle, gramps_id, blob_data) VALUES (?, ?, ?)", (fam_handle, "F1", fam_blob))

    from gps_agents.gramps.models import Name, Person as GPerson, Event as GEvent, EventType as GEventType, GrampsDate

    child_person = GPerson(names=[Name(given="Kid", surname="Test")], parent_family_ids=[fam_handle], birth=GEvent(event_type=GEventType.BIRTH, date=GrampsDate(year=1909)))

    with pytest.raises(IdempotencyBlock) as ei:
        upsert_person(gc, proj, child_person)
    assert "parent age" in str(ei.value)


def test_weak_evidence_downgrade_blocks_auto_merge(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    from gps_agents.gramps.models import Name, Person as GPerson, Event as GEvent, EventType as GEventType, GrampsDate

    p = GPerson(names=[Name(given="YOnly", surname="Merge")], birth=GEvent(event_type=GEventType.BIRTH, date=GrampsDate(year=1850)))

    class FakeMatcher:
        def __init__(self, *_args, **_kwargs):
            pass
        def find_matches(self, person, threshold=50.0, limit=1):
            class M:
                match_score = 96.0  # 0.96
                matched_person = None
                matched_handle = None
            return [M()]

    with pytest.raises(IdempotencyBlock):
        upsert_person(gc, proj, p, matcher_factory=lambda c: FakeMatcher())


def test_citation_dedup_by_fingerprint(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    # First, ensure the source exists to reference in citation
    s = Source(title="1850 US Census", author="US Gov", publisher="NARA")
    upsert_source(gc, proj, s)

    from gps_agents.gramps.models import Citation as GCitation, GrampsDate

    c1 = GCitation(source_id="S1", page="12", date=GrampsDate(year=1850))
    c2 = GCitation(source_id="S1", page=" 12 ", date=GrampsDate(year=1850, approximate=True))  # approx reduces to year

    r1 = upsert_citation(gc, proj, c1)
    r2 = upsert_citation(gc, proj, c2)

    assert r1.handle == r2.handle


# ---------------------- Media tests ----------------------

def test_media_dedup_same_hash_one_file(env_tmp: Path):
    content = b"hello world"
    p1 = save_media_bytes(content, env_tmp / "media")
    p2 = save_media_bytes(content, env_tmp / "media")
    assert p1 == p2
    assert p1.exists()


# ---------------------- Wikidata tests ----------------------

def test_wikidata_ensure_statement_prevents_duplicates():
    class MockWD:
        def __init__(self):
            self.claims = []
        def get_claims(self, entity_id: str, property_id: str) -> list[dict[str, Any]]:
            return list(self.claims)
        def add_claim(self, entity_id: str, property_id: str, value, qualifiers, references) -> str:
            guid = f"{entity_id}$1"
            self.claims.append({
                "id": guid,
                "property": property_id,
                "value": value,
                "qualifiers": qualifiers,
                "references": references,
            })
            return guid

    wd = MockWD()
    cache: dict[str, str] = {}

    guid1 = ensure_statement(wd, "Q123", "P569", {"time": "+1850-00-00T00:00:00Z", "precision": 9}, references=[{"P248": "Q999"}], cache=cache)
    guid2 = ensure_statement(wd, "Q123", "P569", {"time": "+1850-00-00T00:00:00Z", "precision": 9}, references=[{"P248": "Q999"}], cache=cache)

    assert guid1 == guid2
    assert len(wd.claims) == 1


def test_wikidata_equivalence_order_independent():
    class MockWD2:
        def __init__(self):
            self.claims = [{
                "id": "Q1$1",
                "property": "p569",
                "value": {"time": "+1850-03-00T00:00:00Z", "precision": 10},
                "qualifiers": {"P580": {"time": "+1850-00-00T00:00:00Z", "precision": 9}},
                "references": [{"P248": "Q999"}, {"P854": "https://example.org"}],
            }]
        def get_claims(self, entity_id: str, property_id: str):
            return list(self.claims)
        def add_claim(self, entity_id: str, property_id: str, value, qualifiers, references):
            self.claims.append({
                "id": "Q1$2",
                "property": property_id,
                "value": value,
                "qualifiers": qualifiers,
                "references": references,
            })
            return "Q1$2"

    wd = MockWD2()
    # Same semantics but different order and precision forms
    ensure_statement(wd, "Q1", "P569", {"time": "+1850-03-15T00:00:00Z", "precision": 10}, qualifiers={"P580": {"time": "+1850-00-00T00:00:00Z", "precision": 9}}, references=[{"P854": "https://example.org"}, {"P248": "Q999"}])
    assert len(wd.claims) == 1


# ---------------------- Property tests ------------------------

def test_person_fingerprint_stable_under_whitespace_and_case():
    from gps_agents.idempotency.fingerprint import fingerprint_person
    p1 = Person(names=[Name(given="JOHN ", surname="  DOE")])
    p2 = Person(names=[Name(given="john", surname="doe")])
    assert fingerprint_person(p1).value == fingerprint_person(p2).value


def test_upsert_person_dry_run_no_writes(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    from gps_agents.gramps.models import Name, Person as GPerson

    p = GPerson(names=[Name(given="Dry", surname="Run")])
    r = upsert_person(gc, proj, p, dry_run=True)
    assert r.action in {"create", "merge"}
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
assert n == 0


def test_decide_upsert_person(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    from gps_agents.idempotency.decision import decide_upsert_person
    from gps_agents.gramps.models import Name, Person as GPerson

    p = GPerson(names=[Name(given="Decide", surname="Only")])
    d = decide_upsert_person(gc, proj, p)
assert d.action in {"create", "merge", "reuse", "review"}


def test_decide_upsert_event_source_place(env_tmp: Path):
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    from gps_agents.idempotency.decision import decide_upsert_event, decide_upsert_source, decide_upsert_place
    from gps_agents.gramps.models import Event as GEvent, EventType as GEventType, GrampsDate, Source as GSource, Place as GPlace

    ev = GEvent(event_type=GEventType.BIRTH, date=GrampsDate(year=1800))
    so = GSource(title="Foo")
    pl = GPlace(name="Somewhere")

    de = decide_upsert_event(gc, proj, ev)
    ds = decide_upsert_source(gc, proj, so)
    dp = decide_upsert_place(gc, proj, pl)
    assert de.action == "create"
    assert ds.action == "create"
    assert dp.action == "create"

# ---------------------- Concurrency tests ----------------------

def test_upsert_person_parallel_no_duplicates(env_tmp: Path):
    import threading
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    p = Person(names=[Name(given="Concurrent", surname="Case")])
    handles: list[str] = []

    def worker():
        r = upsert_person(gc, proj, p)
        handles.append(r.handle)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(handles)) == 1
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
        assert n == 1


def test_upsert_person_multiprocess_no_duplicates(env_tmp: Path):
    from multiprocessing import Process, Manager
    db = make_gramps_db(env_tmp)
    gc = GrampsClient(db)
    gc.connect(db)
    proj = SQLiteProjection(env_tmp / "proj.sqlite")

    p = Person(names=[Name(given="Multi", surname="Proc")])

    def worker(shared):
        local_gc = GrampsClient(db)
        local_gc.connect(db)
        local_proj = SQLiteProjection(env_tmp / "proj.sqlite")
        r = upsert_person(local_gc, local_proj, p)
        shared.append(r.handle)

    with Manager() as m:
        shared = m.list()
        procs = [Process(target=worker, args=(shared,)) for _ in range(6)]
        for pr in procs:
            pr.start()
        for pr in procs:
            pr.join()
        assert len(set(list(shared))) == 1
    with sqlite3.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM person").fetchone()[0]
        assert n == 1


# ---------------------- Git guard tests ----------------------

def test_git_commit_guard_skips_when_no_change(env_tmp: Path, monkeypatch):
    repo = env_tmp / "repo"
    repo.mkdir()
    os.chdir(repo)
    os.system("git init -q")
    f = repo / "a.txt"
    f.write_text("one")
    os.system("git add a.txt && git commit -m initial -q")

    # second attempt without change
    created = safe_commit(repo, [f], "msg")
    assert created is False

    # change content
    f.write_text("two")
    created2 = safe_commit(repo, [f], "msg2")
    assert created2 is True
