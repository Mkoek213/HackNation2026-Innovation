# Frontend design style

Living record of frontend guidelines supplied by the user. Updated: 2026-11-21.
User-confirmed guidelines take precedence over library defaults and implementation choices.

## Confirmed guidelines (2026-10-03 overhaul, supersedes earlier warm-monochrome passes)

### Scope

- The product does only what it must: the chat (reporting and finding innovations) is the focal point.
- Routes: `/` (public home page: what Radar innowacji is, with entry points to the chat and the innovation base), `/rozmowa` (Rozmowa, the chat), `/matters` (Moje sprawy), `/knowledge/innovations` (Baza innowacji;
  `/knowledge` redirects there), `/contact` (Kontakt), and the admin-only
  `/administration/analytics` and `/administration/documents`; `/administration` redirects to Dokumenty.
- The tab menu is shown before sign-in too. Kontakt is a standalone form (name, e-mail, message, consent) reachable
  without signing in or starting a chat, and it is the last tab for everyone.
- Innovation cards show the sector, institution and maturity; the detail dialog adds a facts row (innovation type,
  institution, maturity, creators) and the source with its import date.
- Admins get two extra header tabs: "Analityka" and "Dokumenty".
  Analytics uses headed panels, metric tiles and data tables. Topic trends are small multiples of inline SVG
  line charts (no chart library) on one shared scale: slate for the previous period, navy with a light fill
  for the selected one, an `aria-label` summary and per-point `<title>` tooltips, with the same data in a
  table inside a disclosure. No maps.
- Entry stays mandatory (the chat backend requires a session), shown as a minimal centered card with two
  equal demo buttons: Użytkownik and Administrator. The visitor types no credentials. The frontend registers
  the fixed demo account when it is missing, then logs in (2026-10-03).
