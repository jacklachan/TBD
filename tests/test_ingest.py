"""Pasted catalogue elements, turned into something the same two paths screen.

The tests that matter here are the refusals. Anything that parses becomes a
scenario an operator is shown, so element sets this code cannot honestly screen
have to be rejected with a reason rather than quietly produce a plausible
screening.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.ingest import (
    IngestError,
    epoch_spread_s,
    evaluate_tles,
    scenario_from_tles,
    split_tle_text,
)
from backend.planning.candidates import baseline_candidate
from backend.planning.policy import policy_from_document
from backend.planning.verifier import STATUS_PASS, validate_candidate
from backend.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_TLE = REPO_ROOT / "scenarios" / "seed_tle.txt"

pytestmark = pytest.mark.skipif(
    not SEED_TLE.exists(), reason="seed TLE snapshot not committed"
)

# A second element set alongside the committed one. The values are contrived so
# the test does not depend on a second live catalogue fetch; the point being
# exercised is the parsing, the shared epoch and the screening, none of which
# care whether this object is real.
SECOND = """OTHER OBJECT
1 54234U 22150A   26254.88000000  .00000021  00000+0  32000-4 0  9995
2 54234  98.7400 193.2000 0001200  60.0000 300.0000 14.19540000200000
"""


def seed_text() -> str:
    return SEED_TLE.read_text(encoding="utf-8")


def pasted() -> str:
    return seed_text() + SECOND


# --------------------------------------------------------------------- parse


def test_three_line_sets_are_split_by_line_number_not_by_counting():
    sets = split_tle_text(pasted())
    assert [name for name, _, _ in sets] == ["NOAA 20 (JPSS-1)", "OTHER OBJECT"]


def test_bare_two_line_sets_parse_without_names():
    bare = "\n".join(line for line in pasted().splitlines() if line[:2] in ("1 ", "2 "))
    sets = split_tle_text(bare)
    assert len(sets) == 2
    assert all(name.startswith("OBJECT") for name, _, _ in sets)


def test_a_line_one_with_no_line_two_is_refused_by_position():
    text = "\n".join(pasted().splitlines()[:2])
    with pytest.raises(IngestError, match="no line 2 follows"):
        split_tle_text(text)


def test_an_orphan_line_two_is_refused():
    with pytest.raises(IngestError, match="no line 1 before it"):
        split_tle_text(
            "2 43013  98.7810 193.6155 0001610  53.1622 306.9701 14.19525379456774"
        )


@pytest.mark.parametrize("text", ["", "   ", "\n\n"])
def test_empty_input_is_refused(text):
    with pytest.raises(IngestError, match="nothing pasted"):
        split_tle_text(text)


def test_prose_is_refused_with_an_example_of_what_was_wanted():
    with pytest.raises(IngestError, match="no element sets found"):
        split_tle_text("here are the orbits for tomorrow, thanks")


# ------------------------------------------------------------------ evaluate


def test_every_object_is_evaluated_at_one_shared_epoch():
    """State vectors at each object's own epoch describe different instants.

    Screening those against each other compares positions that never coexisted,
    which would be a wrong answer rather than an imprecise one.
    """
    objects = evaluate_tles(pasted())
    assert len({o.epoch_utc for o in objects}) == 1
    assert epoch_spread_s(pasted()) > 0, "the raw sets really are at different epochs"
    print(
        f"\n[ingest] {len(objects)} objects, element epochs "
        f"{epoch_spread_s(pasted()):,.0f} s apart, evaluated at one"
    )


def test_one_object_is_not_a_screening():
    with pytest.raises(IngestError, match="at least two objects"):
        evaluate_tles(seed_text())


def test_the_same_object_twice_is_refused():
    with pytest.raises(IngestError, match="appears twice"):
        evaluate_tles(seed_text() + seed_text())


def test_too_many_objects_are_refused():
    many = "".join(
        SECOND.replace("54234", f"5423{n}").replace("OTHER", f"OTHER {n}")
        for n in range(1, 9)
    )
    with pytest.raises(IngestError, match="at most"):
        evaluate_tles(seed_text() + many + many)


# ------------------------------------------------------------------ scenario


def test_the_scenario_screens_with_the_ordinary_verifier():
    document = scenario_from_tles(pasted())
    result = validate_candidate(
        document, policy_from_document(document), baseline_candidate()
    )
    assert result.status == STATUS_PASS
    assert result.encounters, "every screened pair reports a closest approach"


def test_the_provenance_says_what_this_is_and_is_not():
    """An overstated provenance is worse than no ingest at all."""
    provenance = scenario_from_tles(pasted())["provenance"]
    assert provenance["source_kind"] == "PASTED_TLE"
    assert provenance["synthetic_conjunction"] is False
    note = provenance["note"].lower()
    assert "two-body" in note
    assert "not an sgp4 conjunction analysis" in note
    assert "probability" in note
    # Each object keeps its own element epoch, because the spread between them
    # is the main reason a screening built this way can be wrong.
    assert all("tle_epoch_utc" in o for o in provenance["objects"])


def test_the_chosen_spacecraft_is_the_only_manoeuvrable_object():
    document = scenario_from_tles(pasted(), satellite_index=1)
    manoeuvrable = [o for o in document["objects"] if o["maneuverable"]]
    assert len(manoeuvrable) == 1
    assert document["satellite_id"] == manoeuvrable[0]["object_id"]
    assert manoeuvrable[0]["name"] == "OTHER OBJECT"


def test_an_out_of_range_satellite_index_is_refused():
    with pytest.raises(IngestError, match="outside the 2 objects"):
        scenario_from_tles(pasted(), satellite_index=5)


@pytest.mark.parametrize("horizon", [0.0, 30.0, 200_000.0])
def test_an_unusable_horizon_is_refused(horizon):
    with pytest.raises(IngestError, match="horizon must be"):
        scenario_from_tles(pasted(), horizon_s=horizon)


# ------------------------------------------------------------------ endpoint


def test_the_endpoint_creates_a_case_that_behaves_like_any_other():
    client = TestClient(create_app(store=Store(":memory:")))
    response = client.post("/ingest/tle", json={"text": pasted()})
    assert response.status_code == 201, response.text
    body = response.json()

    case_id = body["case_id"]
    assert body["scenario"]["provenance"]["source_kind"] == "PASTED_TLE"
    assert body["ingest"]["epoch_spread_s"] > 0

    # The case is a case: it screens, it exports, it is not a special mode.
    analysis = client.post(
        f"/cases/{case_id}/analysis",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["candidate_count"] >= 1

    export = client.get(f"/cases/{case_id}/export", params={"format": "cdm"})
    assert export.status_code == 200
    assert "CCSDS_CDM_VERS" in export.text


def test_the_endpoint_refuses_rubbish_with_a_typed_error():
    client = TestClient(create_app(store=Store(":memory:")))
    response = client.post("/ingest/tle", json={"text": "not elements"})
    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "TLE_UNREADABLE"


def test_the_endpoint_bounds_the_paste_size_before_parsing_it():
    """413 rather than 422: the guard drops the body before it is read.

    Parsing a 20 KB paste only to reject it would mean the size limit is
    enforced after the work it exists to prevent.
    """
    client = TestClient(create_app(store=Store(":memory:")))
    assert client.post("/ingest/tle", json={"text": "x" * 20_000}).status_code == 413


def test_the_endpoint_is_behind_the_same_guard_as_the_rest_of_the_api():
    """It creates a case and runs a screening, so it is not a free endpoint.

    An endpoint added outside the guard's prefix list is unauthenticated,
    unbounded and cross-origin by omission rather than by decision.
    """
    client = TestClient(create_app(store=Store(":memory:")))
    denied = client.post(
        "/ingest/tle",
        json={"text": pasted()},
        headers={"Origin": "https://untrusted.example"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["error"] == "ORIGIN_DENIED"


def many_objects(count: int = 12) -> str:
    """A full paste, spaced around the same shell.

    Contrived values, because the point is how the chain behaves with the
    maximum number of objects rather than whether these particular ones exist.
    """
    sets = []
    for n in range(count):
        norad = 40000 + n
        mean_anomaly = (n * 29.7) % 360.0
        sets.append(
            f"OBJ-{n}\n"
            f"1 {norad:05d}U 17073A   26254.91060846  .00000019  00000+0  "
            f"30092-4 0  999{n % 10}\n"
            f"2 {norad:05d}  98.7810 193.6155 0001610  53.1622 "
            f"{mean_anomaly:8.4f} 14.19525379456774\n"
        )
    return "".join(sets)


def test_a_full_paste_screens_and_exports_a_record_that_still_verifies():
    """Twelve objects is the limit, and every step downstream has to take it.

    The record grows with the number of screened pairs, and it has to stay
    inside the request cap or the operator cannot hand their own record back
    for checking.
    """
    from backend.security import MAX_REQUEST_BYTES

    client = TestClient(create_app(store=Store(":memory:")))
    created = client.post("/ingest/tle", json={"text": many_objects()})
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    assert len(created.json()["ingest"]["objects"]) == 12

    analysis = client.post(
        f"/cases/{case_id}/analysis",
        json={"expected_scenario_version": 1, "expected_policy_version": 1},
    ).json()
    assert analysis["candidate_count"] >= 25

    record = client.get(f"/cases/{case_id}/export", params={"format": "cdm"}).text
    size = len(record.encode())
    assert size < MAX_REQUEST_BYTES, (
        f"a full paste exports {size:,} bytes, over the {MAX_REQUEST_BYTES:,} "
        "byte request cap, so it could not be handed back for checking"
    )

    checked = client.post("/interop/verify-cdm", json={"text": record})
    assert checked.status_code == 200, checked.text
    assert checked.json()["verdict"] in ("AGREES", "NO_CLAIMS")
    print(f"\n[full paste] 12 objects, record {size:,} bytes of {MAX_REQUEST_BYTES:,}")


def test_the_primary_threat_is_the_object_that_actually_comes_closest():
    """Not whichever one was typed first.

    The search path ranks burns against the named primary threat. Naming an
    object that never comes near means the ranking is about nothing, while the
    approach that matters sits unranked. The verifier screens everything either
    way, so this is about the ranking being meaningful rather than about safety.
    """
    from backend.core.trajectory import Trajectory
    from backend.ingest import evaluate_tles

    text = many_objects()
    document = scenario_from_tles(text)
    objects = evaluate_tles(text)
    satellite = objects[0]

    grid = np.arange(0.0, document["horizon_s"], 30.0)
    own, _ = Trajectory.from_state(satellite.r_m, satellite.v_mps).states_at(grid)

    closest, best = "", float("inf")
    for other in objects[1:]:
        theirs, _ = Trajectory.from_state(other.r_m, other.v_mps).states_at(grid)
        separation = float(np.min(np.linalg.norm(theirs - own, axis=1)))
        if separation < best:
            closest, best = f"NORAD-{other.norad_id}", separation

    assert document["primary_threat_id"] == closest
    assert document["primary_threat_id"] != f"NORAD-{objects[1].norad_id}" or (
        closest == f"NORAD-{objects[1].norad_id}"
    )
    print(f"\n[primary threat] {closest} at roughly {best / 1000:,.0f} km")
