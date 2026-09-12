# Assets and source continuity

- `public/assets/earth-september.jpg`: NASA Earth Observatory, Blue Marble Next Generation, September 2004, topography and bathymetry. [Source page](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-topography-bathymetry/), [original 5400×2700 JPEG](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-topography-bathymetry/september/world.topo.bathy.200409.3x5400x2700.jpg). Downloaded once on 12 September 2026. SHA-256 `4c6723e79dc7c1bdb8c193cdf8f946b10b9407bc9fd1164cdf5e75d0aa79ad3b`. Shipped locally; no runtime image request to NASA. This is illustrative surface imagery, not current weather or a precise ground-track overlay.
- `src/scene/satellite.ts`: original procedural spacecraft, solar cells, antenna, instrument and thruster geometry. Illustrative, enlarged, and not a claimed engineering replica of NOAA 20. No Blender or unlicensed GLB required.
- Inter 300/400/500: local font files bundled by `@fontsource/inter`. OFL notice copied from the supplied reference project to `public/licenses/Inter-OFL.txt`.
- Phosphor icons: `@phosphor-icons/react`, MIT. Supplied MIT notice preserved in `public/licenses/Phosphor-MIT.txt`.
- Three.js: MIT, notice preserved in `public/licenses/Three-MIT.txt`.

The user-supplied `design.md`, approved dark/light v2 images and active glass.css informed typography, material, corner hierarchy and layout. The supplied design and exact token ledger are preserved under `Handoff/design`. The reference's fictional terrain and legacy travel photos are not appropriate satellite data; they are not included in the product. The reference branding and screenshots are not runtime UI.
