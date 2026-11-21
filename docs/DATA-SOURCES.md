# Investigation: access to the PCI brief data sources

Date: 2026-11-21.
Question: which data sources suggested by the brief can feed the Radar knowledge base legally and repeatably, filtered to województwo podkarpackie?

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
- School innovations are not present in any public registry; they enter Radar only through chat submissions.
- RAD-on abstracts describe research projects, not proven innovations; maturity is left unset for them.

## Next steps

1. Register an EPO OPS key and add `import_epo.py` filtered by applicant address in Podkarpacie.
2. Ask PCI whether a PBN token or UPRP bulk data can be provided for the pilot.
3. Replace the keyword classifier with the GLiDE classifier used by the admin upload when imports grow.
