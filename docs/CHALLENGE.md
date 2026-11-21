# Challenge: "Radar innowacji" (Podkarpackie Centrum Innowacji)

Sources: [full challenge brief](../materials/PCI%20-%20Pe%C5%82na%20tre%C5%9B%C4%87%20zadania%20konkursowego.pdf)
and [Radar Innowacji FAQ](../materials/Radar%20Innowacji%20FAQ.pdf) (HackNation 2026).
Use the FAQ to define the discovery product and the full brief for submission, evaluation and deployment.

## Requirement traceability

| Source | Requirement | Evidence and acceptance |
| --- | --- | --- |
| FAQ §§1–4, 8.1–3 | Automatically find and organise existing Polish solutions in technology, education and administration | Five importers (European Funds 2014-2020, CORDIS, Interreg, RAD-on, deployment reports) gather about 1400 cards from 16 voivodeships; 10 deployment reports are verified by evidence phrases. |
| FAQ §5, 8.4, 8.6 | Document deployment, novelty, readiness, applicability and credibility | Each card scores the five criteria 1-5 with basis `potwierdzone` or `szacunek` and a source; credibility follows fixed rules, the rest are Gemini estimates with checked quotes; deployment levels follow the FAQ stages. |
| FAQ §§3, 8.5 | Search, filter and compare for different audiences | Search by need; filter by area, target group ("Dla kogo", all six FAQ groups), voivodeship, deployment level, credibility and sector; compare two cards side by side or in the assistant. |
| FAQ §§4, 8.7 | Recurring source updates | The daily job (`refresh_innovations.sh`, 04:15) refreshes source records and then assesses new cards; the catalog shows the next run and the last check. |
| Full brief §3 | Similar solutions and less duplicated work | Each card lists the four closest cards by meaning ("Podobne rozwiązania"); the chat compares a card with alternatives. |
| FAQ §§6–7 | Discovery with optional usage analytics | No idea submission, social or funding features; reported candidates are existing solutions hidden until staff review in Dokumenty. Admin analytics show chat topics, cards proposed in chat, cards opened in the catalog and chosen filters, all by anonymous visit ids and never with typed search text. |
| Full brief §§3, 6.4–5 | Explain a transfer or deployment path and how to measure it | Card section "Potencjalni odbiorcy i ścieżka": path, recipients, first step and measures; the chat adds addressee, condition and metric. |
| Full brief §§5, 9 | Sources, assumptions, security, integration and scaling | See [data sources](DATA-SOURCES.md), [API](../backend/API.md) and [operations](DEVELOPMENT.md). |
| FAQ §8.8–9, full brief §6 | Validate examples and measure usefulness | Two timed discovery tasks against the raw sources (below). Count deployments started from Radar during a PCI rollout. |
| Full brief §4 | Submission and demonstration | Polish title and description, PDF presentation up to 10 slides, public video up to 3 minutes. |

## Organisation

Podkarpackie Centrum Innowacji (PCI) supports innovation and entrepreneurship in województwo podkarpackie.
It connects science, business and public administration, funds R&D projects of universities and companies, and runs accelerator programmes.
Priority sectors: automotive, quality of life, ICT, aviation and space.
PCI offers labs and prototyping tools to young innovators aged 16-30.

## Problem

Valuable ideas appear in schools, universities, local governments (JST) and other public institutions, but often stay known only inside the organisation that created them.
There is no simple, common mechanism to identify them systematically, compare their potential and route them to the right recipients.
As a result, innovations are not deployed elsewhere, do not reach users, partners or investors, and institutions solve the same problems independently.
An innovation is not always a technological product: it can be organisational, educational, social or process-based.

## Challenge

Build a solution that systematically finds "hidden" innovations in public institutions, pre-assesses their potential and indicates paths for further development, transfer, commercialisation or deployment.
It should answer: where and how to look for valuable ideas, what information to collect, how to assess potential, and how to connect an innovation with a user, partner, investor or another organisation that needs a similar solution.

## Expected result

A prototype that identifies, structures, pre-assesses and routes innovations from public institutions.
The form is open (system, platform, analytical tool, technology-supported process).
Especially welcome mechanisms:

- reporting or automatic detection of potential innovations,
- structuring information about the idea and its creators,
- assessing potential against clearly defined criteria,
- recommending a development, transfer, commercialisation or deployment path,
- searching for similar solutions to reduce duplicated work,
- connecting creators with potential users, partners or investors.

