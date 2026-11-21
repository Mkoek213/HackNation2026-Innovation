# Investigation: access to the PCI brief data sources

Date: 2026-11-21. The original investigation used Podkarpackie. Refresh now accepts
all Polish voivodeships by default and supports `--region` for pilots.

## Findings

| Source | Access | Podkarpacie filter | Decision |
| --- | --- | --- | --- |
| Interreg 2021-2027 project list (interreg.gov.pl) | Official XLSX (art. 49 CPR), no key | Lead partner voivodeship column | Used: `backend/scripts/import_interreg.py`, 36 of 258 projects |
| RAD-on / POL-on open data (radon.nauka.gov.pl) | Public JSON API, no key, token pagination | Institution `voivodeship`, then projects by `entityShowingAchievementsUuid` | Used: `backend/scripts/import_radon.py`, 200 newest of 390 eligible projects from 13 institutions |
| Interreg, NCBR successes, pcinn.org pages | Static HTML | Not needed | Used live by the chat (`discover_sources`, `read_source`) |
| UPRP e-wyszukiwarka | SPA behind Incapsula bot protection | - | Not used: automated access is blocked |
| EPO register / OPS | Register returns 403; OPS needs a registered consumer key | Applicant address | Not used yet: needs a free OPS key |
| PBN API | Returns 403 without a token | Affiliation | Not used yet: needs an API token |
| PPM, BazTOL | Repositories of Poznań institutions | Not regional | Not used: no Podkarpacie content |
| dLibra (czasopisma.pan.pl) | JS-only landing page | Affiliation in metadata | Not investigated further |

RAD-on has no patent endpoint (`/polon/patents` and similar return 404); its project endpoint ignores most filters except `entityShowingAchievementsUuid`.
The RAD-on institutions endpoint ignores the `voivodeship` parameter, so the importer filters the 841 institutions client-side (16 active in Podkarpacie, church universities excluded).

## Data handling

- Records keep `source_name`, `source_url` and `imported_at`, so every card names its source.
- RAD-on project managers are public data and are stored as `authors` with their affiliation; Interreg partners are institutions only.
- Sector, innovation type and institution type are assigned by transparent keyword rules in `backend/scripts/import_common.py`; the rules over-assign "Jakość życia" and admins correct labels in the Dokumenty panel.
- Interreg NEXT Poland-Ukraine records are published in English only, so their cards are English.

## Limitations

- No patents in the base yet; adding EPO OPS (free key) is the most valuable next source.
- The examined registries have limited school and local administration coverage. The public deployment-report adapter currently verifies three selected cases.
- RAD-on abstracts describe research projects, not proven innovations; maturity is left unset for them.

## Deployment evidence

| Area | Case and official source | Evidence scope |
| --- | --- | --- |
| Administration | [ePłatności](https://www.gov.pl/web/cyfryzacja/ponad-milion-platnosci-bez-kolejek-cyfrowe-oplaty-urzedowe-staja-sie-standardem) | The Ministry documents the first transaction in Bydgoszcz and national use. |
| Technology | [EZD RP](https://www.gov.pl/web/ezd-rp/770-zrealizowanych-wdrozen-produkcyjnych-ezd-rp) | The EZD RP portal records production use in the regional office in Białystok. |
| Education | [Lekcja:Enter](https://lekcjaenter.pl/aktualnosci/zapraszamy-do-obejrzenia-filmu-podsumowujacego-nasz-projekt) | The programme operator confirms participation. It provides no causal estimate of learning gains. |

Reviewers register the public report and the evidence phrases to check in
`backend/scripts/import_deployments.py`. The adapter rechecks them on refresh. Missing
phrases on a readable page send the record for review. A failed fetch retains the last
successful version. This is a bounded adapter for selected reports. A completed Interreg
project and a RAD-on project abstract enter the broader candidate pool. Exact term ranking
continues when Gemini embeddings are unavailable. Paged catalog lookup uses text and
structured filters on the available records.

## Next steps

1. Register an EPO OPS key and add `import_epo.py` filtered by applicant address in Podkarpacie.
2. Ask PCI whether a PBN token or UPRP bulk data can be provided for the pilot.
3. Replace the keyword classifier with the GLiDE classifier used by the admin upload when imports grow.
