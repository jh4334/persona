# Pixel Asset Redesign QA

## Target

- Direction: warm refined 16-bit palette, stronger top-down 3/4 furniture depth, readable chibi characters, modular character/furniture separation.
- Contract: `docs/asset_request.md`
- Asset preview: `docs/pixel-assets-preview.png`
- Integrated classroom preview: `docs/pixel-assets-classroom-preview.png`

## Runtime check

- Browser surface: actual `src/classroom_sim/web/static/index.html` and `app.js`
- QA state: 12 students, 4 columns × 3 rows, all eight emote slots, three gauges per student
- Observed: all students render without overlap or clipping; clicking the first student selects `s01` and opens the matching detail card.

## Visual checklist

| Check | Result |
|---|---|
| Warm shared palette and pure nearest-neighbor pixels | PASS |
| 3/4 blackboard and furniture depth | PASS |
| Distinct, readable faces and silhouettes | PASS |
| Character sheets contain no embedded desk/chair pixels | PASS |
| Two 32×48 idle frames per 64×48 character sheet | PASS |
| Student names, gauges, and emotes remain separated | PASS |
| All 12 students fit the classroom viewport | PASS |
| Transparent checkerboard preview has no clipped assets | PASS |

## Independent review

- Functional/design-system review: PASS
- Visual-fidelity review: PASS after enlarging student names and replacing the full-app screenshot with a focused classroom-canvas preview.

Final verdict: PASS.
