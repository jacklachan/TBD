# Transect — reusable spatial glass UI

Version 3 · 8 September 2026 · implemented React / Three.js reference

This is the handoff for recreating the approved visual language with a different problem statement. Read sections 1–12 before building. Appendix A contains the **complete live token file**, and Appendix B contains the **technical audit of all 49 supplied reference images**, with filenames, regions, observations, proposed rules, confidence, exceptions and supplied palettes. This document is sufficient to brief another agent about the style; exact image reuse additionally requires the listed asset files.

## 1. Instructions for the next agent

Use the new problem statement to decide the product's entities, labels, metrics, statuses, imagery and actions. Preserve the material, hierarchy and component anatomy described here. Build original content and an arrangement suited to the problem. Keep explanations about design systems, tokens, rendering techniques and implementation outside the product UI.

The intended result is a quiet spatial workspace: one detailed continuous media field, peripheral translucent panels, fine edge reflections, restrained navigation, light large numerals and small regular-weight labels. Dark mode is deeply dark with readable light foreground. Light mode is icy blue-gray with **dark charcoal/slate text**. Both modes retain the same component geometry.

Do not reinterpret this as a generic dashboard of opaque gray rectangles. Preserve the contribution of imagery and local background transmission. Do not introduce a new bright brand color based on the largest swatch in a supplied palette. Do not introduce routes, distances, elevations, world positions or other data that the problem has not supplied.

**Precedence:** latest user direction → approved v2 appearance → current implementation rules and token JSON in this document → source observations in Appendix B → historical v1 files. Appendix B records the earlier image approval stage. Its statements about an unchanged viewer or pending approval describe that stage, not the present implementation. Its proposed sizes/alphas are superseded by Appendix A where different. If later images show a real mismatch, describe the evidence and update both prose and tokens together.

## 2. The reference families and the three primary anchors

The source inventory contains 27 JPEGs in `Dark mode`, 22 images in `Light mode`, and one palette JSON per folder. Filenames intentionally retain the user's spelling. All 49 have individual records in Appendix B. Device frames, rooms, hands, people, editorial margins, brand presentations and photography are explicitly separated from application chrome.

| Source family | Files | What transfers | What stays specific to the source |
|---|---|---|---|
| Vexto dark telemetry — default structural family | `Dark mode/dark mode refrence 1.jpg` through `27.jpg` | Metric label/value/unit/chart anatomy; compact groups; restrained neutral navigation; optical glass on selected/media panels; spatial callouts | Bus drawings, transit terminology, street routes, physical monitor frames and promotional typography |
| Dentale spatial glass — light material adaptation | `Light mode/reference ui image 3.jpg` through `22.jpg` | Pale blue frost; continuous model canvas; inspectors; inset rounded-square tools; nested media | Dental red/pink anatomy, dental tool glyphs, patient terminology and weak white-on-pale text |
| Travel assistant — separate family | `Light mode/reference ui image 1.png`, `2.png` | Useful comparison of readable dark text on pale surfaces | Yellow assistant, hotel content, travel photography and its product layout; not merged into this system |

Vexto is the default because repeated product views support survey/telemetry composition and metric anatomy, while D12 explicitly names the font family and weight labels. The **exactly three primary anchors for this default source family** are:

1. **`Dark mode/dark mode refrence 1.jpg`** — monitor's application region: full composition, navigation capsule, grouped filters, metrics, chart and selected/ordinary card distinction. High confidence in relationships; photographed perspective prevents direct CSS measurements.
2. **`Dark mode/dark mode refrence 9.jpg`** — terrain and floating callout: continuous spatial imagery, glass transmitting blue/green content and foreground/background separation. High confidence in material appearance; no alpha, blur kernel or geospatial data is available.
3. **`Dark mode/dark mode refrence 12.jpg`** — type specimen: names Helvetica Neue and Light, Regular and Medium. High confidence in the printed names; specimen sizes are not application heading sizes, and no font binaries were supplied.

**Missing theme evidence:** these three do not establish a light theme. There is no observed light/dark pair for Vexto. The light implementation is an authored Dentale adaptation supported especially by L14's pale card and L16's inset tool. D8 remains important secondary material evidence. All are audited; supplementary references are not additional primary anchors.

The immediate user-approved appearance targets are `public/mockups/transect-dark-v2-refined.png` and `public/mockups/transect-light-v2.png`. They are generated raster compositions, not editable design files. The earlier files without `v2` are superseded. The two approved images differ slightly in glyphs, positions and control shape; implementation intentionally unifies their geometry.

## 3. Foundations, color roles and visual distribution

| Role | Dark implementation | Light implementation | Evidence / basis / scope |
|---|---|---|---|
| Canvas | `#030606`; graded terrain | `#B6CBD9`; cool washed terrain | P: authored base. D9 and L22 support continuous content fields, not these exact hex values. |
| Primary ink | `#FEFEFF` | `#222323` | S swatches D22 / L9; role assignment P. Light ink explicitly corrects the source's pale text per user feedback. |
| Secondary ink | `#B4B7B0` | `#2D4252` | S swatches D2 / L7; assignment P. Never lower opacity of a whole parent to dim labels. |
| Tertiary ink | `#A0A6A4` | `#415665` | P readable metadata. Not original sampled text. |
| Ordinary glass | `rgba(9,12,13,.82)` | `rgba(202,219,233,.72)` | P tuned after browser rendering; D1/D8 and L14 support material family. Both are composites, not opaque palette swatches. |
| Selected / raised glass | `rgba(29,34,36,.70)` | `rgba(215,229,241,.64)` | P mapping informed by D8 and L16. Use selective emphasis, not the same bright treatment everywhere. |
| Chart | Gray-white trace, dim dashed grid | Dark slate trace, slate dashed grid | D11 observed; exact colors and data P. A tiny amber segment carries an exception. |
| Status | Amber `#EBA640`, green `#83BA7E`, red `#EC8880` | Amber `#956000`, green `#356B40`, red `#A13B34` | Exact values P. Use a 6 px dot **and a word**. The dot is not a general action fill. |
| Interactive accent | Neutral raised capsule, clear foreground | Neutral inset capsule, dark foreground | D1/L16 observed selection language; hover/focus are proposed states. |
| Media | Dim blue-black water, muted olive/stone detail | Blue/green relief under an icy wash | Media remains content. It must not become a component background color extracted from a large swatch. |

The palette JSONs contain six image-wide swatches per image, often quantized in 50 / 25 / 12.5 / 6.25 / 3.13 / 3.12 percent increments. They do **not** measure semantic role coverage. For example, black may be a foreground person or device bezel; pink can be dental content; blue may be the backdrop seen through glass.

Desktop composition should keep a large uninterrupted central/right media region. Peripheral glass occupies roughly one third of the approved-style screen footprint; the rest is exposed content, with more content inside image cards. This is a layout guide, not a universal color-percentage target. The implemented rectangle-union measurement is recorded in the validation appendix; it counts container footprints, including nested photos, and is explicitly different from measured color coverage. Small status/data accents occupy a very small fraction of the screen. Do not enlarge them into whole highlighted panels without a new semantic reason.

## 4. Glass is a stack of layers

Order: **media → local backdrop blur → translucent tint → local reflection → thin curved rim → sharp foreground**. The background varies across a card, while foreground text and glyphs remain crisp. Do not blur the entire card or add a whole-page frosted blur.

The live recipe uses a 26 px `backdrop-filter`, a 1 px contour, a separate masked edge highlight, a tint and a restrained upper-left reflection. These are **implementation proposals**, not recovered source parameters. A flattened screenshot cannot establish original blur, alpha or shadow values.

```css
.glass {
  position: relative;
  border: 1px solid var(--rim);
  border-radius: var(--radius-card);
  background-color: var(--surface);
  background-image: var(--reflection);
  box-shadow: var(--shadow);
  backdrop-filter: blur(26px);
  -webkit-backdrop-filter: blur(26px);
}
.glass::before {
  content: "";
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  pointer-events: none;
  border: 1px solid transparent;
  background: linear-gradient(128deg,
    var(--rim-light), transparent 28%, transparent 75%, var(--rim)
  ) border-box;
  mask: linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
}
```

Load foundation CSS **before** layout CSS. A later `.glass { position:relative }` overrode the absolutely positioned header during the first build and clipped it at the viewport edge. Do not rely on `overflow:hidden` to conceal incorrect bounds.

Dark reflection is strongest only at the upper-left start: alpha .20, falling to .035 at 26% and transparent by 48%. Its base remains near-black. The isolated D8 showcase is more reflective than ordinary cards; it is not a universal fill. Light reflection starts at white alpha .46, falls to .11 at 35% and disappears by 60%. Solid fallbacks are `#101415` / `#CBDCE8` when backdrop filtering is unavailable.

Light mode is **not a global image inversion**. Ink, tints, outlines, status colors, chart strokes, media grading and canvas wash map independently. Full gradients, filters and shadow values are in Appendix A.

## 5. Typography and actual available weights

Use locally bundled **Inter 300 / 400 / 500**. These real files are imported from `@fontsource/inter`; `font-synthesis:none` prevents invented weights. Inter is a disclosed substitute for Helvetica Neue. Its shapes and apparent stroke density differ from the raster references, particularly white text on black. Do not pretend the source font is available or request nonexistent 200/600 weights.

| Product role | Implementation size | Weight | Relationship and exceptions |
|---|---:|---:|---|
| Page heading | 28 px desktop, 27 px narrow mobile | 300 | Compact two-line heading/subtitle group, not a marketing headline |
| Metric | 54 px; 48–54 px at intermediate desktop widths | 300 | Large count before small unit, `letter-spacing:-.055em`, line-height 1.12 |
| Reading strip | 48 px desktop; 42 px compact desktop; 32 px mobile | 300 | Three equal groups, small regular units; never allow units to collide |
| Card heading | 17 px; inspector 18 px | 400 | Label first, then value or imagery |
| Body / navigation | 14 px | 400 | Selected capsule uses 500 |
| Secondary labels | 12–13 px | 400 | Use an explicit secondary color, not parent opacity |
| Date / compact ID | 11 px / 9–10 px | 400 | Tiny IDs are secondary reference-like metadata; increase if the new task makes them essential |
| Units | 15–16 px desktop, 10 px mobile readings | 400 | Baseline aligned, close to numeral; unit is lower emphasis, not superscript |

All numerical sizes in this table are P: reconstructed implementation values. The type names in D12 are observed; its giant specimen sizes and editorial titles are not transferred into application headings. UI density must be judged at the actual viewport, not from an enlarged specimen crop.

## 6. Reusable anatomy, independent of screen arrangement

| Component | Internal order and geometry | Evidence, basis, confidence, exceptions |
|---|---|---|
| Navigation capsule | 60 px desktop parent; pill radius 999 px; selected child 40 px tall; brand left, navigation next, utilities right | D1 upper UI / D23 mobile selection. O anatomy, P dimensions. High relationships; mobile tab placement is authored. |
| Filter group | 54 px parent, 7 px vertical inset, 34 px selected child, compact label + regular count | D1 grouped filter. O group/selection, P size. Three conditions are survey-specific. |
| Metric card | 22 px outer radius, 20 px padding, heading + NE arrow, large value/unit, short caption, thin chart/date strip | D1 metric / D11 graph. O anatomy, P numbers. Arrow is decorative here because no metric drilldown was requested. |
| Site / entity row | 102 px high; 18 px corner; 10 px inset; 80 px thumbnail, 13 px inner corner; name/ID, date, status at right | D1/D2 selected asset anatomy adapted to an original horizontal row. P layout, high family consistency. Two rows visible; list scrolls for remaining records. |
| Media inspector | 30 px corner; 20 px padding; heading/ID, 18 px gap, 230 px image, status footer; nested image 26 px corner | D9 callout + L22 inspector; dimensions P. Image content is a generated terrain crop, not a surveyed capture. |
| Reading bar | 30 px corner; 26×24 px outer padding; 3 groups with thin separators; reduced padding/type on narrow screens | D3 horizontal value/graph and original approved composition; exact strip P. Equal grouping, not three separate unrelated cards. |
| Note / input | 22 px parent; 17–19 px inset; regular label, editable transparent textarea; inset capsule save action | Input states unobserved; P adapted from grouped controls. Do not turn it into an opaque white input in light mode. |
| Floating tool | 52×52 px, radius 18 px, centered 24–25 px fine icon; 44 px on mobile | L16 rounded-square anatomy. P numerical reconstruction. Both themes share this shape; generated light mockup's circular version is superseded. |
| Site pin / label | 37 px ordinary disc, 52 px selected, filled pin glyph; small separate frosted label capsule | D9 and approved raster spatial callouts. P placement. Label moves above the pin on mobile. No connector paths. |
| Status | 6 px dot + 12 px regular word, 9 px gap | D1/D6/D20 semantic accents. O anatomy; P survey meanings and exact palette. |

Use an 8 px gap between close siblings; 12 px media insets; 20–24 px panel/group padding. These are authored implementation values, not a measured universal grid. Parent corners should exceed the corners of their inset children. Fully rounded navigation is distinct from rounded-square map tools. Keep icons in the same Phosphor Light family; the solid map-pin silhouette is an intentional location exception. Do not mix Dentale's segmented tool glyphs with unrelated filled icons.

