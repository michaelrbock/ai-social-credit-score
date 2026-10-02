# AI Social Credit Score landing page

This is a static developer-tool landing page for the personal AI Social Credit
Score plugin. Edit `dist/index.html`, `dist/styles.css`, and `dist/app.js`
directly. It includes installation instructions, a five-command explorer,
scoring/privacy details, and setup FAQs.

The local UI JavaScript switches between illustrative command examples and copies
commands to the clipboard. The page uses Fathom Analytics for website pageviews;
no plugin prompts, scores, or rationales are sent to Fathom. All demo scores and
output are illustrative, not real user history.
Command tabs support arrow keys, Home, and End; FAQs use native disclosure controls.

Preview with `python3 -m http.server 8000 --directory dist` from this directory.
There is no package installation or build step. The `dist/` directory can be
served by a static web host.

## Social preview

The homepage includes Open Graph and X large-image card metadata, with absolute
URLs and a canonical URL on `https://aisocialcreditscore.com/`. Its checked-in
`dist/social-preview.png` is 1200 × 630 pixels. The score shown is illustrative.

To edit the card, change `design/social-preview.html` and run
`node website/scripts/render-social-preview.cjs` from the repository root with
Playwright available to Node. The renderer uses Playwright's Chromium by default;
set `CHROMIUM_EXECUTABLE_PATH` to use an installed Chrome/Chromium executable.
This is an optional authoring tool, not a website build dependency. Commit the
regenerated PNG alongside any source changes. Run the metadata checks with
`python3 -m unittest discover -s tests -p 'test_website_metadata.py'`.
