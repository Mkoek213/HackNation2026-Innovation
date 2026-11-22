# Data sources

Date: 2026-11-21.
The catalog covers all of Poland; every importer accepts `--region` to limit a pilot to one voivodeship.
Sources were chosen for the data a card needs (description, area, institution, region and evidence of use), not to cover every source named in the brief.

## Sources in use

| Source | Access | Filter | Importer and volume |
| --- | --- | --- | --- |
| Public deployment reports (gov.pl, samorzad.gov.pl, pacjent.gov.pl, programme and contractor pages) | HTML pages, no key | Hand-picked reports; exact evidence phrases must appear on the page | `import_deployments.py`: 10 confirmed cards, 3 per area or more, 3 from Podkarpackie |
| European Funds 2014-2020 project list (Ministry of Funds and Regional Policy, gov.pl) | Monthly XLSX (about 60 MB), no key | Completed funding, beneficiary is a school, university, local government or public institution, at least two innovation keywords; round-robin over area and voivodeship | `import_fundusze.py`: 500 of 1981 eligible of 103 829 projects |
| CORDIS Horizon Europe export (European Commission, CC BY 4.0) | CSV zip (about 38 MB), no key | Polish coordinator or participant; innovation actions, EIC, pre-commercial procurement first; MSCA, ERC, co-funding and terminated projects skipped | `import_cordis.py`: 400 of 1372 eligible projects |
| Interreg 2021-2027 project list (interreg.gov.pl, art. 49 CPR) | Official XLSX, no key | Lead partner from a Polish voivodeship | `import_interreg.py`: 172 of 258 projects |
| RAD-on / POL-on open data (radon.nauka.gov.pl) | Public JSON API, no key, token pagination | Institutions per voivodeship, then their research projects with a Polish abstract since 2022 | `import_radon.py`: up to 20 newest projects per voivodeship |
| Interreg, NCBR successes, pcinn.org pages | Static HTML | Not needed | Read live by the chat (`discover_sources`, `read_source`) |

The 2014-2020 European Funds list is used because its projects are finished, so each one describes something that was delivered.
No equivalent nationwide 2021-2027 export was found; `import_fundusze.py` keeps the attachment URL of the newest monthly edition as a constant to update.
About 1% of CORDIS rows have unquoted semicolons in free text that shift every later column; the importer skips them.
CORDIS texts stay in English as published; the automatic assessment adds a Polish summary that is searchable.

## Sources not used

- UPRP e-wyszukiwarka: a single-page app behind Incapsula bot protection, so automated access is blocked.
- EPO register and OPS: the register returns 403 and OPS needs a registered consumer key; patents are rarely deployed public-sector innovations, so they were not prioritised.
- PBN: the API returns 403 without an institutional token.
- NCN project search: returns 403 to automated clients; RAD-on already covers NCN-funded projects.
- Google Scholar: no API and its terms forbid scraping; a publication is rarely an innovation in the Oslo Manual sense.
- OpenAlex: open, but publications add noise for the same reason.
- PPM and BazTOL: repositories of Poznań institutions, not a national innovation source.

## Data handling

- Every card keeps `source_name`, `source_url`, `imported_at` and `checked_at`, so it names its source.
- RAD-on project managers are public data and are stored as `authors` with their affiliation; other sources store institutions only.
- Area, sector, innovation type and institution type come from transparent keyword rules in `backend/scripts/import_common.py` (Polish and English keywords, company legal forms excluded from public institutions); admins correct labels in the Dokumenty panel.
- Registry records enter as `kandydat`; only deployment reports with verified evidence phrases become `potwierdzona`.
- `assess_innovations.py` then scores every card against the five FAQ criteria (see [backend/API.md](../backend/API.md)).

## Deployment evidence

| Area | Case and source | Evidence scope |
| --- | --- | --- |
| Administration | [ePłatności](https://www.gov.pl/web/cyfryzacja/ponad-milion-platnosci-bez-kolejek-cyfrowe-oplaty-urzedowe-staja-sie-standardem) | First transaction in Bydgoszcz and national use, per the Ministry. |
| Administration | [e-Doręczenia](https://www.gov.pl/web/cyfryzacja/100-mln-przesylek-w-e-doreczeniach-cyfrowa-korespondencja-z-urzedami-stala-sie-standardem) | Over 100 million deliveries and 4.6 million addresses, per the Ministry. |
| Administration | [PSeAP](https://samorzad.gov.pl/web/powiat-jasielski/pseap---podkarpacki-system-e-administracji-publicznej.) (Podkarpackie) | A partner county describes the delivered e-services and document workflow systems. |
| Technology | [EZD RP](https://www.gov.pl/web/ezd-rp/770-zrealizowanych-wdrozen-produkcyjnych-ezd-rp) | Production use in the regional office in Białystok. |
| Technology | [e-Recepta](https://pacjent.gov.pl/e-recepta) | The operator describes nationwide use in every pharmacy. |
| Technology | [Bus stop monitoring in Rzeszów](https://www.assecods.pl/en/case-studies/intelligent-bus-stop-monitoring-system) (Podkarpackie) | 47 bus stops, per the contractor; the card says the effects need confirmation by the city. |
| Education | [Lekcja:Enter](https://lekcjaenter.pl/aktualnosci/zapraszamy-do-obejrzenia-filmu-podsumowujacego-nasz-projekt) | Participation figures from the programme operator, no causal estimate of learning gains. |
| Education | [Laboratoria Przyszłości](https://www.gov.pl/web/nauka/niemal-miliard-zlotych-w-ramach-laboratoriow-przyszlosci-juz-w-szkolach-w-calej-polsce) | Over 99% of eligible schools joined, per the Ministry. |
| Education | [OSE](https://www.gov.pl/web/cyfryzacja/ose-szybki-internet-w-szkolach-sprzet-dla-uczniow-i-nauczycieli) | Signed and connected schools, per the Ministry. |
| Education | [RaP STEAM](https://samorzad.gov.pl/web/gmina-grodzisko-dolne/pilotazowe-zajecia-warsztatowe-z-robotyki-w-zespole-szkol-im-prof-franciszka-leji-w-grodzisku-gornym) (Podkarpackie) | Gmina Grodzisko Dolne reports that robotics workshops for grades V–VIII started in Grodzisko Górne on 1 September 2024. |

Reviewers register a report and its evidence phrases in `backend/scripts/import_deployments.py`.
The refresh rechecks them; missing phrases on a readable page send the card back to review, and a failed fetch keeps the last version.

## Next steps

1. Add more deployment reports, especially from schools and municipalities, as PCI collects them.
2. Ask PCI whether a PBN token or UPRP bulk data can be provided for a pilot.
3. Replace the keyword classifier with the GLiDE classifier used by the admin upload.