Users: staff and representatives of schools, universities, local governments and other public institutions, and organisations looking for ready or developing solutions.

## Formal requirements

The submission must contain: project title, problem and solution description, description of how it works and its main functions, a PDF presentation (max 10 slides), and a video in an open repository (max 3 minutes) showing the project working.
Optional: code repository, working prototype, screenshots, demo link, mock-ups and other materials.

## Technical requirements

No mandated stack; technology should fit the solution and allow further development and deployment.
If the project uses data, AI/ML, automatic recommendations or external integrations, name the data sources, the basic assumptions and the limitations.
Pay attention to: scaling to many organisations, security and data protection, integration with existing systems, transparency of assessment and recommendation criteria, and development after the hackathon.

## Validation scenario

Judges check whether the solution really supports finding and assessing hidden innovations and leads the user from identifying an idea to a possible development or deployment path.

1. Enter an example innovation or detect one automatically.
2. Collect and structure the key information.
3. Assess its potential against the proposed criteria.
4. Indicate potential recipients, partners or development paths.
5. Present the justification of the recommendation, with expected effectiveness measures.

Evaluate on at least two example use cases.

### Local validation record

On 2026-11-21 the local catalog held 1402 cards: 10 confirmed deployment reports, 500 European Funds projects, 400 CORDIS projects, 172 Interreg projects and 320 RAD-on projects, covering all 16 voivodeships.
All 1402 cards were assessed with `kryteria-2026-11` by `gemini-3.5-flash-lite`.
In the browser, at desktop width and at 390 px, the following worked: catalog search, all filters including the target group, comparison, the card dialog with similar solutions, the sync badge and the catalog analytics.
The chat answered the two demo cases (ePłatności and EZD RP) with an addressee, a first condition and a measure.
A candidate reported through the chat creator was stored as `zgloszone`, was absent from the public list, detail route, catalog and chat retrieval, and became public after staff changed it to `kandydat` in Dokumenty.
The project's prepaid Gemini credits then ran out (HTTP 402), which stopped the chat, the assessment and new embeddings.
A second assessment run during that outage cleared the notes of 581 cards and the dense vectors of 747 cards; both causes are fixed, and the data is restored by `assess_innovations.py` (without `--force`) and `backfill_dense.py` once credits are available.

### Time to find an existing solution

Measured on 2026-11-21 on the same machine for two tasks: a municipality looking for online payment of office fees, and a school looking for a robotics programme already used in schools.

| Step | Radar | Raw sources |
| --- | --- | --- |
| Get the data | Already gathered and assessed | European Funds list: 62 MB XLSX, 10 s download; CORDIS: 38 MB zip, 7 s; Interreg and RAD-on separately |
| Search | One query, 0.5 s (`płatności urzędowe`, `robotyka szkoły`) | 103 829 European Funds rows to filter; a title filter gives 32 and 16 rows, mostly company R&D |
| First relevant result | ePłatności and RaP STEAM in the top three, with confirmed use and source | No deployment status, area or assessment; every row needs a separate check |

This is a proxy: it counts data handling and steps, not a timed session with target users, which is still pending.

Submission files: [description](../submission/opis.md), [eight-slide PDF](../submission/radar-innowacji.pdf)
and [local demonstration](../submission/radar-demo.mp4).

## Suggested data sources

- Patent databases: UPRP (https://ewyszukiwarka.pue.uprp.gov.pl), EPO register (https://register.epo.org).
- Scientific publications: PBN (https://pbn.nauka.gov.pl), PPM (https://ppm.edu.pl).
- Digital libraries: czasopisma.pan.pl (dLibra), BazTOL.
- EU-funded project databases: Interreg (https://interreg.gov.pl/lista-projektow/), NCBR beneficiary successes.

What the project actually uses, and why, is recorded in [the data source investigation](DATA-SOURCES.md).

## Scoring

Relation to the challenge and quality of the solution 20%, idea and originality 20%, usefulness and user experience 20%, completeness and quality of the prototype 20%, deployment potential, scalability and transferability 20%.

## Deployment context

The greatest value is use beyond the hackathon: systematic search and structuring of innovations in real institutions.
Design for many institution types, not one organisation; emphasise scalability, a repeatable assessment process and a clear answer to what happens with an innovation after it is identified.

Contact: Kacper Moczarny, k.moczarny@pcinn.org; mentors on the PCI stand and the challenge Discord.
