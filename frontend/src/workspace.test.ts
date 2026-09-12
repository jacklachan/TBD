import { describe, expect, it } from "vitest";
import {
  nearestSample,
  minimum,
  clockText,
  currentVariant,
  comparisonIds,
} from "./workspace";
import { guard, StaleResponse } from "./api";
import { isApprovable } from "./contracts";
import type { Analysis, CaseSnapshot, VisualizationBundle } from "./contracts";

describe("one authoritative clock", () => {
  it("selects the inserted exact event instead of interpolating around it", () => {
    expect(nearestSample([0, 10, 13.712345, 20], 13.712345)).toBe(2);
    expect(nearestSample([0, 10, 13.712345, 20], 14)).toBe(2);
    expect(nearestSample([0, 10], -3)).toBe(0);
    expect(nearestSample([0, 10], 100)).toBe(1);
  });
  it("keeps narrow minima, including a dip between regular samples", () => {
    expect(minimum([5400, 5100, 133.7, 5000])).toEqual({
      value: 133.7,
      index: 2,
    });
  });
  it("does not fall back to another trajectory when selection is absent", () => {
    expect(
      currentVariant(
        { variants: [{ candidate_id: "baseline" }] } as VisualizationBundle,
        "rescue",
      ),
    ).toBeUndefined();
  });
  it("uses elapsed hours, not local timezone", () =>
    expect(clockText(16234.332)).toBe("04:30:34"));
});

describe("version and authorization boundaries", () => {
  it("drops a result computed under an earlier policy", () => {
    expect(() =>
      guard(
        { scenario_version: 1, policy_version: 1 },
        { expected_scenario_version: 1, expected_policy_version: 2 },
      ),
    ).toThrow(StaleResponse);
  });
  it("requires a real allowing reviewer and candidate/version matched evidence", () => {
    const snapshot = {
      case_id: "c",
      scenario_version: 1,
      policy_version: 2,
      execution: null,
      proposal: {
        status: "READY",
        case_id: "c",
        scenario_version: 1,
        policy_version: 2,
        candidate_id: "r",
        validation_id: "v",
        reviewer_verdict: null,
      },
      validations: [
        {
          validation_id: "v",
          status: "PASS",
          candidate_id: "r",
          scenario_version: 1,
          policy_version: 2,
        },
      ],
    } as CaseSnapshot;
    expect(isApprovable(snapshot)).toBe(false);
    snapshot.proposal!.reviewer_verdict = { decision: "ALLOW" } as never;
    expect(isApprovable(snapshot)).toBe(true);
    snapshot.validations[0].candidate_id = "trap";
    expect(isApprovable(snapshot)).toBe(false);
  });
  it("keeps the baseline, vetoed option and computed recommendation without hardcoding IDs", () => {
    const analysis = {
      recommended_id: "r",
      options: [
        { candidate_id: "b", kind: "NO_BURN", rank: null },
        {
          candidate_id: "v",
          rank: 1,
          primary_qualified: true,
          validation: { status: "BLOCK" },
        },
      ],
    } as unknown as Analysis;
    expect(comparisonIds(analysis)).toEqual(["b", "v", "r"]);
  });
});
