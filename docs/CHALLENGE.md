# Challenge: "Radar innowacji" (Podkarpackie Centrum Innowacji)

Sources: [full challenge brief](../materials/PCI%20-%20Pe%C5%82na%20tre%C5%9B%C4%87%20zadania%20konkursowego.pdf)
and [Radar Innowacji FAQ](../materials/Radar%20Innowacji%20FAQ.pdf) (HackNation 2026).
Use the FAQ to define the discovery product and the full brief for submission, evaluation and deployment.

## Requirement traceability

| Source | Requirement | Evidence and acceptance |
| --- | --- | --- |
| FAQ §§1–4, 8.1–3 | Automatically find and organise existing Polish solutions in technology, education and administration | Nationwide registry imports gather candidates. The deployment-report adapter verifies public evidence for ePłatności, EZD RP and Lekcja:Enter. |
| FAQ §5, 8.4, 8.6 | Document deployment, novelty, readiness, applicability and credibility | Card links to proof of use and labels the basis of each assessment. Check one confirmed record, a candidate and optional technology TRL. |
| FAQ §§3, 8.5 | Search, filter and compare for different audiences | Filter by need, area, region, stage and sector. Compare the same criteria in the assistant and open its sources. |
| FAQ §§4, 8.7 | Recurring source updates | The daily host job refreshes source records. Check repeat execution, editorial changes and source failures. |
| FAQ §§6–7 | Discovery with optional usage analytics | Public entry points lead to discovery. Existing admin analytics measure usage. |
| Full brief §§3, 6.4–5 | Explain a transfer or deployment path and how to measure it | Specify an adopter, first condition, next action and metric. |
| Full brief §§5, 9 | Sources, assumptions, security, integration and scaling | See [data sources](DATA-SOURCES.md), [API](../backend/API.md) and [operations](DEVELOPMENT.md). |
| FAQ §8.8–9, full brief §6 | Validate examples and measure usefulness | Compare two timed discovery tasks against source browsing. Count pilots and confirmed deployments during a PCI rollout. |
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

On 2026-11-21, the two worked cases were municipal payments (Bydgoszcz, ePłatności)
and internal document workflow (Białystok, EZD RP). The running catalog returned the
matching cards, opened evidence, and compared their deployment stages, applicability
and suggested next steps. The technical interaction took 0.95 s and 0.79 s from entering
the prepared terms to opening the evidence card. These are single local runs. A timed
comparison against an independent manual search and evaluation with target users are pending.
The education filter and keyboard dialog were also verified at 390 px using Lekcja:Enter.

The local catalog contained 3 confirmed cards, 172 Interreg candidates and 20 RAD-on
candidates from Podlaskie. The scheduled check refreshed the 3 deployment sources
with no duplicates. A manual API review confirmed that a refresh can promote a candidate
and preserve an edited title and attached PDF. A deliberately unavailable source left
the catalog unchanged. The comparison worked with the provider unavailable. The Gemini
key was rejected during local verification, so a live generated assistant answer was
outside the verified flow.

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