## 7. Original Transect screen composition

The screen is fictional survey content: six sites, two Watch and one Attention; 24.8 m basin clarity; Emerald inlet selected with 18.4 °C / 8.6 mg/L / 7.3 pH. These values are sample data, not scientific observations. The miniature chart uses its own coherent illustrative sequence and labelled scale; it does not claim to derive the basin average or selected-site reading.

At the 1586×992 desktop reference viewport:

- Header inset 24 px horizontally, 20 px vertically, height 60 px.
- Heading around 3.8% from left, 11.2% from top.
- Left stack at 3.8% left / 18.7% top, width about 374 px: condition filter → clarity metric → two visible entity rows → note.
- Inspector at 2.6% right / 10.1% top, width about 350 px.
- Reading bar from 48.3% left to 15.8% right, 7.1% above the bottom.
- A broad open basin remains between the two panel groups. Utility tools sit near the right edge; a quiet illustrative scene caption replaces the raster's unsupported distance scale.

These positions recreate the approved original composition; they are not reusable component anatomy. For another problem, keep the hierarchy and contiguous media contribution but rearrange the panel groups as the task needs. Do not copy source promotional monitor layouts or the survey's field names as universal product rules.

At 901–1350 px, compact the left and right columns, reading numerals and gaps. At 601–900 px, use two content columns below a visible scene region. At 600 px and below, use a single scroll flow: header/tabs → heading and visible scene → filter → selected inspector → metric → entity rows → readings → note. The background is fixed to the viewport; full-page browser screenshots show it in the first viewport only, so also inspect scrolled viewport captures. Do not scale a desktop screenshot down to phone size.

## 8. Three.js: purposeful depth, shared spatial coordinates

The implementation uses Three.js 0.185.1 directly, without a second scene framework. `src/workspace/Terrain.jsx` owns the renderer; React/HTML owns labels, text, panels and accessible controls. This is **2.5D image-textured relief**, not a georeferenced terrain model or freely orbitable 3D map.

The local original asset is `public/assets/basin-terrain.png`, 1586×992 px. It was generated by removing UI from the approved light mockup and reconstructing covered terrain. The model introduced differences under removed panels, including an upper-right tarn. It is illustrative generated media, not a placeholder card, stock survey capture or source geography.

Implementation recipe:

