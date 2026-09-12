# Orbital project precedents — GitHub and hackathon evidence

**Checked:** 12 September 2026. **Team constraint:** three builders, twenty hours.

**Scope:** Research only. No repositories were installed, built, or executed. No application code was copied into this workspace.

## 1. What the evidence changes

The orbital planning idea is plausible and has relevant competition precedents. The strongest match is SpaceGuardian, first place at the 8th CASSINI Hackathon: the organizer describes automated collision prevention and maneuver optimization. Its event had 110 submitted projects across three challenges. That supports this problem's competitive potential; it does not establish that our team can build its equivalent in twenty hours. [EUSPA results](https://www.euspa.europa.eu/newsroom-events/news/8-cassini-hackathon-winners)

The research also weakens a novelty claim based on “satellite tracker + maneuver suggestions + AI.” Several public repositories already combine those features. One is even named OrbitGuard. Retire our previous working name and describe our concept as the **Conjunction Decision Desk** until a separate name search is done.

The useful distinction for our demo is a small, inspectable workflow that **recomputes maneuver consequences, catches a secondary encounter, and responds to a changed mission constraint**. This is a proposed execution focus, not a claim of worldwide originality.

The previous thirty-six-hour scope is not a sound twenty-hour commitment. The revised plan cuts live catalog ingestion, broad orbit support, machine-learning training, elaborate 3D, and multi-operator negotiation from the required build.

## 2. Research method and limits

- Searched public GitHub/project pages, maneuver-planning and conjunction-assessment terms, NASA Space Apps archives, Devpost, CASSINI/EUSPA records, and organizer/institutional announcements.
- Checked metadata for fourteen selected repositories, including default branch, last push date, archive status, and GitHub's detected license.
- Inspected selected implementation/model files in seven of those repositories. Captured commit-specific links below so observations remain reviewable if the default branch changes.
- Cross-referenced award claims against organizer records where available. Distinguished overall rank, national/local recognition, nomination, and participation.
- Did not run test suites, verify performance numbers, audit every source file, or establish production fitness. A tests directory proves tests exist, not that they pass or test the right thing.
- This is a broad targeted survey, **not an exhaustive inventory of every GitHub repository**. Private, unindexed, renamed, and unpublished projects cannot be comprehensively covered. Repository abundance and selected winners do not provide a win probability.

The focus is orbital decision software and closely related demonstrations. This is not an equally deep new survey of all eight tracks or of privacy tools.

## 3. Fourteen-repository shortlist

Dates below are GitHub metadata's last push date at inspection, not proof of recent code quality. License entries are GitHub-detected repository licenses; individual files, dependencies, datasets, and assets still need checking before reuse. All fourteen repositories were reported as unarchived at inspection.

