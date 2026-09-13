"""Manual, once-only acquisition of the two external snapshots.

Run by hand, commit the output, never call from the application. CelesTrak
refreshes roughly every two hours and returns HTTP 403 for a repeat download
before the next update; accumulated HTTP errors trigger a firewall block. An
existing snapshot is therefore never silently overwritten -- pass --force only
when you have a reason.

    python scripts/fetch_snapshots.py --tle --catnr 43013
    python scripts/fetch_snapshots.py --socrates

Ownership per Handoff/DATA.md: A fetches the TLE, C fetches SOCRATES.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]

TLE_PATH = REPO_ROOT / "scenarios" / "seed_tle.txt"
TLE_PROVENANCE_PATH = REPO_ROOT / "scenarios" / "seed_provenance.json"
SOCRATES_RAW_PATH = REPO_ROOT / "data" / "context" / "socrates_raw.html"
SOCRATES_PATH = REPO_ROOT / "data" / "context" / "socrates_snapshot.csv"
SOCRATES_PROVENANCE_PATH = REPO_ROOT / "data" / "context" / "socrates_provenance.json"

# Column names follow CelesTrak's documented SOCRATES CSV field names so the
# normalized file stays recognisable against their format documentation.
SOCRATES_COLUMNS = [
    "NORAD_CAT_ID_1",
    "OBJECT_NAME_1",
    "DSE_1",
    "NORAD_CAT_ID_2",
    "OBJECT_NAME_2",
    "DSE_2",
    "TCA",
    "TCA_RANGE_KM",
    "TCA_RELATIVE_SPEED_KMS",
    "MAX_PROB",
    "DILUTION_KM",
]

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php"
SOCRATES_URL = "https://celestrak.org/socrates/table-socrates.php"

TIMEOUT_S = 30


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _guard_existing(path: Path, force: bool) -> bool:
    if path.exists() and not force:
        print(f"  SKIP {path.relative_to(REPO_ROOT)} already exists (use --force to replace)")
        return False
    return True


def _get(url: str, params: dict[str, str]) -> str:
    response = requests.get(url, params=params, timeout=TIMEOUT_S)
    print(f"  GET {response.url} -> {response.status_code}")
    response.raise_for_status()
    body = response.text.strip()
    if not body:
        raise RuntimeError("empty response body")
    return body


def fetch_tle(catnr: int, force: bool) -> int:
    """Fetch one object's TLE and record where it came from.

    The catalogue number is an argument, not a constant. Identity and epoch are
    read back out of the saved file by the scenario generator; nothing
    downstream may hardcode them.
    """
    if not _guard_existing(TLE_PATH, force):
        return 0

    try:
        body = _get(TLE_URL, {"CATNR": str(catnr), "FORMAT": "TLE"})
    except Exception as exc:  # noqa: BLE001 - recorded, not retried
        print(f"  FAIL TLE: {exc}")
        return 1

    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    if len(lines) != 3 or not lines[1].startswith("1 ") or not lines[2].startswith("2 "):
        print(f"  FAIL TLE: unexpected payload shape ({len(lines)} lines)")
        print("\n".join(lines[:5]))
        return 1

    TLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TLE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    provenance = {
        "source_kind": "CELESTRAK_GP_TLE",
        "source_url": f"{TLE_URL}?CATNR={catnr}&FORMAT=TLE",
        "retrieved_at_utc": _now_utc(),
        "source_sha256": _sha256("\n".join(lines) + "\n"),
        "object_name": lines[0].strip(),
        "norad_id": int(lines[1][2:7]),
        "note": (
            "Seed for the satellite initial state only. Conjunction geometry in "
            "every scenario is synthetic. TLE accuracy is of order a kilometre "
            "at epoch, so the defensible claim is that the orbit is realistic, "
            "not that any conjunction is real."
        ),
    }
    TLE_PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"  OK  {lines[0].strip()} (NORAD {provenance['norad_id']})")
    print(f"      {TLE_PATH.relative_to(REPO_ROOT)}")
    return 0


_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<td\b([^>]*)>(.*?)</td>", re.IGNORECASE | re.DOTALL)


def _cell_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return " ".join(text.replace("&nbsp;", " ").split())


def parse_socrates(raw_html: str) -> list[list[str]]:
    """Extract conjunction rows from the SOCRATES Plus HTML table.

    CelesTrak serves this report as HTML; the endpoint ignores a FORMAT
    parameter. Each conjunction occupies two table rows -- the primary object
    carries a rowspan=2 TCA cell plus min range and relative speed, and the
    secondary object carries max probability and the dilution threshold.
    """
    rows = _ROW_RE.findall(raw_html)
    records: list[list[str]] = []

    index = 0
    while index < len(rows) - 1:
        primary_cells = _CELL_RE.findall(rows[index])
        # The primary row of a conjunction is the one holding the merged TCA cell.
        if not any("rowspan" in attrs.lower() for attrs, _ in primary_cells):
            index += 1
            continue

        secondary_cells = _CELL_RE.findall(rows[index + 1])
        primary = [_cell_text(body) for _, body in primary_cells]
        secondary = [_cell_text(body) for _, body in secondary_cells]

        # primary:   [buttons, norad, name, dse, tca, min_range, rel_speed]
        # secondary: [buttons, norad, name, dse, max_prob, dilution]
        if len(primary) < 7 or len(secondary) < 6:
            index += 2
            continue

        records.append(
            [
                primary[1], primary[2], primary[3],
                secondary[1], secondary[2], secondary[3],
                primary[4], primary[5], primary[6],
                secondary[4], secondary[5],
            ]
        )
        index += 2

    return records


def _write_socrates_csv(records: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(SOCRATES_COLUMNS)
    writer.writerows(records)
    return buffer.getvalue()


def fetch_socrates(max_rows: int, force: bool, parse_only: bool = False) -> int:
    """Fetch and normalize the public close-approach report.

    The raw HTML is kept as the committed source of truth and the CSV is derived
    from it, so the parser can be corrected later without another request.
    Display only -- nothing here is an input to any computation.
    """
    source_url = f"{SOCRATES_URL}?NAME=,&ORDER=MINRANGE&MAX={max_rows}"

    if parse_only:
        if not SOCRATES_RAW_PATH.exists():
            print(f"  FAIL SOCRATES: {SOCRATES_RAW_PATH.relative_to(REPO_ROOT)} not present")
            return 1
        raw = SOCRATES_RAW_PATH.read_text(encoding="utf-8")
        print(f"  parsing existing {SOCRATES_RAW_PATH.relative_to(REPO_ROOT)}")
    else:
        if not _guard_existing(SOCRATES_RAW_PATH, force):
            return 0
        try:
            raw = _get(SOCRATES_URL, {"NAME": ",", "ORDER": "MINRANGE", "MAX": str(max_rows)})
        except Exception as exc:  # noqa: BLE001 - recorded, not retried
            print(f"  FAIL SOCRATES: {exc}")
            return 1
        SOCRATES_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        SOCRATES_RAW_PATH.write_text(raw, encoding="utf-8")

    records = parse_socrates(raw)
    if not records:
        print("  FAIL SOCRATES: no conjunction rows parsed; raw HTML kept for inspection")
        return 1

    csv_text = _write_socrates_csv(records)
    SOCRATES_PATH.write_text(csv_text, encoding="utf-8")

    provenance = {
        "source_kind": "CELESTRAK_SOCRATES_PLUS",
        "source_url": source_url,
        "retrieved_at_utc": _now_utc(),
        "raw_file": SOCRATES_RAW_PATH.name,
        "raw_sha256": _sha256(raw),
        "normalized_file": SOCRATES_PATH.name,
        "normalized_sha256": _sha256(csv_text),
        "row_count": len(records),
        "columns": SOCRATES_COLUMNS,
        "note": (
            "Real published close approaches, shown as context beside the "
            "simulation. Not an input to any computation and unrelated to the "
            "scenario objects. Served as HTML by CelesTrak and parsed here; the "
            "raw response is retained so the parser can be corrected without "
            "another request."
        ),
    }
    SOCRATES_PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"  OK  {len(records)} conjunctions -> {SOCRATES_PATH.relative_to(REPO_ROOT)}")
    return 0


CATALOG_DIR = REPO_ROOT / "data" / "catalog"
CATALOG_PROVENANCE_PATH = CATALOG_DIR / "catalog_provenance.json"

# The protected constellation, and the debris of the two events that put the
# most fragments into its shell: the 2009 Iridium 33 / Cosmos 2251 collision at
# about 790 km, and the 2007 Fengyun-1C test at about 850 km.
CATALOG_GROUPS = {
    "iridium-NEXT": "PROTECTED",
    "iridium-33-debris": "DEBRIS",
    "cosmos-2251-debris": "DEBRIS",
    "fengyun-1c-debris": "DEBRIS",
}


def fetch_catalog(force: bool) -> int:
    """Fetch the constellation and debris element sets, once each.

    One request per group, no retries, and the first failure stops the rest --
    see the CelesTrak limits in Handoff/DATA.md.
    """
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    if CATALOG_PROVENANCE_PATH.exists() and not force:
        print(f"  SKIP {CATALOG_PROVENANCE_PATH.relative_to(REPO_ROOT)} already exists (use --force to replace)")
        return 0

    files = []
    for group, role in CATALOG_GROUPS.items():
        path = CATALOG_DIR / f"{group}.tle"
        try:
            body = _get(TLE_URL, {"GROUP": group, "FORMAT": "TLE"})
        except Exception as exc:  # noqa: BLE001 - recorded, not retried
            print(f"  FAIL {group}: {exc}")
            return 1
        lines = [line.rstrip() for line in body.splitlines() if line.strip()]
        if len(lines) < 3 or len(lines) % 3 != 0 or not lines[1].startswith("1 "):
            print(f"  FAIL {group}: unexpected payload shape ({len(lines)} lines)")
            return 1
        text = "\n".join(lines) + "\n"
        path.write_text(text, encoding="utf-8")
        files.append({
            "group": group,
            "role": role,
            "file": path.name,
            "source_url": f"{TLE_URL}?GROUP={group}&FORMAT=TLE",
            "object_count": len(lines) // 3,
            "sha256": _sha256(text),
        })
        print(f"  OK  {group}: {len(lines) // 3} objects")

    provenance = {
        "source_kind": "CELESTRAK_GP_TLE_GROUPS",
        "retrieved_at_utc": _now_utc(),
        "files": files,
        "note": (
            "Real public element sets, fetched once and committed. Screened with "
            "SGP4 as published; no covariance is available, so no probability is "
            "computed. Element sets are roughly kilometre-accurate at epoch and "
            "degrade over days: a close approach found here is a reason to look, "
            "not a prediction."
        ),
    }
    CATALOG_PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", action="store_true", help="fetch the constellation and debris groups")
    parser.add_argument("--tle", action="store_true", help="fetch the seed TLE")
    parser.add_argument("--socrates", action="store_true", help="fetch the context snapshot")
    parser.add_argument("--catnr", type=int, default=43013, help="catalogue number for --tle")
    parser.add_argument("--max-rows", type=int, default=25, help="rows for --socrates")
    parser.add_argument("--force", action="store_true", help="replace an existing snapshot")
    parser.add_argument("--parse-only", action="store_true", help="re-parse the saved SOCRATES HTML without fetching")
    args = parser.parse_args()

    if not (args.tle or args.socrates or args.catalog):
        parser.error("pass --tle, --socrates, --catalog, or a combination")

    failures = 0
    if args.catalog:
        print("tracking catalogue:")
        failures += fetch_catalog(args.force)
    if args.tle:
        print("seed TLE:")
        failures += fetch_tle(args.catnr, args.force)
    if args.socrates:
        print("SOCRATES context:")
        failures += fetch_socrates(args.max_rows, args.force, parse_only=args.parse_only)

    if failures:
        print(
            f"\n{failures} source(s) failed. Recorded, not retried. "
            "Do not loop on this -- see Handoff/DATA.md."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
