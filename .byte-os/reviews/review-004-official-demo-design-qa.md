# Review 004 — Official Demo Historical Backtest Design QA

Result: passed

## Scope

- Live deployed `历史回测` page at `http://127.0.0.1:8765/#/backtest`.
- Desktop viewport 1440 × 1000 and mobile viewport 390 × 844.
- Top3/product-boundary copy, comparison table, sealed metrics, chart, Chinese
  deviation disclosure, responsive navigation and console state.

## Evidence

- Desktop screenshot:
  `/Users/elan/.codex/visualizations/2026/08/12/019ff422-4bd0-7ce3-bca1-69874fefaae4/elanquant-final-qa/backtest-desktop-1440-final.png`
- Mobile screenshot:
  `/Users/elan/.codex/visualizations/2026/08/12/019ff422-4bd0-7ce3-bca1-69874fefaae4/elanquant-final-qa/backtest-mobile-390-top.png`
- Both viewports had `documentElement.scrollWidth === window.innerWidth` and
  no browser console warning or error.
- The mobile heading and description were reworked to wrap at 390 px after an
  initial visual review found clipping.
- The page displays the sealed mean-signal result (7.03%), benchmark (16.30%),
  excess (-9.27%) and 233-session support without calling the curve NAV.
- The page explicitly retains Top3 and states that the historical version does
  not share orders, positions, NAV or strategy names with it.

## Verification

- Frontend Vitest: 12/12 passed.
- ESLint: passed with zero warnings.
- TypeScript/Vite production build: passed.
- npm production audit: zero vulnerabilities.