| Repository | Evidence level | License / last push | Useful lesson or potential reuse | Twenty-hour decision |
|---|---|---|---|---|
| [brandon-rhodes/python-sgp4](https://github.com/brandon-rhodes/python-sgp4) | Metadata and maintained package documentation | MIT / 2026-07-12 | Standard SGP4 propagation for public orbital elements | Use only if a public-catalog context view earns its time; not an arbitrary-burn simulator |
| [shashwatak/satellite-js](https://github.com/shashwatak/satellite-js) | Metadata and README/API examples | MIT / 2026-08-20 | Browser propagation, coordinate transforms, TLE/OMM support | Useful optional visualization primitive; avoid duplicating the authoritative simulation in the browser |
| [cesabici-bit/satguard](https://github.com/cesabici-bit/satguard) | Metadata, tree, planner source | MIT / 2026-03-23 | Candidate-grid organization and explicit CW applicability restrictions | Study the design; do not treat its planner as our complete verifier |
| [Nishant7p/OrbitGuard](https://github.com/Nishant7p/OrbitGuard) | Metadata, tree, generator, maneuver-model documentation | MIT / 2026-08-23 | Baseline candidate, bounded policy, evidence comparison, unsupported-case handling | Closest product overlap; rename our concept and explain our additional recomputation |
| [ncdrone/orbveil](https://github.com/ncdrone/orbveil) | Metadata, README, tree, propagation source | Apache-2.0 / 2026-02-28 | Typed states, explicit TEME frame, SGP4 error handling | Good screening reference; README explicitly excludes maneuver planning |
| [kesslerlib/kessler](https://github.com/kesslerlib/kessler) | Metadata and README | GPL-3.0 / 2026-05-15 | Research-oriented conjunction simulation and inference; developed through FDL Europe collaboration | Later research reference; avoid adding a learning stack to this event |
| [Rushorgir/RADAR](https://github.com/Rushorgir/RADAR) | Metadata, tree, maneuver source, hackathon README | No detected license / 2026-08-31 | Modular ingest/propagate/screen/UI boundaries | Concept reference; inspected maneuver output is a simplified proxy |
| [eshadesigns/Drift-Zero](https://github.com/eshadesigns/Drift-Zero) | Metadata, tree, maneuver source, hackathon README | No detected license / 2026-07-22 | Dashboard option comparisons and mission tradeoff presentation | Presentation reference; do not inherit its outcome/cost assumptions |
| [jdardash/space-collision-predictor](https://github.com/jdardash/space-collision-predictor) | Metadata, tree, maneuver source | MIT / 2026-09-02 | Cleanly exposed maneuver-option interface | Treat maneuver values as estimates pending trajectory recomputation |
| [nekhss/Viyan](https://github.com/nekhss/Viyan) | Metadata, tree, decision and negotiation source | MIT / 2026-07-18 | Visible case states, priorities, approval flow, MCP-oriented structure | Learn the flow; inspected decisions and negotiation are rules, not evidence of LLM planning |
| [MAMV3x3/space-apps-challenge-2022](https://github.com/MAMV3x3/space-apps-challenge-2022) | Metadata, README, official project linkage | MIT / 2023-12-20 | Dagon's React/Three.js/satellite.js visualization | Historical UI reference; not an independently validated risk engine |
| [ahmad-moussawi/track-space-debris](https://github.com/ahmad-moussawi/track-space-debris) | Metadata and official CEDAR X project description | No detected license / 2021-12-03 | Clear filters and small browser workflow | Visualization inspiration; project page puts conjunction assessment in future work |
| [Alexander2116/CS_hackathon](https://github.com/Alexander2116/CS_hackathon) | Metadata, README, Devpost award linkage | No detected license / 2024-04-18 | Space trash: Python simulation, GUI, animations, ML experiment | Actual prize-linked repository; use as a scoping lesson, not a ready web-app base |
| [Achraf99Jday/ACES-NASA](https://github.com/Achraf99Jday/ACES-NASA) | Metadata, README, university award corroboration | No detected license / 2021-10-03 | Eye Above: interactive debris map, categories, time navigation | Good product/story precedent; do not inherit its aging infrastructure |

The SGP4 package's documented output is in TEME; that is relevant if adding public-catalog data. Keep it separate from the proposed synthetic simulation until transformations are deliberately implemented. [Package documentation](https://pypi.org/project/sgp4/)

## 4. What source inspection actually found

These are bounded observations about the linked files, not claims that an entire repository is defective. They are particularly useful because impressive READMEs can conceal simplified planning models.

### A. SatGuard: useful grid search, limited post-maneuver model

The planner enumerates burn-time/magnitude combinations, uses Clohessy–Wiltshire displacement, and checks near-circular applicability. The inspected path recomputes a probability using default LEO covariance and modifies the encounter geometry at the original event. It does not itself propagate the changed trajectory through a full catalog over time.

**Learn:** structured candidate comparisons and applicability checks. **Add ourselves:** post-burn propagation, new encounter-time search, all-three-object validation, and honest separation metrics. [Inspected planner, commit 07a86ce](https://github.com/cesabici-bit/satguard/blob/07a86ce8c65dee49abfd540c59f049b7e4b1f874/src/satguard/maneuver/planner.py)

### B. Existing OrbitGuard: extremely close concept, explicit surrogate limits

Its generator includes no-burn plus signed candidates at fractions of a user's maneuver budget. Its model document explicitly describes a constant-velocity RIC displacement surrogate and says secondary-conjunction screening belongs in downstream validation.

**Learn:** honest model boundaries, baseline comparison, invalid-input outcomes. **Our proposed difference:** implement the small simulated downstream check, expose its evidence, and replan when policy changes. This does not establish superior overall capability. [Generator](https://github.com/Nishant7p/OrbitGuard/blob/3f0ca18fd241c0c2bbd8c0efef16e8471a3ec1b7/engine/maneuver/generator.py), [model limitations](https://github.com/Nishant7p/OrbitGuard/blob/3f0ca18fd241c0c2bbd8c0efef16e8471a3ec1b7/docs/MANEUVER_MODEL.md)

### C. RADAR: desired distance is not a measured outcome

The inspected advisory uses a simplified along-track displacement proxy and assigns the returned new miss distance to the configured target. Its risk-reduction factor is a distance-based heuristic, and the source labels the approach as simplified/qualitative.

**Learn:** an advisory can be a useful first estimate. **Do not inherit:** presenting that target as an independently simulated outcome or probability improvement. [Inspected optimizer, commit 80795a3](https://github.com/Rushorgir/RADAR/blob/80795a3c11de1d68392a763652587cad42ad3cd4/src/maneuver/optimizer.py)

### D. Drift Zero: option cards can hide assumptions

Its maneuver module starts with predefined separation-increase targets, estimates delta-v from distance divided by lead time, then computes cost/lifetime fields from assumed propulsion and station-keeping parameters. The inspected helper returns zero delta-v when lead time is nonpositive; that is unsuitable as evidence that an expired encounter can be mitigated for free.

**Learn:** make alternatives easy to compare. **Our change:** reject expired actions and compute actual simulated trajectories; show delta-v without unsupported lifetime/dollar claims. [Inspected module, commit 5c4dc96](https://github.com/eshadesigns/Drift-Zero/blob/5c4dc964c330e957db671a80ee9d887961bde0f0/backend/shield/maneuver.py)

### E. Space Collision Predictor: an estimate still needs verification

In the inspected planner, several options return the requested target separation as their estimated new miss distance. The function does not propagate both altered trajectories to demonstrate the result or screen other objects.

**Learn:** input/output organization. **Our change:** retain estimates as proposals until the deterministic simulator recomputes their consequences. [Inspected maneuver module, commit 38ed209](https://github.com/jdardash/space-collision-predictor/blob/38ed2096438dee5e64044ac7af4e4f52d7ccd8bd/src/sda/maneuver.py)

### F. Viyan: distinguish workflow rules from agent reasoning

The inspected negotiation function selects responsibility from numerical priority differences. The decision function selects fixed altitude adjustments and adds fixed offsets to expected separation according to risk category. These files implement a rule-based demonstration; they do not establish that the whole repository lacks other AI components.

**Learn:** explicit case/approval states. **Our change:** log actual model tool calls and derive maneuver outcomes from simulation. [Decision source](https://github.com/nekhss/Viyan/blob/a8199f4f9a317a802529f3862fc29014ac49f851/backend/simulation/decision.py), [negotiation source](https://github.com/nekhss/Viyan/blob/a8199f4f9a317a802529f3862fc29014ac49f851/backend/simulation/negotiation.py)

### G. OrbVeil: a useful small building-block pattern

The propagation file explicitly defines state units/frame, calls the standard SGP4 library, and surfaces propagation errors or validity masks. Its README separately states that maneuver planning is absent.

**Learn:** clear types and invalid-result handling. **Do not assume:** the presence of a screening library completes our maneuver workflow. [Inspected propagation source, commit 6fd454e](https://github.com/ncdrone/orbveil/blob/6fd454e1111d3ba82928ad837095a780a56567eb/src/orbveil/core/propagation.py)

## 5. Verified hackathon results and their relevance

| Project/team | Verified result and event date | What it demonstrated or proposed | How relevant is it? |
|---|---|---|---|
| **SpaceGuardian, Slovenia** | **First place, 8th CASSINI Hackathon**, held 22–24 November 2024; results article published March 2025 | Automated collision prevention and orbital maneuver optimization | Strongest direct precedent. Multi-day event, not evidence of a twenty-hour build. [Results](https://www.euspa.europa.eu/newsroom-events/news/8-cassini-hackathon-winners), [event dates](https://www.cassini.eu/hackathons/8th-hackathon-announcement) |
| **Ecosmic** | Dutch winner, ActInSpace 2022; a separate EBAN Space Women Entrepreneurship prize at the international final | The team describes intelligent satellites using star trackers for debris monitoring | Relevant orbital-sustainability precedent. Existing team/startup work means we cannot infer a from-scratch build duration. [Host/incubator interview](https://www.sbicnoordwijk.nl/ecosmic-enabling-safe-sustainable-space-operations-esabic/), [team's project description](https://fr.linkedin.com/posts/ecosmic_two-days-ago-the-ecosmic-team-participated-activity-7000820156444590080-NFh8) |
| **Eye Above / ACES** | French competition victory in NASA Space Apps 2021, corroborated by Sorbonne; not established as a global win | Interactive debris map with categories and time navigation | Strong evidence for a clear, focused product. University account describes a larger specialist team than ours. [University report](https://sciences.sorbonne-universite.fr/actualites/lassociation-etudiante-aces-remporte-le-championnat-de-france-au-hackathon-de-la-nasa), [code](https://github.com/Achraf99Jday/ACES-NASA) |
| **Vela / Team SpaceEx** | **Third place, BramHacks 2025**, organizer announcement 12 November 2025 | Debris monitoring using satellite data and predictive analytics | Relevant, but third place would not meet our top-two target. Do not abbreviate it to overall winner. [City's results](https://investbrampton.ca/city-of-brampton-empowers-young-innovators-to-explore-space-technology-at-bramhacks-2025/) |
| **Space trash** | **Fourth Place Overall, StudentHack 2024**, Devpost award record | Python orbital simulation and animation with a launch-time ML experiment | Closely linked public code and award evidence. Team describes itself as PhD physicists; not a directly comparable skill baseline. [Award/project](https://devpost.com/software/space-trash), [code](https://github.com/Alexander2116/CS_hackathon) |
| **SAT-E / Neviem ešte** | **Overall winner, Spaceport Hackathon 2024: Gaming Edition**, organizer announcement | Game about space debris and telecommunications | Adjacent evidence for an understandable interactive story, not validation of an orbital planner. [Organizer announcement](https://www.linkedin.com/posts/slovak-space-office_spaceporthackathon-gamingedition-spacetechnology-activity-7272194987931361280-UzL0), [event entries](https://itch.io/jam/spaceport-hackathon-2024-gaming-edition) |

The European Commission separately corroborates the CASSINI winner and describes a challenge based on conjunction data and realistic scenarios. [European Commission account](https://defence-industry-space.ec.europa.eu/8th-edition-cassini-hackathon-challenges-hackers-improve-space-collision-avoidance-2024-11-22_en)

I did not establish an authoritative public source-code repository for the specific SpaceGuardian, Ecosmic, or Vela entries. Do not attach an unrelated same-name GitHub repository to their awards.

### Similar projects that must not be counted as verified winners

- **Dagon, Space Apps 2022:** official page shows **Global Nominee**, with an explicit link to its ISS-tracker repository. [Project record](https://2022.spaceappschallenge.org/challenges/2022-challenges/track-the-iss/teams/dagon)
- **Hypercube, Space Apps 2021:** official page shows **Global Nominee**, not global winner. [Project record](https://2021.spaceappschallenge.org/challenges/statements/mapping-space-trash-in-real-time/teams/hypercube/)
- **CEDAR X, Space Apps 2021:** project/code linkage found; a winning award was not established. Its own description identifies conjunction assessment as future work. [Project record](https://2021.spaceappschallenge.org/challenges/statements/mapping-space-trash-in-real-time/teams/cedar-x/)
- **RADAR and Drift Zero:** repository descriptions associate them with hackathons; this research did not verify a prize for either.
- **Kessler:** a research-library precedent, not a verified hackathon-winner example.

There is selection bias here: finding successful examples cannot tell us the success rate of all orbital submissions. These examples also span different years, rules, team sizes, and judging priorities.

## 6. What to reuse, what to design ourselves

| Decision | Rationale |
|---|---|
| Use ordinary numerical/plotting libraries | Save time on well-understood primitives, while retaining a small inspectable simulation |
| Use Python SGP4 or satellite.js only for a separately labeled public-catalog view if needed | They do not automatically simulate an arbitrary maneuver and validate its consequences |
| Learn candidate/baseline structures from SatGuard and existing OrbitGuard | They make a useful design vocabulary; we still need our own verified small scenario and workflow |
| Build the three-object post-burn verifier and policy-change loop as the core contribution | This is the evidence that supports the planned signature demo |
| Borrow interaction ideas from prize-linked visualizations | Clear time navigation and selected-object context help judges understand a small model |
| Prefer selected licensed modules; timebox any whole-platform starter evaluation to forty-five minutes | Honor the team's reuse preference while checking whether setup and unfamiliar assumptions actually save time |
| Skip new ML/RL training, Ada/SPARK migration, and full-catalog screening | They add major uncertainty without being required for our central user action |

The concrete reuse candidates in the revised plan are the existing OrbitGuard's candidate-generation structure and SatGuard's candidate-result pattern; its small CW helper is an optional bounded estimate/reference. The final verification model remains separate. SatGuard's inspected package requires Python 3.12+, so importing the entire platform is a larger setup choice than adapting one isolated helper. No claimed time saving has been benchmarked. [Dependency declaration](https://github.com/cesabici-bit/satguard/blob/07a86ce8c65dee49abfd540c59f049b7e4b1f874/pyproject.toml), [CW helper](https://github.com/cesabici-bit/satguard/blob/07a86ce8c65dee49abfd540c59f049b7e4b1f874/src/satguard/maneuver/cw.py)

Open-source license permission and hackathon originality rules are separate questions. The organizers' approval of synthetic/online **data** does not establish permission to submit an existing **codebase**. Before implementation, confirm the event's rules on libraries, starter code, and pre-event work. Research and this plan do not rely on pre-event implementation being allowed.

For any actual reused code, record the source URL, commit/version, license, files used, and our modifications; preserve required notices. GitHub explains that a public repository without a license does not automatically grant general reuse rights. For unlicensed examples above, use them as conceptual references unless appropriate permission is established. [GitHub licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)

## 7. Revised feasibility judgment

**Plausible in twenty hours:** three synthetic objects, a validated short-horizon two-body model, a small finite maneuver set, a planner agent with real tools, one policy change, a secondary-conflict check, human approval in simulation, and an evidence export.

**Not a responsible twenty-hour promise:** an operational orbital traffic platform, trustworthy real-world probability estimates from bare public elements, a new learned trajectory optimizer, or multi-operator autonomous execution.

My recommendation remains **space as a tightly scoped, higher-risk competitive choice**, provided one teammate can own and explain the numerical core. Its plausibility is supported by code and precedents; our specific implementation is still untested. A small circularity workflow remains a safer completion choice if that numerical ownership is missing.

At hour three of the future build, require a verified no-burn trajectory, a computed encounter, and a burn that changes the outcome correctly. At hour six, require the secondary-conflict check to work through the interface. If these gates fail, reassess immediately rather than treating visual polish as progress on the core.

The updated `plan.md` turns these findings into the exact twenty-hour scope and ownership schedule.