1. `PlaneGeometry(3.197580645, 2, 160, 100)` creates 32,000 triangles. Build a small 161×101 analysis canvas from the texture.
2. For each vertex, compute `luma = .2126*r + .7152*g + .0722*b`, and `water = clamp((min(g,b)-r)*8, 0, 1)`. Set `z = luma * (1-water) * .10`. This gives a low-relief optical illusion; image brightness is not elevation.
3. Use `MeshBasicMaterial` with the texture marked `SRGBColorSpace`, and renderer output `SRGBColorSpace`. The image already includes its lighting. The [Three.js color-management guide](https://threejs.org/manual/en/color-management.html) explains the separation between texture and output color spaces.
4. Use an orthographic camera at z=3, with 1.04 overscan to protect edges. Bound explicit zoom to 1–1.35. A fine pointer offsets camera x by at most .10 and y by .065 scene units; it settles using exponential interpolation. No automatic orbit or endless animation.
5. Store each site at normalized image coordinates `(u,v)` with top-left origin. Convert to world `((u-.5)*width, (.5-v)*height, relief(u,v))`, then project with the **same camera**. Place the HTML marker at that projected screen point. Never maintain a separate guessed percentage position while the mesh zooms.
6. Mobile is an authored reframe: camera center y=-.40, base zoom 1.65; tablet y=-.48 / base zoom 2.0. Selected labels move above the pin. The scene's exact geographic orientation is not asserted.
7. Cap pixel ratio at 1.75, render only while input/view changes settle, pause while the document is hidden, and dispose geometry, material, texture, listeners, observer and renderer on unmount. Under reduced motion, keep pointer camera movement off and make explicit view changes immediate.
8. If WebGL2 is unavailable or the context is lost, retain the graded static terrain and labels. Disable unavailable view controls. Theme switching and local content still work.

Scene values have explicit units in Appendix A. Approximate heights and camera motion are new proposals requested by the user, not interactions observed in the source images. Use the scene to support the new task: a model, site, specimen or other spatial asset. If the new problem is not spatial, choose meaningful media rather than inventing a map.

## 9. Interactions and state treatment

The user initially required only a working theme switch. This build also includes small local conveniences: condition filters, scrollable site list, selection updating inspector/readings, a search input under Sites, editable notes saved in local storage, and terrain zoom/reset. There is no backend, deployment, account workflow, routing service or external write.

| State | Implemented behavior | Evidence status |
|---|---|---|
| Theme | Sun/moon button, stored in `transect-theme`; document color scheme and semantic variables change | Authored mapping; no original paired-theme toggle is observed |
| Selected | Capsule fill / brighter site border; selected location has larger pin and label | Source-backed visual language; local selection behavior P |
| Hover | Quiet raised tint, no movement or bright glow | P, unobserved in still images |
| Focus | 2 px contrasting outline, 4 px offset; native keyboard support; skip link | P, unobserved. Do not remove focus to make screenshots cleaner |
| Disabled | Note save disabled until edited; zoom bounded, unavailable scene controls disabled | P; reduced foreground/tint, not whole-panel opacity |
| Empty results | Clear message and Clear filters action; selected inspector remains available as context | P; changing results does not silently erase the current inspection |
| Saved note | Local state updates visibly and persists after reload; storage failure keeps draft and announces failure | P; never claim a save if storage fails |
| Touch | Reflowed cards and 44 px view controls; site selection and theme toggle support taps | P; tested in Chrome mobile emulation, not physical devices |

Desktop source metadata is sometimes faint. This implementation improves secondary ink instead of copying every contrast failure. The small 9–10 px site ID remains a compact secondary label and is a known density compromise. Increase it for tasks in which the identifier is essential.

## 10. Adapting this to another problem statement

Start by mapping concepts, not reusing survey copy:

| New problem needs | Reuse | Example substitution |
|---|---|---|
| A collection of inspectable entities | Horizontal image/entity row, selected border, compact filter | Survey sites → specimens, rooms, assets, installations |
| One primary health/performance measure | Label/value/unit/caption/chart metric | Water clarity → temperature, utilization, defect count |
| A currently selected entity | Media inspector with heading, image and small status | Inlet image → original specimen photograph or model closeup |
| Related measurements | Unified three-cell reading strip | Temperature/O₂/pH → the domain's three comparable readings |
| A user annotation | Quiet local note card with inset save action | Field note → review note or inspection annotation |
| Spatial relationships | Detailed scene and camera-projected pins | A facility floor, object model or real georeferenced map when supplied |

Use realistic original content. Establish the meaning of colors before assigning them. A red dental model does not make the new product red, and an amber chart exception does not make all primary actions amber. Replace the media with an appropriate original/permitted asset while maintaining its importance in the composition. Report reused illustrative crops if there is only one asset.

If only this Markdown file is supplied, generate or source an appropriate new scene. For a comparable alpine example, use this standalone asset brief: “Detailed photorealistic oblique overhead alpine relief, broad blue-green lake centered toward the right, rugged pale stone/snow peaks across the top and right, muted forested slopes lower left, softly directional daylight, terrain filling the frame, no horizon, text, interface, pins, paths or scale, aspect ratio 1.60:1.” Apply the separate dark/light grades afterward. Do not generate an entire raster UI and use invisible hit areas as the implemented product.

First render a compact component region in both themes. Compare it against the approved images or, if they are not supplied, the anatomy and material rules here. Correct typography weight/scale, local glass reflections, tint, borders, corner hierarchy and inset spacing. Then assemble the new screen. Inspect real screenshots at desktop and mobile widths, including scroll positions and keyboard focus. When a source cannot establish a state, mark the implementation as a proposal. Do not invent fidelity scores.

## 11. Evidence ledger for important rules

O = directly observed; S = supplied palette; M = performed measurement; E = visual estimate; P = proposed implementation. Confidence applies to the rule's transfer, not to recovering hidden design-file parameters.

| Rule | Filename / visible region | Direct observation | Scope / basis / confidence / exceptions |
|---|---|---|---|
| Quiet ordinary vs optical selected cards | D1, monitor UI's ordinary cards and selected vehicle; D8, card face | Selected face has stronger reflection; many ordinary cards are subdued | Ordinary/selected surfaces. O high; exact alpha P medium. Do not put full showcase reflections on every item. |
| Spatial background remains content | D9, lake/callout; L22, central model and peripheral panels | Rich continuous content sits behind discrete overlays | Composition. O high; new geography/media P. Device edges and wall are excluded. |
| Separate local transmitted colors | D9 water and glass callout; L7 upper/lower panel | Blue/green/midtone changes follow backdrop and lighting | Glass. O high; blur26/tint/shadow P. Whole-card blur is not supported. |
| Dark neutral palette | D1 ordinary panel sample `[950,916,972,941]` | Measured median `#1E1F21` | Source-pixel M, high for sample only. Not a recovered opaque design token. Live darker tint follows approved revision. |
| Local dark reflection | D8 `[418,653,490,691]` and `[403,1008,475,1037]` | Measured upper `#333434`, lower `#0D0D0D` | Source-pixel M, high for boxes. Shows variation; source alpha cannot be derived. |
| Pale frost | L14 `[1444,1884,1567,1966]` | Measured median `#C3CDD7` | M high sample; P live RGBA. Does not imply white foreground is readable. |
| Tool edge | L16 `[2243,2048,2304,2130]` | Measured lit edge `#C9D3DC`; inset rounded-square anatomy visible | M color / O shape, high. Size18/52 P; normalized across themes. |
| Type hierarchy | D1 metric region; D12 specimen | Large light values, smaller units, regular labels; named Light/Regular/Medium | O high role relationship; P pixel values. Inter substitution disclosed; no specimen-size transfer. |
| Fine chart/data emphasis | D11 chart crop | Gray context, white salient trace, small amber exception, dashed guides | O high; P 1.1/1.3 px and illustrative data. No universal amber action role. |
| Nesting and density | D1 repeated groups; L16 nested selected tool | Child insets, repeated nearby gaps, parent corners exceed children | O/E high relationship; P dimensions. No universal source grid was measured. |
| Light text correction | L9 white-on-pale labels; user readability feedback | Reference text can be faint over pale glass | P intentional ink reassignment, high confidence in user intent. Not literal original text color. |
| Shared dark/light geometry | Approved generated v2 images | Control silhouettes and tiny layout positions drift between rasters | P deterministic components. Sources are unrelated products, not a proven original theme pair. |
| Responsive layout / states / camera | D23 mobile presentation; approved desktop composition | Only still-image structural evidence | P breakpoints, focus, hover, disabled, zoom and motion. Must be verified in browser; not presented as observed behavior. |

Source-pixel sampling used Pillow / NumPy, explicit rectangular boxes, and median RGB statistics; luminance calculations use sRGB linearization. `evidence/reference-audit-v2/audit-data.json` contains raw dimensions, hashes and sample records. `tools/audit-reference-colors.py` reproduces that analysis. Boxes are `[left,top,right,bottom]` in original source pixels. CSS geometry was authored and checked in the rendered DOM; it was not measured out of a perspective photo.

## 12. Files, running the reference and limits

```text
npm install
npm run dev
```

Open the local URL printed by Vite. This session uses `http://127.0.0.1:5174/` because 5173 was already occupied. `/calibration` shows the material sheet. `npm run build` creates `dist`; `npm test` checks the local model; `npm run test:browser` runs the interaction suite against a running app (set `APP_URL` if its port differs).

Active implementation: `src/main.jsx`, `src/theme.js`, `src/workspace/*`, `src/model.mjs`, `design-tokens.json`. The historical v1 `App.jsx`, `Terrain.jsx`, `components.jsx`, `data.js`, `styles.css` and `app.css` have been archived to `evidence/build-v3/legacy-source` and are **not imported by the active entry point**. Do not revive their opaque dashboard or route path. Root `DESIGN_SYSTEM.md` and `REFERENCE_SELECTION.md` point to the current handoff; v1 tokens/viewer are archived under `evidence/build-v3`.

For exact asset continuity, pass `design.md`, `public/assets/basin-terrain.png`, the two approved v2 PNGs and `calibration-sheet.png` to the next agent. For a new domain, `design.md` plus the new problem statement contains the complete style brief and live tokens; create appropriate new media.

No source Figma files, original blur/alpha stack, Helvetica Neue binaries, georeferenced map, routes, elevation dataset or native 3D model were supplied. The scene and crop imagery are generated and illustrative. No live service is connected, and no site has been deployed. Browser screenshot verification covers the combinations listed in the validation appendix; it does not claim Safari, physical-phone or broad GPU certification.

Inter is OFL-licensed, Phosphor and Three.js are MIT-licensed; local license copies are in `public/licenses`. The old USGS/Pexels assets remain on disk but are not used by this screen. Source UI references are used for local analysis; source branding, bus/dental content and device photos are not shipped as product artwork.

## Validation of the built reference

The validation report appended below records the actual screenshots, corrections and interaction checks. Image-generation drift, authored theme pairing, font substitution, illustrative relief and inferred dimensions remain explicit limitations. The implementation uses real semantic text and local state; it does not overlay transparent buttons on a finished screenshot.


### Transect implementation validation — revision 3

8 September 2026. This report covers the real React/Three.js interface, superseding the prior raster-viewer validation.

## Reference-backed choices

- D1: compact navigation capsules, grouped filters, large light metric with reduced unit, quiet neighboring cards.
- D8/D9: localized reflection, dark lower glass, transmitted terrain colors and content-tied callouts.
- D11: thin neutral graph, dashed guides and a small amber exception.
- D12: named light/regular/medium type roles; actual Inter 300/400/500 are bundled substitutes.
- L14/L16/L22: icy glass, inset rounded-square tools and continuous media beneath peripheral inspectors. Light ink is an intentional readability correction; these unrelated source products are not claimed to be a paired theme.

## Specific mismatches found and corrected

1. **First material study looked too flat.** Increased only the upper-left reflection, tapering across the face. Dark tint stays near-black; local edges remain visible. Compared the rendered study with the approved v2 images before assembling the full screen.
2. **Initial light terrain and glass were grayer/darker than the approved image.** Increased the blue-white scene wash and pale panel tint. Reduced photo contrast while preserving actual detailed content. Dark/light ink is now deterministic CSS, replacing approximate raster text colors.
3. **Desktop header clipped at the right edge.** A later foundation `.glass` rule overrode its layout position. Corrected CSS import order; actual header bounds now remain inside the viewport.
4. **Mobile inspector shrank to its content and readings collided.** Set its width to the available column and restored the responsive type/padding rules. Mobile now has a full-width inspector and separate reading cells.
5. **Compact desktop chart dates touched the card boundary and the compass overlapped the note.** Allocated graph height from remaining card space and moved the compact-screen caption below the note.
6. **Tablet selected site fell below the exposed scene.** Reframed the same camera/texture and kept marker projection in that shared camera space. Labels are hidden once the scene scrolls out of view, and clipped edge markers are suppressed.
7. **Static fallback was darkened twice.** The state class and image-layer class collided. Renamed the backdrop layer, removed the double filter and derived fallback image framing from the same camera dimensions.
8. **Generated theme images disagreed on tool shape and small positions.** Both themes now use the same HTML geometry and 18 px rounded-square tool containers.
9. **Raster distance scale had no supplied geospatial basis.** Replaced it with an illustrative scene caption. There are no route connectors, fake distances or claimed elevations.

The initial and corrected screenshots are in `evidence/build-v3`. Visual review used actual PNGs, not a self-assigned fidelity score. The palette and pixel methods are separated from estimates in `design.md`.

## Rendered and exercised

| Viewport | Dark | Light | Verification |
|---|---|---|---|
| 1586×992 desktop | Screenshot inspected | Screenshot inspected | Theme click/keyboard/persistence, all local workflows, WebGL drawing and view controls |
| 1440×900 laptop | Screenshot inspected | Screenshot inspected | Theme click/keyboard/persistence, corrected chart/footer and bounds |
| 768×1024 tablet | Screenshot inspected | Screenshot inspected | Layout bounds, reading-cell separation and shared scene framing |
| 390×844 mobile | Full page + viewport + scrolled view inspected | Full page + viewport + scrolled view inspected | Theme click/keyboard/persistence; additional touch-emulated filtering and site selection |
| Representative calibration, 1480 px wide | Inspected alongside light | Inspected alongside dark | Typography, metric, card, navigation, input, status and media overlay |

Chrome headless and Chrome mobile emulation were used. Full-page images of a fixed background show the scene at the first viewport only; separate scrolled viewport captures verify the actual glass/media relationship during scrolling. No Safari or physical-phone testing is claimed.

Interaction checks exercise condition filters, site selection changing imagery and readings, search with zero results and clear action, note editing/saving/persistence, keyboard focus and theme switching. Reduced motion keeps the pointer camera stationary. WebGL-disabled rendering uses a static image and working theme switch. Three.js reports one draw call and 32,000 triangles; zoom moves the projected marker together with the scene and reset restores the default view. All three real font weights load. The checked widths have no horizontal page overflow, header/inspector/reading bounds stay inside the viewport, and reading cells do not overlap.

The model suite checks combined text/condition filtering, preserving unrelated notes, persisted edits, corrupt storage handling and surfaced storage failure. Browser checks record page errors in `evidence/build-v3/browser-checks.json`; layout and footprint measurements are in `layout-checks.json`.

## Performed measurements

At 1586×992, the union of the outer header/filter/metric/list/note/inspector/reading/tool rectangles occupies **35.23%** of the viewport. This includes nested photos and gaps within the list/tool group; it excludes heading and pins. It is a measured DOM footprint, not pixel segmentation or a reusable exact color-coverage ratio.

In the exposed-scene sample `[450,90,1170,740]`, mean linear luminance is 0.00805 in the approved dark raster and 0.00620 in the implementation; light is 0.36267 versus 0.35932. The first light implementation measured 0.32051 before the wash correction. Geometry and imagery differ, so these numbers describe tonal distribution only, not similarity or fidelity.

The card's text-free patch `[402,316,410,352]` has median RGB `[8,12,12]` in dark and `[184,202,214]` in light. Comparing the exact CSS primary/secondary ink with this one background patch gives 19.50:1 / 9.68:1 dark and 9.35:1 / 6.19:1 light. These calculations verify the intended direction of the text-color correction. They do not certify every point on translucent cards. Method and raw values: `tools/measure-build-v3.py`, `evidence/build-v3/pixel-measurements.json`.

## Remaining deviations and unavailable assets

- The backdrop is generated, image-textured **2.5D relief**, not a native geospatial terrain model. Image-derived brightness is not elevation. A new tarn and terrain detail appeared when the covered UI regions were reconstructed.
- Site images are different crops of that one original terrain asset, not six independent real-world captures. The data and geography are fictional. There are no empty media cards.
- Inter differs from Helvetica Neue and from the generator's drawn glyphs. Large values remain real weight 300; no thin weight is synthesized. Tiny 9–10 px IDs remain secondary metadata and should be enlarged if task-critical.
- Glass alpha, blur, reflections, numerical geometry, responsive reflow, state mappings and camera motion are authored reconstruction values. The original layer stack and source 3D geometry were unavailable.
- Light text deliberately departs from Dentale's faint white foreground. Dark mode is intentionally very low-key; reflections are quieter than D8's isolated showcase.
- The default site list reveals two rows at once and scrolls for the remaining sites. Filters/search preserve the current inspector as context until another site is chosen.
- No backend, deployment, real routing, account system or measured navigation scale is included. Local storage can be unavailable; the implementation retains the draft and announces save failure.
- The production build includes the Three.js renderer in a large JavaScript chunk. Vite reports a size advisory; this is not a build failure. Performance across low-end physical devices has not been benchmarked.

No global contrast certification or pixel-perfect reconstruction is claimed. Representative pixel measurements and observed bounds are recorded separately; they do not prove every translucent-background combination meets a contrast target.


## Appendix A — complete live tokens

These values are consumed by the implementation. Explicit units and source-family boundaries travel with this document. Reconstruction values are proposals, not hidden design-file measurements.

```json
{
  "version": "3.0.0",
  "status": "Live implementation; author-created paired theme from separate source families",
  "precedence": "Approved v2 mockups + design.md supersede v1. Screenshot-derived alpha or exact font sizes are not claimed.",
  "unitConventions": {
    "dimensions": "CSS px",
    "colors": "sRGB CSS color with alpha ratio 0–1",
    "time": "ms",
    "sceneCoordinates": "normalized image UV, origin top left",
    "fontWeight": "numeric real font weights"
  },
  "sourceFamilies": {
    "default": "Vexto dark telemetry D1–D27",
    "lightAdaptation": "Dentale spatial glass L3–L22 with user-requested dark ink",
    "excluded": "Travel assistant L1–L2"
  },
  "shared": {
    "font-body": {
      "value": 14,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "font-meta": {
      "value": 12,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "font-title": {
      "value": 28,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "font-card": {
      "value": 17,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "font-metric": {
      "value": 54,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "font-reading": {
      "value": 48,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "radius-card": {
      "value": 22,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "radius-large": {
      "value": 30,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "radius-media": {
      "value": 20,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "radius-control": {
      "value": 18,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "radius-pill": {
      "value": 999,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "space-small": {
      "value": 8,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "space-inset": {
      "value": 12,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "space-card": {
      "value": 20,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "space-section": {
      "value": 24,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "border-width": {
      "value": 1,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "glass-blur": {
      "value": 26,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "control-size": {
      "value": 52,
      "unit": "px",
      "valueBasis": "proposed reconstruction; not a source pixel measurement"
    },
    "font-family": {
      "value": "\"Inter\", sans-serif",
      "unit": "font-family"
    },
    "weight-display": {
      "value": 300,
      "unit": "font-weight"
    },
    "weight-body": {
      "value": 400,
      "unit": "font-weight"
    },
    "weight-selected": {
      "value": 500,
      "unit": "font-weight"
    },
    "transition-theme": {
      "value": 360,
      "unit": "ms"
    }
  },
  "themes": {
    "dark": {
      "canvas": {
        "value": "#030606",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "text": {
        "value": "#FEFEFF",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "text-secondary": {
        "value": "#B4B7B0",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "text-muted": {
        "value": "#A0A6A4",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "surface": {
        "value": "rgba(9,12,13,0.82)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "surface-raised": {
        "value": "rgba(29,34,36,0.70)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "surface-solid": {
        "value": "#101415",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "rim": {
        "value": "rgba(220,232,237,0.16)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "rim-light": {
        "value": "rgba(238,248,251,0.53)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "divider": {
        "value": "rgba(212,227,231,0.15)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "reflection": {
        "value": "linear-gradient(135deg, rgba(208,227,237,.20) 0%, rgba(137,170,180,.035) 26%, transparent 48%)",
        "unit": "CSS image",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "shadow": {
        "value": "0 10px 32px rgba(0,0,0,.12), inset 0 1px 0 rgba(231,245,251,.07)",
        "unit": "CSS shadow",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "trace": {
        "value": "#D6DBD9",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "watch": {
        "value": "#EBA640",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "healthy": {
        "value": "#83BA7E",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "attention": {
        "value": "#EC8880",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "focus": {
        "value": "#C2D9E4",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "terrain-filter": {
        "value": "brightness(.25) saturate(.55) contrast(1.13)",
        "unit": "CSS filter",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "media-filter": {
        "value": "brightness(.48) saturate(.64)",
        "unit": "CSS filter",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "terrain-wash": {
        "value": "radial-gradient(ellipse at 60% 49%, transparent 24%, rgba(0,4,6,.20) 82%)",
        "unit": "CSS image",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "pin": {
        "value": "rgba(17,24,25,.76)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "selection": {
        "value": "rgba(178,198,208,.12)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      }
    },
    "light": {
      "canvas": {
        "value": "#B6CBD9",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "text": {
        "value": "#222323",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "text-secondary": {
        "value": "#2D4252",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "text-muted": {
        "value": "#415665",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "surface": {
        "value": "rgba(202,219,233,0.72)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "surface-raised": {
        "value": "rgba(215,229,241,0.64)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "surface-solid": {
        "value": "#CBDCE8",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "rim": {
        "value": "rgba(249,253,255,0.68)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "rim-light": {
        "value": "rgba(255,255,255,0.95)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "divider": {
        "value": "rgba(63,90,111,0.24)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "reflection": {
        "value": "linear-gradient(135deg, rgba(255,255,255,.46) 0%, rgba(244,250,255,.11) 35%, transparent 60%)",
        "unit": "CSS image",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "shadow": {
        "value": "0 8px 28px rgba(40,73,94,.10), inset 0 1px 0 rgba(255,255,255,.35)",
        "unit": "CSS shadow",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "trace": {
        "value": "#2D4252",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "watch": {
        "value": "#956000",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "healthy": {
        "value": "#356B40",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "attention": {
        "value": "#A13B34",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "focus": {
        "value": "#244E6B",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "terrain-filter": {
        "value": "saturate(.65) brightness(1.10)",
        "unit": "CSS filter",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "media-filter": {
        "value": "contrast(.82) saturate(.72) brightness(1.10)",
        "unit": "CSS filter",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "terrain-wash": {
        "value": "linear-gradient(rgba(186,215,237,.55),rgba(172,205,228,.45))",
        "unit": "CSS image",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "pin": {
        "value": "rgba(210,232,245,.79)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      },
      "selection": {
        "value": "rgba(247,252,255,.27)",
        "unit": "CSS color",
        "valueBasis": "proposed semantic mapping; see design.md evidence ledger"
      }
    }
  },
  "scene": {
    "texture": "/assets/basin-terrain.png",
    "width": {
      "value": 3.197580645,
      "unit": "scene units"
    },
    "height": {
      "value": 2,
      "unit": "scene units"
    },
    "segments": {
      "x": 160,
      "y": 100,
      "unit": "segments"
    },
    "relief": {
      "value": 0.1,
      "unit": "scene units",
      "basis": "image-derived depth illusion, not elevation"
    },
    "overscan": {
      "value": 1.04,
      "unit": "ratio"
    },
    "zoom": {
      "min": 1,
      "max": 1.35,
      "step": 0.1,
      "unit": "ratio"
    },
    "cameraPointer": {
      "x": 0.1,
      "y": 0.065,
      "unit": "scene units"
    },
    "pixelRatioCap": {
      "value": 1.75,
      "unit": "ratio"
    },
    "motion": {
      "duration": 700,
      "unit": "ms",
      "reducedMotion": "No automatic camera movement; explicit zoom is instant"
    },
    "responsiveCamera": {
      "mobile": {
        "maxWidth": 600,
        "unit": "CSS px",
        "centerY": -0.4,
        "centerUnit": "scene units",
        "baseZoom": 1.65
      },
      "tablet": {
        "maxWidth": 900,
        "unit": "CSS px",
        "centerY": -0.48,
        "centerUnit": "scene units",
        "baseZoom": 2
      }
    }
  }
}
```

## Appendix B — technical audit of every supplied reference

This source audit predates the implementation. Its source observations, measured pixels and supplied palettes remain evidence. Its reconstruction proposals are superseded by the live rules above when they differ. It does not establish original paired themes or observed interaction states.

## How to read the evidence

- **Observed (O):** a visible feature or literal label in an image. An image's marketing copy is recorded as content, never treated as an instruction or a verified research result.
- **Measured (M):** file dimensions, hashes, explicit source-pixel sample statistics, or calculated color-pair luminance. The method, coordinates and raw values are in `evidence/reference-audit-v2/audit-data.json`; the reproducible analysis is `tools/audit-reference-colors.py`.
- **Supplied (S):** a hex value or percentage from the user's palette extraction. Its UI role is not supplied and must be interpreted separately.
- **Estimated (E):** a visual proportion or material interpretation. A flattened, photographed UI cannot establish exact source font sizes, corner radii, alpha, shadows or blur.
- **Proposed (P):** an authored choice for the survey mockup, including its paired theme mapping and improved text contrast. Numerical reconstruction targets below are proposals, not measurements of the references.

Every per-image record below identifies the filename, source dimensions, visible region, observed anatomy, reusable rule, confidence, exceptions and that file's supplied palette. Important cross-image rules additionally have an evidence table here. No perspective rectification or native design-file inspection was performed.

## Family boundaries

| Family | Files | Recognizable language | Boundaries and exceptions |
|---|---|---|---|
| Vexto dark telemetry | All D1–D27, with UI, branding and editorial subsets distinguished below | Near-black canvas, quiet charcoal ordinary cards, more reflective selected/media cards, light large numerals, white/gray data with small amber exceptions, semantic green/red, spatial terrain | Best-supported source for survey composition, metric anatomy and type hierarchy. D12 names a font and weights. D13 is branding; many D14–D27 pages are editorial. Their huge headings and physical imagery are not app rules. |
| Dentale blue spatial glass | L3–L22 | Continuous spatial viewport; blue/icy glass; inset rounded-square controls; peripheral inspectors; technical diagram/preview cards; cyan and pink model annotations; white foreground | Strongest light-glass material and tool-selection evidence. L4/L7/L17 are darker blue material showcases inside the light folder. They are not evidence of a separate product dark theme. White text on pale glass is often weak. |
| Travel assistant | L1–L2 | Pale neutral shell, narrow icon rail, large travel photography, overlapping yellow assistant, dark non-media text, green data, white image captions | Separate product. Its yellow assistant, travel font proportions, hotel tiles and pale road map should not be averaged into Dentale or Vexto. |

**Default structural family: Vexto.** It offers the strongest repeated evidence for map/telemetry composition, component states and typography. **Light mapping: authored adaptation of Dentale's pale glass.** These are unrelated source products, not an observed light/dark pair. The survey layout and content remain original; material and component anatomy are adapted from the references the user preferred.

## Separating UI from its presentation

Application chrome includes navigation capsules, text, cards, inputs, control trays, inspector containers and status badges. The underlying terrain, rendered dental anatomy, bus render, travel photos, file illustrations and technical diagrams are content. Translucent UI can transmit content colors without adopting those colors as its semantic fill.

Device frames, metallic edges, notches, hands, people standing before screens, walls, desks and case-study margins are excluded from component color and spacing extraction. Tilt, lens blur and depth-of-field in macro shots are presentation. The UI foreground should remain sharp even where the background seen through glass is blurred.

## Palette reconciliation and color distribution

Both palette files parse successfully and map one-to-one to the images: **27/27 dark and 22/22 light**, no duplicate filenames, no missing images or missing palette entries. Every entry reports success and six swatches. Percentages are restricted to 3.12/3.13, 6.25, 12.5, 25 and 50; totals range from 99.99 to 100.01 from rounding. This looks discretized, but the extraction algorithm is not provided, so its exact cause is unknown.

These percentages are the supplied extraction weights, **not measured screen coverage by UI role**. In D7, the foreground silhouette contributes black. In D1/D5/D6, the gray room and monitor affect grays. In L5/L6/L8, dark skin and device frames supply dark swatches. In L18/L19, pink anatomy supplies much of the palette. Small but important white text, red notifications, green health symbols and amber chart segments may be absent from six-color summaries.

| Role | Dark source behavior | Light source behavior | Survey adaptation and value basis |
|---|---|---|---|
| Neutral chrome | D1/D5/D11: near-black foundation with slightly lighter charcoal content | L3/L6/L14/L22: blue-gray rather than pure white | Dark panel targets `#161718`–`#202121` (S, D1); pale targets `#B0BFCC`, `#C8D1DB`, `#E2E7ED` (S, L14). Assignment to reusable roles is P. |
| Selected/highlighted panel | D1/D8/D20: stronger optical highlight on one asset; ordinary cards stay quieter | L16/L18/L21: bright inset rim makes the selected control distinct | Preserve selective emphasis (O); exact alpha and reflection area are P. Avoid equal strong glow on every panel. |
| Media | D9/D10: blue-black lake and green/gray relief, spatially varied | L3/L22: red anatomy over blue environment; L1/L2 use photos | Survey terrain/photos remain media. Dark water target `#1D2729` and terrain `#3A4536` are from D9 palette, not chrome tokens. No dental red background is transferred. |
| Data colors | D3/D4/D11: gray context, white salient trace, amber exception | L10/L12/L21: cyan/pink model or timeline events | White/slate chart with tiny amber exception; application meaning is P. Do not turn amber into a general action fill. |
| Status colors | D1/D6/D20: green check, red warning/count, amber repair/delay | L5/L6: small cyan active/progress labels | Retain dot plus word for survey conditions. Exact survey status colors and meanings are P; image-wide palettes do not fully recover small status swatches. |
| Overlays | D8/D9/D21: varying blurred backdrop transmission and limited edge light | L7/L14/L16: optical variation, frost at curved edges, softer center | Tint, blur, edge lighting and readable foreground are separate layers. Glass color is not represented by a single opaque hex. |
| Interactive accents | D1: selected capsule; D6: utility disks; D23: selected mobile disk | L16/L21: inset selected control/capsule | Neutral selected fill plus clear glyph/text. Theme switch is an authored control; none of these references proves a paired-theme toggle. |
| Typography | White/light gray on dark; some subordinate copy fades too far | Mostly white on pale blue, except dark text in travel family | Light primary `#222323` (S, L9) and secondary `#2D4252` (S, L7) are **new text-role assignments**. Their presence in the palette does not mean they were originally text. Dark primary `#FEFEFF` (S, D22), secondary `#B4B7B0` (S, D2); exact role mapping P. |

Distribution is hierarchical, not a universal percentage recipe. In Vexto product views, neutral panels form dense peripheral clusters, spatial imagery occupies a large contiguous central/right area, and saturated marks are small. In Dentale product views, the rendered model dominates and tool groups sit around it; pink is primarily content. The survey keeps a continuous terrain layer with peripheral panels and a clear central lake. Reflection strength must vary by component priority.

For a future editable reconstruction only, a reasonable **proposed composition budget** is 55–65% exposed spatial content and 30–40% bounded panels/navigation, with small controls occupying the rest. These are planning ranges, not measured reference coverage; optical categories overlap because content also appears through panels. No recoloring should be driven by applying the JSON percentages to components.

## Recorded color measurements

Samples use unscaled source pixels and per-channel patch medians. Boxes are `[left, top, right, bottom)`, origin at the upper-left. JPEG compression, rendering and lighting are included. These are not recovered native tokens.

| Source/region | Source-pixel box | Measured median | Implication |
|---|---|---|---|
| D1 ordinary metric interior | `[950,916,972,941]` | `#1E1F21` | Ordinary cards are dark charcoal, not mid-gray. |
| D8 upper reflected glass | `[418,653,490,691]` | `#333434` | Local reflection is brighter than the card's lower interior. |
| D8 lower glass above mini-map | `[403,1008,475,1037]` | `#0D0D0D` | One component spans substantially different apparent colors. |
| D8 external bus/backdrop | `[1253,77,1296,134]` | `#070707` | Near-black external pixels must not be mislabeled as card fill. |
| D9 lake water | `[403,442,475,499]` | `#1F3037` | Blue water is a media color. |
| D11 chart interior | `[648,115,720,173]` | `#1D1E20` | Corroborates the dark neutral chart foundation. |
| L7 upper-right glass | `[2150,1475,2273,1556]` | `#2C424F` | The light folder includes dark transmitted blue inside glass. |
| L7 lower-left glass | `[676,2499,799,2580]` | `#6C9AB3` | A single glass card cannot be faithfully reduced to one blue. |
| L14 pale glass interior | `[1444,1884,1567,1966]` | `#C3CDD7` | Supports the pale blue-gray material family. |
| L16 selected control region | `[2243,2048,2304,2130]` | `#C9D3DC` | Inset selection includes a light local region, not a flat whole-page overlay. |

Calculated opaque color pairs further explain the text correction: `#222323` over `#B0BFCC` gives **8.38:1**; `#2D4252` over that same pale color gives **5.55:1**. White over `#B0BFCC` gives only **1.88:1**. These are arithmetic comparisons of chosen colors, not accessibility certification of generated text, glass compositing or the references. Raster anti-aliasing and changing transmitted backgrounds still matter.

## Reusable anatomy, typography and geometry

The following is a reconstruction brief, not a claim that source CSS was recovered. All numerical sizes are **P**, chosen for a roughly 1600 × 1000 design canvas. Relative relationships are **O/E** and scoped by their evidence. A generated raster cannot guarantee an installed typeface, actual font weight or exact hex reproduction.

| Component/rule | Observed evidence and scope | Proposed reconstruction | Confidence / exceptions |
|---|---|---|---|
| Product heading | D1/D5 title over map; L3/L22 case title over viewport | 28–32 px, light/regular, line height 1.15; one clear screen title | High hierarchy, estimated size. D12's 128 px specimen and case-study titles are excluded. |
| Large metric | D1/D3/D8 large light figures, much smaller unit | 48–56 px light; unit 14–16 px regular aligned near baseline; label 16–18 px | High pattern, P exact sizes. Do not fade fractional digits into unreadability. |
| Body and metadata | D6 nested incident; L5/L15 sender/body distinction | Body 14–16 px regular, line height 1.4; metadata 12–13 px regular; opaque readable color | High distinction. Unreadably dim reference metadata is intentionally corrected. |
| Font weights | D12 explicitly labels Light/Regular/Medium; L14 shows heavier compact numbers | Limit survey hierarchy to light/regular/medium, commonly represented as 300/400/500 in an implementation | Literal source names observed. No font binaries supplied; CSS numbers and exact family availability are not established. L14's stronger values do not imply a universal bold face. |
| Navigation | D1/D5 text links with one rounded selected fill | Capsule about 40–44 px tall; 16–22 px horizontal padding; 8–12 px spacing; radius 999 px | High anatomy; P geometry. D23 mobile dock has a different selected disk anatomy. |
| Filter strip | D1 transport segment group with nested selection | 48–56 px outer strip, 6–8 px inset; selected child 32–40 px high | High nesting; P dimensions. Source transport counts are not survey data. |
| Metric card | D1/D3 title+arrow, value+unit, secondary line, chart | 20–24 px inner padding, 24–28 px outer radius; heading/value gap 16–24 px; chart gap 16 px | High anatomy; P geometry. Content arrangement can change while internal hierarchy remains. |
| Asset/site card | D2/D8 heading+date, image/diagram, status, spatial footer | 16–20 px padding; 20–28 px radius; consistent image inset and 12–16 px gap to text | High anatomy; survey uses a compact horizontal photo row as an authored adaptation. Bus wireframes and timetables are omitted. |
| Inspector and nesting | D6/D10 outer panel → header → tinted incident → detail rows; L22 peripheral inspector | 24–32 px outer radius, nested radius reduced by padding; 8–12 px gaps for sibling rows, 16–24 px between groups | High nesting. Dense text surfaces should transmit less detail than media callouts. |
| Input/note | D6 pill search; L5 rounded composer and separate send; current survey note | 42–48 px input height, 14–16 px text, 16–20 px horizontal padding; note body distinct from action | Input anatomy observed, field-note implementation and focus/validation P. No functional note editing is requested in this revision. |
| Small tool button | D6 disks; L16/L18 rounded-square inset tools | 44–52 px side, 16–20 px corner; centered 18–22 px glyph; 1.5–2 px line stroke | High shape families, P sizes. Survey chooses consistent Vexto-like line glyphs; Dentale's segmented glyphs are not mixed in. |
| Icon-only tray | D23 bottom dock; L11/L21 parent tray plus selected child | Parent radius 24–28 px; inset 6–8 px; optional thin separators only between task groups | High observed grouping. Actual product actions/labels would need design if implemented. |
| Status | D1/D6/D20 symbol + label, restrained tinted fill | 6–8 px dot or 14–16 px distinct symbol plus 12–14 px label; 6–8 px gap | High anatomy; P exact values. Red notification count, amber exception and green online are separate roles. |
| Borders | D8 rim stronger near reflected edges; D1 ordinary cards subdued; L16 inset light edge | About 1 px base contour with a separate softly varying inner edge | Appearance O; width P. A uniform bright border on every card would depart from ordinary product views. |
| Corner hierarchy | D1/D8 broad card corners; capsules fully rounded; L16 smaller rounded-square child | Outer radius larger than nested content; reduce nested radius by its inset instead of using one radius everywhere | High relationship, E source geometry. Perspective can make circles appear elliptical. |
| Spacing | D1/D6 compact sibling grouping, larger section separation; L22 clear space around model | Proposed 4 px base rhythm; 8–12 px sibling gaps; 16–24 px padding/group gaps; keep card text on common inner alignments | High relationship, P numeric system. No universal 8 px source grid was measured. |
| Glass composition | D8/D9/L7 blurred transmitted content; L14/L16 inset frost | Separate media → local blur → tint → curved edge/reflection → sharp foreground. If later coded, start with 20–32 px local blur; dark tint alpha 0.65–0.85, light 0.55–0.75, then calibrate against background | Material appearance high confidence, all rendering values P. No alpha, filter kernel or shadow can be recovered exactly from a flattened image. |
| Chart | D4/D11 fine context trace, emphasized short segment and points, faint dashed guides | 1–1.5 px main trace, 1 px quiet grid, 4–6 px important points; use dark slate trace on light glass | High anatomy, P values. Charts should use coherent units and data if made functional. |
| Layer order | D9 content-tied callout above map; L22 preview/inspectors/tools above render | Spatial media at back; cards and tool trays above; selected pin/label and focused control above their parent | High broad order. Exact z-index values and panel occlusion policy are unobserved. |

The original Vexto left-grid layout and Dentale peripheral-inspector layout are compositional references. Their component anatomy is reusable independently. The survey's left summary/site/note stack, right photo inspector and lower reading strip are its own arrangement. Copying a rounded rectangle without its label/value hierarchy, inset spacing, foreground contrast and media relationship would miss the actual visual language.

## Contradictions resolved explicitly

1. **Light folder does not mean white UI.** L7/L17 show dark blue transmitted glass; L14 shows pale frost. Preserve both as material contexts, not automatic theme counterparts.
2. **White reference text versus readability.** L5/L9/L14 visibly use faint white text on pale glass. The user asked for darker text, so charcoal/slate replaces it deliberately. This is an improvement proposal, not a claim of literal source fidelity.
3. **Dark source grays versus brighter prior mockup.** Source card medians are roughly #1E1F21 while the prior mockup had broad brighter transmitted areas and sunlit terrain. Darken surfaces/media independently from text; keep limited reflections to preserve glass.
4. **Large bright/pink/green extracted swatches versus component colors.** Device/photo/model/backdrop pixels do not define buttons, navigation or status.
5. **Thin typography versus readable small text.** Keep large numerals light, but use regular small text. D12 specimen sizes and editorial display sizes do not become app headings.
6. **Two icon languages.** Vexto generally uses fine line glyphs; Dentale often uses segmented/pixel-like glyphs. Borrow Dentale's control container, while keeping one line-icon treatment for the survey.
7. **Routes versus arbitrary connections.** D2/D8 mini-routes follow an angular street depiction; D9/D10 show a spatial corridor. Neither supplies route data. The survey uses independent site pins and has no connector path. The generated terrain/scale is fictional and not georeferenced.
8. **Repeated promotional views versus independent evidence.** L7/L17 and many Vexto crops repeat a component. Repetition corroborates style but does not establish extra interactions or themes.
9. **Glass versus blur everywhere.** Strong lens blur in macros is presentation. Only the transmitted backdrop should be soft; foreground text and icons remain crisp.

## Interaction evidence and unknowns

Observed visual states: Vexto selected navigation and highlighted vehicle, online/offline/repair variants, expanded/collapsed warning items; travel Overview/Hotels tab selection; Dentale selected tools, selected mode and progress/active badges. Their animation, keyboard behavior and exact click response are not demonstrated by still images.

Hover, pressed, disabled, focus, validation errors, loading, empty states, reduced motion and theme transitions remain unobserved. They must be labeled proposals if implemented later. The current deliverable is a pair of static image proposals for approval; no new app functionality is claimed. The existing viewer's earlier theme-switch tests do not validate this image revision.

## File-by-file inspection

The following records are exhaustive across the 49 originals. The source dimensions and palette values are automatically attached from the measured inventory and the supplied JSON. Anatomy observations and reusable recommendations are the visual audit. Confidence is scoped within each record; dimensions are native raster dimensions, not CSS viewport sizes.

### D1 — Dark mode/dark mode refrence 1.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Application UI photographed on a monitor; left navigation, metrics and vehicle cards; terrain at right.

**Observed anatomy (O):** Top navigation is a run of text links with one filled capsule. A four-item transport filter sits inside a darker grouped container. Online/offline blocks combine a colored symbol, label and thin large count. The efficiency card has a label, northeast arrow, large value with reduced unit, target text, dashed grid, gray trace, white peak segments and amber trough. Vehicle cards stack heading/date, line drawing, status/connectivity, mini-map and timeline.

**Reusable rule and scope (P, informed by O):** Reuse the capsule selection, label/value/unit hierarchy, compact nested grouping and quiet ordinary cards. The selected vehicle has a much stronger optical sheen than its neighbors; use that distinction for the selected survey site.

**Confidence and exceptions:** High confidence in anatomy and hierarchy. Screen perspective prevents direct CSS dimensions. The gray surround and silver monitor edge are presentation. Some reference labels are too dim; do not reproduce their low contrast.

**Supplied palette (S; image extraction, not UI-role coverage):** `#161718` (50%), `#A7A8A8` (25%), `#202121` (12.5%), `#2A2C2B` (6.25%), `#424644` (3.13%), `#6B6F6B` (3.13%).

### D2 — Dark mode/dark mode refrence 2.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Perspective macro of the selected vehicle card; center wireframe and lower mini-map.

**Observed anatomy (O):** The bus is thin technical line art rather than an icon. A capsule identifier overlays it, with a darker circular initial. The status pill is outlined; GPS and LTE have matching thin glyphs. A pale route follows an angular street network beneath a solid map pin and translucent directional wedge.

**Reusable rule and scope (P, informed by O):** Adapt the header → imagery → compact status → spatial detail anatomy to a site card. Keep overlay identifiers legible without covering the entire image. A route should follow meaningful geometry and is separate from a pin's location.

**Confidence and exceptions:** High confidence in visible layering; medium in exact control purpose. The perspective and out-of-focus top/bottom are photographic staging, not desired UI blur. The supplied picture cannot establish geographically valid routing.

**Supplied palette (S; image extraction, not UI-role coverage):** `#202221` (50%), `#4C514E` (25%), `#69706B` (12.5%), `#81867E` (6.25%), `#91968D` (3.13%), `#B4B7B0` (3.13%).

### D3 — Dark mode/dark mode refrence 3.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Standalone passenger-volume glass card over a rendered/photographic bus backdrop.

**Observed anatomy (O):** A wide rounded card has dark lower glass and a broad blurred light reflection above. Heading and arrow align across the top; large light-weight count sits above a compact graph. White and amber horizontal annotations sit over much fainter noisy traces. The bus remains visible outside the card.

**Reusable rule and scope (P, informed by O):** Use the horizontal metric-card anatomy and locally transmitted backdrop color. The graph's secondary traces should recede behind the important reading and annotations.

**Confidence and exceptions:** High confidence. The bus body contributes large grays to the palette; those grays are not base panel colors. The broad reflection is a particular lighting condition, not a universal gradient.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0A0B0C` (50%), `#7B8082` (12.5%), `#1D1E1E` (12.5%), `#3A3C3D` (12.5%), `#959799` (6.25%), `#919395` (6.25%).

### D4 — Dark mode/dark mode refrence 4.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Macro of the passenger-volume chart annotation.

**Observed anatomy (O):** A large 57k label sits above an amber rule; -8% is amber underneath. Adjacent neutral annotations use white rules. Fine noisy background traces and sparse dashed grid lines create context with little saturation.

**Reusable rule and scope (P, informed by O):** Transfer the annotation hierarchy to meaningful survey exceptions: a short emphasized segment or rule, numeric value, then small delta. Keep most data neutral.

**Confidence and exceptions:** High confidence in relative hierarchy. No evidence for animated drawing, hover tooltips or the exact dataset. Depth-of-field blur and the chart's apparent diagonal are presentation.

**Supplied palette (S; image extraction, not UI-role coverage):** `#282A29` (50%), `#333433` (25%), `#3A3A39` (12.5%), `#636362` (6.25%), `#3D4240` (3.13%), `#4D4843` (3.13%).

### D5 — Dark mode/dark mode refrence 5.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Wider desktop monitor view with left telemetry, central terrain, lower schedule table.

**Observed anatomy (O):** The left column packs filters, paired health metrics, chart and a two-column vehicle grid. The map occupies a large adjacent area and hosts capsules, category markers, a selected marker, callout and map controls. A broad lower panel uses a big schedule offset followed by dense table rows.

**Reusable rule and scope (P, informed by O):** Retain the spatial canvas plus floating context relationship and reduce repeated panel emphasis. A dense table is an optional component for data-heavy views, not a requirement for the survey mockup.

**Confidence and exceptions:** High confidence in composition; medium in smallest text. The monitor, pedestal and gray room are excluded. This repeats D1's product, so it is corroboration rather than a separate theme.

**Supplied palette (S; image extraction, not UI-role coverage):** `#151617` (25%), `#222526` (25%), `#797979` (12.5%), `#AFB0B0` (12.5%), `#929393` (12.5%), `#4E514D` (12.5%).

### D6 — Dark mode/dark mode refrence 6.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Top-right application search/utilities and warning inspector over terrain.

**Observed anatomy (O):** The search field is a long dark capsule with shortcut hint and search glyph. Circular utility controls include connectivity, support, bell with red count and avatar. A dark outer warning panel contains a muted red expanded item and a collapsed item. Expanded content indents timestamps, station rows with vertical rules and a recommendation.

**Reusable rule and scope (P, informed by O):** Use outer inspector → section header → tinted incident → indented details. Reserve saturated red for the count/symbol; use a dark low-saturation red panel. Utility icon spacing and search anatomy can transfer.

**Confidence and exceptions:** High confidence in nesting and visible expanded/collapsed states. Whether a chevron is interactive and how animation behaves are unobserved. The green underlay is terrain, not success fill.

**Supplied palette (S; image extraction, not UI-role coverage):** `#1F201E` (50%), `#A9AAAA` (12.5%), `#494744` (12.5%), `#322D2A` (12.5%), `#838582` (6.25%), `#9E9E9E` (6.25%).

### D7 — Dark mode/dark mode refrence 7.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Desktop UI shown behind a foreground human silhouette.

**Observed anatomy (O):** The same left telemetry column and central map are visible at a more distant scale. The selected vehicle card remains the most reflective left-side element. Bottom schedule/volume panels share the dark surface language.

**Reusable rule and scope (P, informed by O):** Use as a distance check for the dominant visual masses and selective emphasis established by D1/D5. Keep the central map recognizable when the interface is viewed as a whole.

**Confidence and exceptions:** High confidence for composition only. The foreground person accounts for much of the near-black image palette and must not become a layout region or component color.

**Supplied palette (S; image extraction, not UI-role coverage):** `#070708` (50%), `#292D2C` (12.5%), `#777976` (12.5%), `#161819` (12.5%), `#9E9E9F` (6.25%), `#ACADAC` (6.25%).

### D8 — Dark mode/dark mode refrence 8.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Isolated selected vehicle card over a bus backdrop, front-facing enough to read its anatomy.

**Observed anatomy (O):** The card uses a narrow curved rim, dark internal lower area, softened upper reflection and slight blue fringing near its sides. It contains title/date/arrow, fine line drawing and ID capsule, an outlined status pill, connectivity labels, mini-map and a ruler-like timeline with circular endpoints and vehicle thumb.

**Reusable rule and scope (P, informed by O):** Principal dark material reference: preserve the variation between reflection and dark transmission. Reuse its layered anatomy for an inspected site; borrow the bright rim sparingly. Maintain clean text over optical effects.

**Confidence and exceptions:** High confidence in material appearance and repeated component structure. Reflection and alpha cannot be separated from one flattened raster. The bus backdrop is media, not a surface token.

**Supplied palette (S; image extraction, not UI-role coverage):** `#060707` (50%), `#171818` (25%), `#262728` (12.5%), `#333332` (6.25%), `#353637` (3.13%), `#6A6B6B` (3.13%).

### D9 — Dark mode/dark mode refrence 9.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Map closeup: selected vehicle marker, dashed radius, route and passenger-load callout.

**Observed anatomy (O):** The callout transmits blurred green terrain and dark blue water across one rounded surface. A filled glass marker sits in a dotted circular area. The white route changes from continuous to dashed; categorical markers use blue and gray. Small arrow/title/subtitle/value sit inside the callout.

**Reusable rule and scope (P, informed by O):** Use blurred backdrop transmission for a selected-site callout, independently of map geometry. Preserve marker → label proximity. Copying the route's appearance alone cannot define its topology; survey sites remain independent.

**Confidence and exceptions:** High confidence in appearance, low confidence in the meaning of solid/dashed routes or radius. No legend or georeferencing is supplied. Palette green/blue belongs to media and transmitted color.

**Supplied palette (S; image extraction, not UI-role coverage):** `#1D2729` (50%), `#3A4536` (25%), `#444D4A` (12.5%), `#596452` (6.25%), `#646964` (3.13%), `#9BA09A` (3.13%).

### D10 — Dark mode/dark mode refrence 10.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Right side of the desktop: warning panel, detailed terrain and passenger chart below.

**Observed anatomy (O):** The same muted-red nested warning items from D6 sit above an exposed map with categorical points and a dashed white corridor. The lower passenger panel uses a brighter blurred reflection with large thin count, small unit and sparse chart.

**Reusable rule and scope (P, informed by O):** Corroborates separate surface roles: dense warning text gets a quieter background, media callouts get transmission, charts get restrained emphasis. Preserve enough terrain around overlays to maintain location context.

**Confidence and exceptions:** High confidence in panel roles. The gray frame/background are not light-theme evidence. Road/route correctness cannot be verified from this crop.

**Supplied palette (S; image extraction, not UI-role coverage):** `#1E2120` (50%), `#9C9D9C` (12.5%), `#7B7E79` (12.5%), `#312E2B` (12.5%), `#393A36` (6.25%), `#4B4C48` (6.25%).

### D11 — Dark mode/dark mode refrence 11.jpg

**Source dimensions (M):** 1440 × 1920 px. **Visible region/classification:** Efficiency-chart macro, white selected segments and right-hand percentage axis.

**Observed anatomy (O):** The base trace is low-contrast gray, peaks are white between two white dots, and selected time windows have subtle vertical area shading. A dashed reference line crosses the chart. Percentage labels sit on the right.

**Reusable rule and scope (P, informed by O):** Reusable chart anatomy: neutral baseline data, one emphasized segment, endpoint dots, quiet selection shading, external axis labels. For light mode darken the trace and guide contrast instead of retaining white.

**Confidence and exceptions:** High confidence in visual structure. The exact significance of shaded intervals is unobserved. Do not infer a universal hover state from the highlighted trace.

**Supplied palette (S; image extraction, not UI-role coverage):** `#18191B` (50%), `#1B1C1E` (25%), `#1D1F20` (12.5%), `#212223` (6.25%), `#27282A` (3.13%), `#4D4D4F` (3.13%).

### D12 — Dark mode/dark mode refrence 12.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Typography presentation page; large Helvetica Neue specimen, weight pills and tablet specimen.

**Observed anatomy (O):** The page explicitly names Helvetica Neue and labels Light, Regular and Medium. Thin large characters contrast with smaller regular/medium labels. A small glass note card appears next to the specimen. The tablet labels H1 at 128 px.

**Reusable rule and scope (P, informed by O):** Use the stated three-weight hierarchy as reference evidence: light for big numerals, regular for body and medium for selection. Size product headings by their role in D1/D5 rather than copying the specimen's 128 px.

**Confidence and exceptions:** High confidence in displayed names, not proof of installed font files or variable-font support. The rendered claim 'Variable Font' is reference copy, not verified font metadata. Oversized editorial typography is excluded from app sizing.

**Supplied palette (S; image extraction, not UI-role coverage):** `#080808` (50%), `#0D0C0C` (25%), `#151414` (12.5%), `#1E1E1E` (6.25%), `#B4B4B4` (3.13%), `#3B3B3A` (3.12%).

### D13 — Dark mode/dark mode refrence 13.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Branding montage: employee badge, business cards and clothing.

**Observed anatomy (O):** Dark printed objects carry the Vexto wordmark and diagonal-stroke symbol. Badge content mixes a bus photograph, address, person name and small portrait. A rounded editorial image grid arranges the objects.

**Reusable rule and scope (P, informed by O):** Only the subdued branding and compact mark/wordmark pairing are relevant. It establishes no app component, form, navigation or theme behavior.

**Confidence and exceptions:** High confidence in classification. Leather, cloth, metallic clip, paper, shadows and gray shirt are physical/presentation materials, not CSS colors or glass effects.

**Supplied palette (S; image extraction, not UI-role coverage):** `#111111` (50%), `#252524` (25%), `#3B3C3C` (12.5%), `#575757` (6.25%), `#999999` (3.13%), `#727272` (3.12%).

### D14 — Dark mode/dark mode refrence 14.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Case-study editorial page with large claim, portrait, small map and three process steps.

**Observed anatomy (O):** A near-black page holds gray large text with a white emphasized line, small amber terminal/rule marks, thin dotted dividers and capsule step labels. The bottom uses 01/02/03 in light weight.

**Reusable rule and scope (P, informed by O):** Keep the discipline of one emphasized fact and sparse accent use. These quotation/process components belong to case-study presentation, not the working survey workspace.

**Confidence and exceptions:** High confidence. Dollar loss and execution claims are unverified reference content. Do not copy the enormous editorial heading or infer a product onboarding flow.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0C0D0C` (50%), `#0D0D0C` (25%), `#0D0D0D` (12.5%), `#151515` (6.25%), `#828180` (3.13%), `#252322` (3.12%).

### D15 — Dark mode/dark mode refrence 15.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Warning-panel macro above editorial mobile-platform introduction.

**Observed anatomy (O):** The upper image repeats the muted-red incident, bright red count and gray secondary metadata. The lower section uses a thin divider, section numbering and a large white-highlighted phrase within gray copy.

**Reusable rule and scope (P, informed by O):** Use the warning-card styling already supported by D6/D10. Keep editorial introductions separate from product UI.

**Confidence and exceptions:** High confidence in repeated incident design; no new mobile layout is visible in this image. The 83% statement is marketing copy, not evidence of mobile behavior or usability.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0C0C0C` (25%), `#363936` (25%), `#221B1D` (12.5%), `#111416` (12.5%), `#0D0D0D` (12.5%), `#0E0C0C` (12.5%).

### D16 — Dark mode/dark mode refrence 16.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Typography/analytics case study with two explanatory rows, a glass note and comparison chart.

**Observed anatomy (O):** Thin rules organize editorial text; white and amber line segments create paired columns. A tall glass card places heading/body above a large percentage. The comparison chart uses white and amber annotations over faint traces.

**Reusable rule and scope (P, informed by O):** Reuse the top explanation/bottom metric anatomy only when one metric deserves a summary card. Preserve thin numerals with readable body text. Chart colors require explicit meanings.

**Confidence and exceptions:** High confidence in appearance. Claimed scanning-speed gains are not independently validated. The comparison's percentages and axis placement should not be copied as survey data.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0D0C0C` (50%), `#0D0D0D` (25%), `#272727` (12.5%), `#363936` (6.25%), `#7B7875` (3.13%), `#3B3E3F` (3.12%).

### D17 — Dark mode/dark mode refrence 17.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Map-callout showcase above a market chart and photograph with green transmitted glass.

**Observed anatomy (O):** The top repeats D9's selected marker and callout. Below, a green-lit passenger photograph visibly colors the floating card; its opaque white headline and large number sit over the transmitted image. A separate neutral chart uses white dots and shading.

**Reusable rule and scope (P, informed by O):** Strong evidence that glass coloration comes from its backdrop. Copy material behavior, not a universal green card fill. Use one foreground hierarchy consistently across varied imagery.

**Confidence and exceptions:** High confidence in transmission; medium in exact lighting mechanism. Poster statistics are not product evidence. Photograph green and terrain green are distinct content sources.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0D100F` (50%), `#28362A` (25%), `#34443E` (12.5%), `#4C5B44` (6.25%), `#929690` (3.13%), `#585F5A` (3.12%).

### D18 — Dark mode/dark mode refrence 18.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Editorial desktop-platform page with a small marker diagram and laptop/desktop dashboard image.

**Observed anatomy (O):** The product view repeats left metrics, vehicle grid, large map and lower schedule panel. Above it are huge gray/white editorial text, dotted rules and small amber details.

**Reusable rule and scope (P, informed by O):** Use the device view only to corroborate desktop information grouping. Keep editorial typography and surrounding negative space out of the application layout.

**Confidence and exceptions:** High confidence in classification and repeated composition. The 78% claim does not establish adoption or screen-size requirements. Device bezel/notch are presentation.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0B0B0C` (50%), `#0F1010` (25%), `#16191A` (12.5%), `#272A27` (6.25%), `#7F817E` (3.13%), `#3B4240` (3.12%).

### D19 — Dark mode/dark mode refrence 19.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Logo construction board and a simulated operating-system dock over map imagery.

**Observed anatomy (O):** Wordmark construction uses dashed guides and labeled clear-space ratios. The symbol appears at 100/50/25 px specimen sizes. A three-icon dock has a shared translucent rounded container; each icon sits in a dark rounded square.

**Reusable rule and scope (P, informed by O):** Brand clear space is separate from control padding. A grouped floating tray can inform navigation grouping, but OS app icons should not be copied into product controls.

**Confidence and exceptions:** High confidence in displayed construction labels. These are supplied specimen labels, not our pixel measurements. The map is media; the dock is OS/presentation context, not confirmed Vexto app navigation.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0F0F0F` (25%), `#0C0C0C` (25%), `#151616` (25%), `#181919` (12.5%), `#2C3836` (6.25%), `#646867` (6.25%).

### D20 — Dark mode/dark mode refrence 20.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Telemetry case-study section showing online/offline mini-cards, vehicle variants and photo overlay.

**Observed anatomy (O):** Online/offline counters use green check/red warning symbols. Repair and online vehicle cards share anatomy but change status label, connectivity and mini-map content. The selected photographic overlay is much more luminous than unselected cards.

**Reusable rule and scope (P, informed by O):** Preserve stable component anatomy across data states. Couple status color with a word and distinct symbol; swap meaningful content such as repair/no-signal rather than only tinting the card.

**Confidence and exceptions:** High confidence in visible variants. No loading, focus or disabled state is shown. Claimed -58.5% effect and chart data are presentation copy.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0C0C0B` (50%), `#0E0E0D` (25%), `#141414` (12.5%), `#2E3424` (6.25%), `#879486` (3.13%), `#535E46` (3.12%).

### D21 — Dark mode/dark mode refrence 21.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Market-value case study: paired charts, map-backed glass metric, bus-backed glass graph.

**Observed anatomy (O):** The same glass surface transmits cool lake, green terrain or broad white bus reflections depending on the background. Large numeric values dominate card interiors; supporting text sits above, while a chart uses a low-contrast data field.

**Reusable rule and scope (P, informed by O):** Use background-responsive optical variation without changing the semantic base fill on every card. Keep white reflections localized. Separate media coverage from chrome coverage when matching appearance.

**Confidence and exceptions:** High confidence in material comparison. Financial/market claims are not facts verified by this audit. Strong blue corner glints are isolated showcases, not mandatory on every control.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0D0D0E` (50%), `#1A1C1C` (25%), `#2F3535` (12.5%), `#5A5E59` (6.25%), `#B9BCBD` (3.13%), `#929697` (3.12%).

### D22 — Dark mode/dark mode refrence 22.jpg

**Source dimensions (M):** 3000 × 3750 px. **Visible region/classification:** Promotional poster: passenger photograph, single green glass telemetry card, huge save-design CTA.

**Observed anatomy (O):** The card is the D8 anatomy rendered over green/yellow-lit photography. Its rim is more pronounced and internal colors stronger than everyday dashboard cards. Giant bold lettering belongs to the promotional call to action.

**Reusable rule and scope (P, informed by O):** Useful exception showing how strongly a background can color glass. Use as a material stress case, while retaining the calmer D1/D8 baseline.

**Confidence and exceptions:** High confidence. Photograph greens and huge white poster lettering distort the palette distribution. The poster CTA is not survey navigation, and the heavy type is not evidence for app headings.

**Supplied palette (S; image extraction, not UI-role coverage):** `#060C07` (50%), `#20331C` (25%), `#315A3A` (12.5%), `#FEFEFF` (6.25%), `#C8D3CC` (3.13%), `#5F6F45` (3.12%).

### D23 — Dark mode/dark mode refrence 23.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Mobile fleet-efficiency product inside a phone plus a magnified bottom navigation crop.

**Observed anatomy (O):** The mobile UI stacks efficiency chart, paired online/offline blocks and vehicle content. A floating rounded bottom tray contains several glyphs; a bright circular selection encloses a dark grid icon. A top vehicle selector and bell compress desktop utilities.

**Reusable rule and scope (P, informed by O):** For a future mobile layout, prioritize a single vertical information flow and compact floating navigation. Preserve selection through both fill and glyph contrast.

**Confidence and exceptions:** High confidence in composition and selected navigation. Phone frame/system bar are excluded. No evidence that desktop panels should simply shrink proportionally; responsive dimensions remain proposed.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0C0C0C` (50%), `#777D79` (12.5%), `#444948` (12.5%), `#151515` (12.5%), `#252726` (6.25%), `#353836` (6.25%).

### D24 — Dark mode/dark mode refrence 24.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Editorial roadmap: large quotation, portrait, transport line drawing, timeline and thumbnail cards.

**Observed anatomy (O):** A thin ruler-like line joins circular milestones with bus glyphs and dotted vertical connectors. An amber current-position capsule appears above. Rounded thumbnails have overlapping text pills.

**Reusable rule and scope (P, informed by O):** The timeline's tick/endpoint anatomy can inspire a survey-history strip only if time steps are meaningful. Thumbnail-plus-label overlays are reusable media anatomy.

**Confidence and exceptions:** High confidence in appearance. This is project storytelling, not route geometry or evidence of a scheduling component in the survey product. All roadmap claims remain unverified.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0C0C0C` (50%), `#0D0D0D` (25%), `#111111` (12.5%), `#181818` (6.25%), `#959391` (3.13%), `#282726` (3.12%).

### D25 — Dark mode/dark mode refrence 25.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** AI-analysis case-study page with warning crops, portrait testimonial and before/after chart.

**Observed anatomy (O):** The warning card is shown both close-up and in situ over terrain. Its outer glass picks up terrain while nested incidents maintain a muted red fill. The comparison card groups a large percentage, supporting line and neutral/amber chart annotations.

**Reusable rule and scope (P, informed by O):** Maintain the contrast distinction between the outer optical container and nested semantic alert fill. Give warnings a structure that can be scanned without reading an entire chart.

**Confidence and exceptions:** High confidence in visible nesting. AI accuracy/testimonial claims are reference copy. No prediction interaction or explainability flow is demonstrated.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0D0D0E` (50%), `#221A1C` (12.5%), `#242525` (12.5%), `#161718` (12.5%), `#3A3E39` (6.25%), `#68645D` (6.25%).

### D26 — Dark mode/dark mode refrence 26.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Tablet held in a hand showing the desktop-style traffic workspace.

**Observed anatomy (O):** The tablet still presents left telemetry plus a broad map and lower metrics. The selected vehicle card is more reflective than the surrounding dark cards, and the map callout floats separately.

**Reusable rule and scope (P, informed by O):** Corroborates reuse of the same components on a larger touch screen. Keep typography and controls legible at actual display size; do not infer exact breakpoints from a tilted device photograph.

**Confidence and exceptions:** High confidence in visible layout, low in intended viewport scale. Hand, bezel, gray surroundings and perspective are excluded from component extraction.

**Supplied palette (S; image extraction, not UI-role coverage):** `#111213` (50%), `#949494` (25%), `#252523` (12.5%), `#393E39` (6.25%), `#797774` (3.13%), `#515750` (3.12%).

### D27 — Dark mode/dark mode refrence 27.jpg

**Source dimensions (M):** 3200 × 4000 px. **Visible region/classification:** Editorial UX case study with mini-map/route fragment, selector capsules, portrait and comparison chart.

**Observed anatomy (O):** Two compact icon-plus-label capsules echo the desktop map selectors. The route illustration has a pin, direction wedge and angular path. The chart uses white/amber horizontal comparisons and subdued background traces.

**Reusable rule and scope (P, informed by O):** Selectors can transfer as icon + label + optional chevron. Reuse chart hierarchy only with coherent survey units. Separate a direction marker, route and timeline rather than treating them as decoration.

**Confidence and exceptions:** High confidence in visible components. The 82%/61% claims are unverified. This page cannot establish real geography or a validated UX performance result.

**Supplied palette (S; image extraction, not UI-role coverage):** `#0C0C0C` (50%), `#0D0D0C` (25%), `#151515` (12.5%), `#191918` (6.25%), `#6E6B67` (3.13%), `#1A1A1A` (3.12%).

### L1 — Light mode/reference ui image 1.png

**Source dimensions (M):** 1434 × 924 px. **Visible region/classification:** Travel application overview, flat screen image: navigation rail, destination hero, assistant and lower metrics/map.

**Observed anatomy (O):** A slim gray rail uses dark outline icons and a yellow brand circle. Top tab chrome sits above a large travel photograph. White destination text overlays media; a translucent segmented navigation sits near its bottom. A yellow assistant card overlaps the hero and lower grid. Below are temperature, budget and crowd indicators, then a pale map with controls and green markers.

**Reusable rule and scope (P, informed by O):** Keep this family distinct. Its useful principles are dark text on pale non-media surfaces, readable media overlays and intentional overlap. The yellow assistant and green charts are product-specific and are not inherited by the blue-glass survey theme.

**Confidence and exceptions:** High confidence in composition and visible typography. The small hero paragraph is faint. The dominant blue is mostly sky/media, not an interaction color. Only the flat screen dimensions are directly measurable; font identity is not supplied.

**Supplied palette (S; image extraction, not UI-role coverage):** `#A3B4B5` (25%), `#E7E8C2` (25%), `#ECECEC` (25%), `#52696E` (12.5%), `#8C9797` (6.25%), `#679095` (6.25%).

### L2 — Light mode/reference ui image 2.png

**Source dimensions (M):** 1434 × 924 px. **Visible region/classification:** Same travel application, Hotels tab, destination hero, assistant and photographic result cards.

**Observed anatomy (O):** Hotels is selected within the same translucent tab strip. A three-column card row emphasizes photography; bottom image overlays hold white names, yellow ratings and small locations. Each card has a dark category disk and an expand control. The assistant text is visibly incomplete.

**Reusable rule and scope (P, informed by O):** Use only media-card anatomy where useful: full image, protected caption area, small corner controls. This and L1 show real tab-state variation; they do not provide dark-theme evidence.

**Confidence and exceptions:** High confidence in repeated shell and selected tab. The partial assistant sentence may reflect a captured transient state; do not treat it as intended copy or proof of a loading animation.

**Supplied palette (S; image extraction, not UI-role coverage):** `#86A2AF` (25%), `#E0E0E1` (25%), `#D8D8AE` (25%), `#7B9094` (12.5%), `#3A5054` (6.25%), `#6B7777` (6.25%).

### L3 — Light mode/reference ui image 3.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Dentale desktop viewport on a monitor; left orientation widget, central dental render and floating toolbars.

**Observed anatomy (O):** A large translucent pink/red anatomical render occupies the central canvas. The blue workspace carries white text. The left has case title, concentric axis control and a rounded scan preview. Small rounded-square tool buttons float above and beside the model. A long translucent timeline lies below a separate tool dock.

**Reusable rule and scope (P, informed by O):** Transfer the spatial-workspace relationship: dominant inspectable content, peripheral controls, floating secondary preview and a distinct bottom tray. Keep red anatomy as rendered content, not danger-colored application chrome.

**Confidence and exceptions:** High confidence in layout/material; medium in exact icon meanings. Monitor and gray room are presentation. Axes are model coordinates, not navigation paths. Light theme text contrast needs correction rather than copying.

**Supplied palette (S; image extraction, not UI-role coverage):** `#A3A9B7` (25%), `#D8D8D8` (25%), `#875B61` (12.5%), `#1E1D1C` (12.5%), `#DB7381` (12.5%), `#DAC8CF` (12.5%).

### L4 — Light mode/reference ui image 4.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Promotional blue poster with a large treatment-instruction glass card.

**Observed anatomy (O):** The card has a title and close control, Start row, numbered translucent steps, emphasized tooth references and Retainer row. A slim vertical rail with a pill thumb sits at the right. Blue backdrop structure shows through the card. White promotional heading and giant save-design lettering surround it.

**Reusable rule and scope (P, informed by O):** Reuse the ordered instruction anatomy as a possible observation checklist: row marker → action → secondary detail, inside a rounded panel. Keep the rail separate from the step content.

**Confidence and exceptions:** High confidence in visible anatomy; medium in whether the rail denotes scroll or progress. The blue blurred backdrop and promotional type are not a complete application layout. Clinical copy is reference content, not instructions to this assistant.

**Supplied palette (S; image extraction, not UI-role coverage):** `#49708D` (25%), `#739AB8` (25%), `#1F4663` (25%), `#91B9D7` (12.5%), `#B7D4EA` (6.25%), `#FFFEFE` (6.25%).

### L5 — Light mode/reference ui image 5.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Mobile chat screen held in a hand.

**Observed anatomy (O):** Top back/title/avatar navigation is followed by a rounded case summary with cyan Active badge. Sender portraits and names anchor unbubbled messages. File and scan cards sit alongside message text. Rounded action buttons form local groups; a pill composer plus separate add/send controls sits at the bottom.

**Reusable rule and scope (P, informed by O):** Reuse message → attachment → action grouping only if notes later become collaboration. For this mockup, retain a clearly labeled note surface. The composer shows a real input-like anatomy without proving its interaction states.

**Confidence and exceptions:** High confidence in visible layout, low in focus/error behavior. White small text on pale blue is weak and should not transfer. Skin, phone frame and status-bar shapes are excluded.

**Supplied palette (S; image extraction, not UI-role coverage):** `#B7C6CF` (25%), `#D5D5D9` (25%), `#DEE1E6` (25%), `#9FB2BF` (12.5%), `#616266` (6.25%), `#0A0605` (6.25%).

### L6 — Light mode/reference ui image 6.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Mobile case-summary and treatment instructions on a tilted phone.

**Observed anatomy (O):** A rounded glass overview card groups a progress badge, compact bold values, lighter captions and a fine tooth diagram. Below, the instruction sequence uses numbered rows and a vertical rail. A small floating three-action bottom tray sits above the phone edge.

**Reusable rule and scope (P, informed by O):** Use stronger numbers with lighter captions where figures are small, and keep summary above detailed procedure content. Nest internal content without repeatedly drawing heavy borders.

**Confidence and exceptions:** High confidence in summary/instruction hierarchy. Hands obscure content; exact bottom padding and touch sizes cannot be inferred. White-on-pale-blue body contrast remains an intentional exception to correct.

**Supplied palette (S; image extraction, not UI-role coverage):** `#DADFE4` (50%), `#19110E` (25%), `#ABC0CC` (12.5%), `#98B1C0` (6.25%), `#433935` (3.12%), `#7C8287` (3.12%).

### L7 — Light mode/reference ui image 7.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Isolated blue-glass TX Overview card on a blurred blue backdrop.

**Observed anatomy (O):** A broad rounded rectangle transmits large bright and dark blue background shapes. A very thin lit boundary defines it. Three compact, heavier values sit over lighter captions; lower left percentage rows use horizontal rules, while upper/lower tooth diagrams occupy the right.

**Reusable rule and scope (P, informed by O):** Principal transmission reference: the glass does not have a uniform blue fill. Separate text into an opaque foreground layer over a soft, spatially varied background. For the survey use analogous grouped readings and compact technical content.

**Confidence and exceptions:** High confidence in optical behavior. The dark blue patch belongs to transmitted background, not a dark-theme pairing. Exact blur, alpha and refraction cannot be recovered from the image.

**Supplied palette (S; image extraction, not UI-role coverage):** `#5C93B3` (25%), `#2D4252` (25%), `#3E647D` (25%), `#7CA2BC` (12.5%), `#B0C5D8` (6.25%), `#9BB7CD` (6.25%).

### L8 — Light mode/reference ui image 8.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Mobile 3D inspection screen, anatomy filling the viewport.

**Observed anatomy (O):** The case title sits over a red model. Fine point annotations and numbered dark circular labels attach to geometry with leader lines. A vertical rounded tool tray sits at right; a separate horizontal tool tray and timeline sit at bottom. Selected hand control has an inset bright rim.

**Reusable rule and scope (P, informed by O):** Reuse peripheral floating controls and anchor annotations to actual content. Keep tools grouped by task rather than distributing unrelated controls around the canvas.

**Confidence and exceptions:** High confidence in tool grouping, medium in exact semantics. Anatomical red is media, not error state. The hand and device frame are presentation. No theme toggle is shown.

**Supplied palette (S; image extraction, not UI-role coverage):** `#DEE1E6` (25%), `#B6A6AF` (25%), `#DEBCC5` (25%), `#0B0604` (12.5%), `#2A1E18` (6.25%), `#9D444A` (6.25%).

### L9 — Light mode/reference ui image 9.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Closeup of pale case-instruction typography and vertical rail.

**Observed anatomy (O):** Title and body text are very light on pale blue; some numeric/action content is heavier. A rounded thumb with opposing arrows sits on a thin track with small cyan/pink marks. The upper summary card has a soft inner edge.

**Reusable rule and scope (P, informed by O):** Borrow the rail/thumb anatomy and spacing between heading, stage and detail. Use dark text for the survey adaptation; the weak source contrast is directly visible.

**Confidence and exceptions:** High confidence in visual hierarchy, medium in control meaning. The black palette swatch could include the device edge and is not evidence that the original uses dark body text. Dark text is a new role assignment requested by the user.

**Supplied palette (S; image extraction, not UI-role coverage):** `#B4C7D2` (50%), `#A3BAC7` (25%), `#96B0BF` (12.5%), `#91ACBC` (6.25%), `#222323` (3.12%), `#728088` (3.12%).

### L10 — Light mode/reference ui image 10.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Isolated Front Scan media card with three external action buttons.

**Observed anatomy (O):** The anatomical image fills a rounded glass card and remains visible behind its heading. A dashed rounded selection window frames the region of interest. A 5/10 indicator and thin cyan progress segment occupy the bottom. Three rounded-square controls sit beneath, with camera selected by a brighter rim.

**Reusable rule and scope (P, informed by O):** Strong media-component anatomy: label/control corner → image with optional region overlay → progress footer; local actions belong outside the image. The survey inspector borrows the framing and inset control material, with survey imagery.

**Confidence and exceptions:** High confidence in structure and selection appearance. The background blush comes from content/presentation, not a required panel accent. A dashed selection window should appear only when a real selection exists.

**Supplied palette (S; image extraction, not UI-role coverage):** `#99AFC4` (50%), `#9493AE` (12.5%), `#979DB9` (12.5%), `#AB7684` (12.5%), `#8C5554` (6.25%), `#947384` (6.25%).

### L11 — Light mode/reference ui image 11.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Mobile lower-tooltray and timeline macro.

**Observed anatomy (O):** A hand glyph sits inside a bright inset rounded control within a darker translucent tray. Thin vertical separators divide groups. A separate timeline carries cyan/pink segments, fine ticks, stage numbers and triangular markers.

**Reusable rule and scope (P, informed by O):** Use a shared tray with selected child and separators where controls form meaningful groups. Keep a temporal timeline visually distinct from the tool selection tray.

**Confidence and exceptions:** High confidence in grouping, medium in timeline event meanings. Perspective stretching does not imply elliptical button geometry. Pixel-like glyph strokes are this family's icon styling, not universal line icons.

**Supplied palette (S; image extraction, not UI-role coverage):** `#161616` (25%), `#9994A1` (25%), `#A7656D` (12.5%), `#7A5055` (12.5%), `#AC98A4` (12.5%), `#C5C2C9` (12.5%).

### L12 — Light mode/reference ui image 12.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Macro of model annotations and two tool trays.

**Observed anatomy (O):** Small cyan rectangles and pink triangles sit on the rendered teeth. Thin light leaders connect points to dark circular numeric labels (.35/.38). A vertical frosted tool group and a horizontal bottom tool group have brighter selected children.

**Reusable rule and scope (P, informed by O):** Labels should stay spatially attached to their measured object; point anchors, leader lines and label bubbles form one component. If applied to survey readings, leaders need meaningful coordinates, not decorative curves.

**Confidence and exceptions:** High confidence in visible attachment; low in measurement units and meanings. The pink and cyan elements are data marks in a clinical model, not global status or primary-action colors.

**Supplied palette (S; image extraction, not UI-role coverage):** `#CAAFBA` (25%), `#CA6168` (25%), `#9B8A96` (25%), `#974A4E` (12.5%), `#252424` (6.25%), `#6A3534` (6.25%).

### L13 — Light mode/reference ui image 13.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Tablet upper-left detail showing brand/title, axis control and scan preview.

**Observed anatomy (O):** The case title is much larger than nearby controls. An orientation widget has an outer tick ring, axis labels, translucent central disk, directional glyphs and a small brighter center button. A scan card sits below with its own local controls.

**Reusable rule and scope (P, informed by O):** Reuse the visual nesting and inset highlight for spatial controls when relevant. Preserve title → control → secondary preview hierarchy without importing a full three-axis widget into a simple map.

**Confidence and exceptions:** High confidence in nesting; medium in exact control actions. Device perspective changes apparent circles and alignment. The Dentale brand mark is not part of the survey application's identity.

**Supplied palette (S; image extraction, not UI-role coverage):** `#A6B6C5` (25%), `#D8D8D9` (25%), `#E0A9B1` (25%), `#B5808E` (12.5%), `#21191A` (6.25%), `#9199A7` (6.25%).

### L14 — Light mode/reference ui image 14.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Closeup of the pale TX Overview summary card.

**Observed anatomy (O):** A thick soft frosted edge surrounds a pale blue-gray center. The title is regular/light, summary values noticeably heavier, captions light, percentage rules fine and technical diagram lines delicate. The card floats above another pale layer.

**Reusable rule and scope (P, informed by O):** Primary pale-material reference for the revision. Use a curved frosted rim, calm interior and restrained nesting. Keep value/caption distinction but deliberately replace pale foreground text with dark ink.

**Confidence and exceptions:** High confidence in appearance. The sampled empty card region is #C3CDD7, which is a flattened raster value, not an original fill token. White-on-pale text should not be treated as an accessibility precedent.

**Supplied palette (S; image extraction, not UI-role coverage):** `#B0BFCC` (50%), `#C1CCD6` (25%), `#C8D1DB` (12.5%), `#CBD4DD` (6.25%), `#E2E7ED` (3.13%), `#CCD5DE` (3.12%).

### L15 — Light mode/reference ui image 15.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Chat macro with sender names, attachment tile and action buttons.

**Observed anatomy (O):** Sender names use stronger weight than message text. Portraits sit on the same visual baseline as names. The file attachment is a rounded tile with a large document illustration and small label. A row of three muted rounded-square buttons belongs to the message below/above it.

**Reusable rule and scope (P, informed by O):** Copy alignment and the separation between message content and its actions if a collaboration component is later needed. For the survey note, keep a readable label, body and clearly distinct action.

**Confidence and exceptions:** High confidence in hierarchy, lower in tiny blurred metadata. PDF illustration is content, not an icon standard. White text contrast and simulated camera blur are not reusable requirements.

**Supplied palette (S; image extraction, not UI-role coverage):** `#B3C5D0` (50%), `#A7B6C3` (25%), `#9BB3C1` (12.5%), `#8FA3B0` (6.25%), `#2A2B2C` (3.12%), `#50494A` (3.12%).

### L16 — Light mode/reference ui image 16.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Macro of Front Scan card edge and vertically stacked local controls.

**Observed anatomy (O):** One selected rounded-square camera control has a softly bright perimeter and darker center; its unselected neighbors are flatter and dimmer. A thin gap separates each control. The card edge shows a thick softened highlight, while anatomy remains visible through the surface.

**Reusable rule and scope (P, informed by O):** Principal control-material reference: selection changes the perimeter and inner shading, not just the glyph color. Use consistent thin survey glyphs inside that inset geometry.

**Confidence and exceptions:** High confidence in selection/material. The selected state is observed; hover, pressed, disabled and keyboard focus are not. The reference's segmented/pixel glyph treatment belongs to Dentale and is deliberately not mixed into Vexto line icons.

**Supplied palette (S; image extraction, not UI-role coverage):** `#B6C3CF` (50%), `#9CAFC0` (12.5%), `#C3717D` (12.5%), `#ADADBD` (12.5%), `#989EAC` (6.25%), `#723842` (6.25%).

### L17 — Light mode/reference ui image 17.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Promotional TX Overview poster, repeating the isolated card from L7.

**Observed anatomy (O):** The same transmitted blue-glass overview is framed by a social handle, large white introduction, save-design lettering and a glass bookmark disk. The card's bright/dark patches follow the backdrop.

**Reusable rule and scope (P, informed by O):** Corroborates L7's optical behavior. Treat it as a promotional re-presentation of the same component rather than additional evidence for a new theme or layout.

**Confidence and exceptions:** High confidence in duplication of component concept. Poster text and bookmark are promotional chrome, not product navigation; their large white coverage should not set app color distribution.

**Supplied palette (S; image extraction, not UI-role coverage):** `#446F89` (25%), `#2E4254` (25%), `#E0E8F0` (12.5%), `#94B1C8` (12.5%), `#648FAB` (12.5%), `#689FC0` (12.5%).

### L18 — Light mode/reference ui image 18.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Macro of top utility row and model-editing tools over pink anatomical content.

**Observed anatomy (O):** A small upper utility cluster is separated spatially from a larger editing row. Buttons are rounded squares. The selected first tool has a luminous inset contour; neighboring fills tint with the pink background. Icons are white, often built from segmented strokes.

**Reusable rule and scope (P, informed by O):** Copy control grouping and selected-vs-idle material differentiation. Keep global actions distinct from local editing tools. Use one icon family per product.

**Confidence and exceptions:** High confidence in material and grouping, medium in meanings of specialized glyphs. Pink is transmitted model color, not button branding. No tooltip or label-reveal behavior is shown.

**Supplied palette (S; image extraction, not UI-role coverage):** `#D27389` (25%), `#F37B95` (25%), `#F79CB5` (25%), `#B54E63` (12.5%), `#9A4D5B` (6.25%), `#191314` (6.25%).

### L19 — Light mode/reference ui image 19.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Isolated orientation widget over a blurred pink anatomical backdrop.

**Observed anatomy (O):** Concentric translucent disks have different edge highlights and depths. A small central rounded-square plus is surrounded by directional arrows. Outer ticks and X/Y/Z labels sit on a larger ring with one cyan highlighted tick.

**Reusable rule and scope (P, informed by O):** Useful component anatomy for 3D orientation: outer reference scale → middle directional plane → center action. For this survey retain the simpler locate/zoom controls; a full axis dial would add unsupported complexity.

**Confidence and exceptions:** High confidence in visible layers; low in exact coordinate values or behavior. Pink/brown come from the background and glass transmission. It does not establish a separate pink theme.

**Supplied palette (S; image extraction, not UI-role coverage):** `#C893A1` (25%), `#4B2C32` (25%), `#8B444F` (12.5%), `#5F383F` (12.5%), `#AD7481` (12.5%), `#C88F9C` (12.5%).

### L20 — Light mode/reference ui image 20.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Front Scan closeup focusing on lower image, footer and adjacent selected camera control.

**Observed anatomy (O):** A dashed rounded region frame sits within the anatomical image. The footer uses larger numerator, smaller denominator and thin cyan progress segment. The action column is outside the card. The larger application timeline is a separate layer below.

**Reusable rule and scope (P, informed by O):** Keep media progress, media actions and global timeline separate. Reuse the larger numerator/smaller unit pattern for survey reading/value pairs, with coherent labels.

**Confidence and exceptions:** High confidence in separation and composition. Exact footer padding is distorted by perspective. Anatomy colors and scan framing do not transfer as survey data or safety status.

**Supplied palette (S; image extraction, not UI-role coverage):** `#B2BFCB` (50%), `#CE727F` (12.5%), `#909EAF` (12.5%), `#B1A7B6` (12.5%), `#988390` (6.25%), `#8C444D` (6.25%).

### L21 — Light mode/reference ui image 21.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Closeup of selected AI Highlight capsule and timeline beneath it.

**Observed anatomy (O):** A selected capsule uses a bright curved edge, soft center shading, cyan dot and white label. A separator divides it from an adjacent icon. Beneath, a pointer aligns to colored timeline intervals and fine numbered ticks.

**Reusable rule and scope (P, informed by O):** The reusable mode selector is dot/icon + label inside a selected inset capsule, separated from neighboring tools. Dot meaning must be explained by its label rather than assumed.

**Confidence and exceptions:** High confidence in selected mode appearance. This is a mode selection, not proof of a binary toggle or hover state. AI label and timeline values are product-specific; low-contrast white text is corrected in the survey theme.

**Supplied palette (S; image extraction, not UI-role coverage):** `#978693` (50%), `#9CA2B2` (25%), `#A7A4B2` (12.5%), `#ACAAB7` (6.25%), `#CDC9D0` (3.13%), `#BBB0BA` (3.12%).

### L22 — Light mode/reference ui image 22.jpg

**Source dimensions (M):** 3072 × 4096 px. **Visible region/classification:** Widest Dentale workspace view on a laptop/display with some foreground hardware obscuring the bottom.

**Observed anatomy (O):** The central model dominates. Left title, orientation and scan card balance a right instructions panel and compact overview. Floating global/local tool rows surround the model, with a long bottom timeline. Patient identity occupies the upper right.

**Reusable rule and scope (P, informed by O):** Strongest light-family composition evidence: one continuous spatial canvas with peripheral inspectors, local tool clusters and secondary media. Use its surface relationships, while preserving the original survey arrangement already preferred by the user.

**Confidence and exceptions:** High confidence in overall hierarchy; medium in tiny text. Black device/foreground hardware and gray wall account for substantial palette colors. No dark counterpart, focus behavior or exact responsive breakpoint is established.

**Supplied palette (S; image extraction, not UI-role coverage):** `#D8D8D8` (25%), `#CB9DAA` (25%), `#A2B2C2` (12.5%), `#8C858E` (12.5%), `#040404` (12.5%), `#2E2324` (12.5%).