- Conversation history stays as a simple list with "Nowa rozmowa". A trash icon deletes a conversation from history (2026-10-04, at the user's request); it appears on row hover or keyboard focus and stays visible on touch devices. Deletion is disabled while that conversation is processing a reply. The backend archives the conversation. Deleting the open conversation selects the next one or creates a new conversation when the history is empty.
- Innovation titles in answers keep opening the source-detail dialog so users can verify answers.
- Audience is government and public institutions: trust-first, accessible (WCAG 2.1 AA target), clean and polished.

### Layout

- Slim navy top bar on every page: radar mark and "Radar innowacji · PCI" on the left, tabs (Rozmowa, Moje sprawy,
  Baza innowacji, Kontakt; admins also see Analityka and Dokumenty before Kontakt), username and logout on the right. The active tab has an amber underline.
- When the tabs do not fit beside the brand and the account controls even after the 1440px tightening (admin tabs,
  enlarged font), they move to a second 48px row under the 64px top row instead of being clipped; `--header-h`
  follows the actual header height.
- Desktop chat: fixed 280px white history sidebar plus a centered conversation column (max 760px).
  Mobile: the sidebar becomes a "Historia rozmów" drawer; the top bar keeps the mark, tabs and an icon logout.
- An empty conversation shows one short heading and sentence explaining what to ask, followed by six
  ready-made openings ("Zacznij od gotowego wniosku", 2026-10-04). Choosing one puts its text into the composer
  and selects the first "…" gap; nothing is sent until the person submits. Existing composer text is kept.

### Palette (navy + amber + cool slate)

| Role | Token | Value |
|---|---|---|
| Primary (actions, identity, user bubbles) | `--navy` | `#16325C` |
| Primary hover | `--navy-hover` | `#0F2647` |
| Accent (fill only, never text on white) | `--amber` | `#F2B544` |
| Accent tint (status notes, selection) | `--amber-soft` | `#FDF1D8` |
| Surface structure | `--slate` / `--slate-soft` | `#E3E9F1` / `#EEF2F7` |
| Page background | `--surface-tint` | `#F5F7FA` |
| Text / secondary text | `--ink` / `--ink-soft` | `#1A2433` / `#4A5568` |
| Borders / input borders | `--line` / `--input` | `#D9E0EA` / `#7A879B` |
| Error / success | `--danger` / `--success` | `#B42318` / `#1E6B3A` |

Amber appears only as the active-tab underline, the brand mark, focus outlines inside the navy bar,
quote rules and tinted notes. Light mode only for now.

### Innovation areas

Innovation-card left edges show one of three sector areas instead of amber; the sector pill takes the
area's soft tint and keeps navy text. A legend above the grid names the areas.

| Area | Sectors | Edge / tint |
|---|---|---|
| Przemysł, transport i kosmos | automotive, aviation, space | `#2A78D6` / `#E3EEFB` |
| ICT i cyfryzacja | ICT | `#EB6834` / `#FDE8DF` |
| Jakość życia i inne obszary | quality of life, other | `#1BAF7A` / `#DCF3EA` |

One colour per sector was rejected: with many hues any two cards can be neighbours and the validator
fails under colour-vision deficiency. The three areas pass all pairs (ΔE 9.2 / 24.0). The third edge is
2.8:1 on white, so the sector text and the legend stay mandatory: colour never identifies a sector on its own.

### Typography and shape

- System sans everywhere (`system-ui` stack); no serif headings, no remote fonts.
- Soft corners: 8px controls, 12px cards, panels, dialogs and chat bubbles.
- Minimal motion: short opacity/translate entry on cards and pages, hover feedback; all disabled under reduced motion.

### Accessibility controls

- Header accessibility bar: high-contrast toggle and font size A− / A / A+, persisted in `localStorage` (`radar-a11y-contrast`, `radar-a11y-font`).
- High contrast forces black text on white, yellow accents on the navy header, and underlined links.

### Conversation controls

- Auto-growing composer with bounded height, a full-surface navy focus ring, an icon-only dictate button, and an icon-only send button. Both buttons have Polish accessible names.
- Dictate uses the browser speech API in Polish (`pl-PL`). Listening is a pressed navy state plus a visible status. Recognized text is inserted at the caret (replacing a selection) for review; nothing is sent until the person submits. Typing and dictation work together: typing does not stop dictation, text typed around the phrase being recognized is kept, and editing inside that phrase ends it so the next phrase starts at the caret. Unsupported browsers get a clear Polish message.
- Pending sends clear the composer immediately and disable sending until the reply finishes; failed sends restore the message so it can be retried.
- A reply in progress shows a brief “Przetwarzam” status with three pulsing dots.

## Project conventions

- User-facing copy in Polish; internal documentation in English.
- Design toward WCAG 2.1 AA: keyboard operation, accessible names, visible focus, readable contrast,
  understandable status and error messages. No WCAG certification is claimed.
- Forms validate on submit with Polish messages: a focused error summary at the top links to each invalid field,
  each field shows its message above the control (`aria-invalid`, `aria-describedby`), and a successful send moves
  focus to the confirmation heading.
- Component system: shadcn/ui (Base UI primitives), adapted to the palette above.
- Define reusable components once in `components/ui/`; keep colors and theme values in `app/globals.css` tokens.
- Icons are the shared primitives in `components/ui/icons.tsx`; decorative icons are hidden from assistive technology.

## Updating this record

Append or revise guidelines when the user supplies them. Keep proposals visibly separate from confirmed choices.

### PCI contact summary

- Keep the dialog to recipient, subject and a collapsed read-only preview of the entire message. Users edit the message in their mail client.
- Open the user's configured mail client via `mailto:` with a short consultation request and the full summary later in the message body. No PDF attachment, `.eml` export, Google OAuth or Gmail API. Keep “Kopiuj wiadomość” as a fallback for unavailable mail handlers or truncated compose links; if clipboard access fails, expand and select the message preview. No direct SMTP action in this dialog.
