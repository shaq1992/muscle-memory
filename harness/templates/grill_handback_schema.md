# Template: Grill Handback Schema

Single source of truth for the two artifacts an ORCHESTRATED REQUIREMENTS
GRILLING session (`commands/orchestrated_grill.md`) writes back to the
orchestrator: the LEAN HANDBACK and the REQUIREMENTS DOC it points at. Written
by the dispatched grilling session; read and ingested BY HAND by the
orchestrator; its shape is checked deterministically by the grill closing hook
(`hooks/enforce_grill_handback.py`). No command restates this schema inline.

This is a SIBLING of `harness/templates/handback_schema.md`, not a variant of
it. Where this file says a rule is INHERITED, the sibling's text is
authoritative and is not restated here; everything else below is specific to
grilling sessions and overrides nothing in the sibling. An implementation
session (`/grill_and_implement`) never writes this shape, and a grilling
session never writes the sibling's.

The session never writes the plan's state file -- the one-writer rule of
`harness/templates/state_schema.md` holds unchanged. A grilling session holds
no tree: no branch, no commits; it writes only the two (gitignored) docs files
defined here.

## Why a separate shape

A grilling session's durable product is a REQUIREMENTS DOC, not a set of
established facts. Forcing it through the implementation handback's
`## Delta` would make the session pre-author state rows for decisions the
orchestrator has not yet weighed, and would push the whole requirements
record through a channel built to be ingested mechanically and read
minimally. So the two are split:

- the REQUIREMENTS DOC carries everything, in full pedantic detail;
- the LEAN HANDBACK is a short index into it -- enough for the orchestrator
  to know what came back and where to look, cheap enough to read whole.

## File locations

- **Handback:** the path in the dispatched prompt's `Handback:` field --
  conventionally `docs/orchestration/<plan_name>/handbacks/<NN>.md`, the same
  location, numbering and never-reused rule as the sibling schema (INHERITED).
- **Requirements doc:** the path in the prompt's bare-value
  `Requirements doc:` field -- conventionally
  `docs/orchestration/<plan_name>/requirements/<NN>.md`, where `<NN>` is the
  same zero-padded dispatched session number. The session writes exactly the
  path it was given and never derives its own.

## Written at session START, not at session end (INHERITED)

The handback is CREATED AS A STUB the moment the session reads its prompt,
before the first question: `Status: OPEN` plus the read receipt. The reasons
and the ordering are the sibling schema's, unchanged.

## The read receipt (INHERITED)

Exactly the sibling schema's two-line receipt, under the same header
`**Handed to this session (read receipt):**` -- `- Rows:` (the E-IDs from the
first cell of each row in the prompt's "Rows this session must obey" block)
and `- Prompt-SHA256:` (one `sha256sum` over the exact bytes of the
dispatched prompt file). Its definition, its verification against the
dispatch manifest, and the orchestrator's "never read back the read receipt"
law all live in `harness/templates/handback_schema.md`; they are not restated
here.

## Stops while `OPEN` are allowed -- the deliberate difference

A grilling session STOPS ON EVERY QUESTION: each AskUserQuestion round and
each `linger` exchange ends a turn, and the session has no question cap, so
it may stop dozens of times before it is done. The sibling schema's rule that
a live session may not close while `OPEN` -- enforced by
`hooks/enforce_handback.py`, which blocks every such stop unless a pause is
declared -- would stall a grilling session on every question. That was the
observed defect this schema exists to remove.

So for a grilling handback:

- every stop while the handback is `OPEN` is ALLOWED -- an `OPEN` stub is the
  normal state of a session that is still asking questions;
- the shape checks below apply only once the file carries a TERMINAL status.

This is why a grilling session arms its own marker,
`.claude/grill_handback_session.json`, and NEVER the sibling's
`.claude/handback_session.json` (the marker's key set is owned by
`commands/orchestrated_grill.md`).

An `OPEN` stub found by the orchestrator therefore means "died, or still
grilling" -- the orchestrator asks the user which, rather than inferring a
death from the status alone.

## Structure of the lean handback

Exactly SIX parts, in this order. There is no `## Delta` section and no
optional section.

```
Status: OPEN | PARTIAL | ABANDONED | COMPLETE

**Handed to this session (read receipt):**
- Rows: <comma-separated row E-IDs from the prompt's orchestration block>
- Prompt-SHA256: <sha256 of the dispatched prompt file, lowercase hex>

## Requirements doc
<path of the requirements doc>
<one line: the scope the doc covers>

## Decisions at a glance
- <one-line load-bearing decision> (doc: <section name>)
- ...

## Open questions
- <one line per question left unresolved>

## For the orchestrator
[advisory: suggested next session; state rows the orchestrator may want to write]

## Structural observations
[closed vocabulary, or "none"]
```

Part one is the header: the `Status` line plus the read receipt. Parts two
through six are the five `##` sections.

### `Status` -- closed vocabulary

The same four values as the sibling schema, with grilling-specific meanings:

| Value | Meaning |
|---|---|
| `OPEN` | The stub. Normal while the session is still grilling. |
| `PARTIAL` | The session closed before the user said the stop sequence; the requirements doc holds what was captured and says so in its first line. |
| `ABANDONED` | The session stopped deliberately without producing a requirements doc worth reading. |
| `COMPLETE` | The user said the stop sequence; the requirements doc is written in full and has passed the re-audit. |

`PARTIAL`, `ABANDONED` and `COMPLETE` are terminal. A grilling session never
self-terminates, so `PARTIAL` is written only when the session is ending for
a reason outside the grilling (the user is leaving, the context is
exhausted) -- never as a shortcut past the stop sequence.

### `## Requirements doc`

Two lines: the doc's path, exactly as given in the prompt, and one line
stating the scope it covers. Nothing else -- the doc speaks for itself.

### `## Decisions at a glance`

At most about FIFTEEN one-line bullets: the LOAD-BEARING decisions only --
the ones that would change what the orchestrator dispatches next. Each bullet
cites the requirements-doc section it summarises. This section is an index,
not a copy: it never carries the user's verbatim wording, the reasoning, or
the full decision set -- those live in the doc. Where a bullet and the doc
disagree, THE DOC WINS.

The bound is a judgement ceiling, not a quota and not a hook check: fifteen
bullets that are all load-bearing is fine; padding to fifteen is the failure.

### `## Open questions`

One line per question the grilling left unresolved, each naming the doc
section where it is recorded in full. Write `none` if nothing is open.

### `## For the orchestrator`

ADVISORY, like the sibling's `## For the next session`: a suggested next
session, and the facts the session thinks deserve state rows -- one line each,
naming the fact and the doc section it comes from. They are suggestions, not
pre-formatted rows: the ORCHESTRATOR authors any row it decides to write
(write-through trigger (d) of `commands/orchestrator.md`). Nothing here binds
the orchestrator; where it conflicts with state, STATE WINS.

### `## Structural observations` (INHERITED)

Same closed tag vocabulary and the same exact machine line shape
`- <tag> | <description>` as the sibling schema, or `none`. The tag table and
its growth rule live in `harness/templates/handback_schema.md`; edit the two
schemas' use of it in lockstep. The session never appends to
`docs/observations.md` itself.

## The requirements doc

The requirements doc is the grilling session's real output, and the only
record downstream sessions will have of what the user decided -- the session
transcript is not downstream-readable. Any missed detail is a disaster. It is
written in FULL PEDANTIC DETAIL and carries, at minimum:

1. **A self-containment note** as its opening lines: question-number tags
   (`Q<N>`) and any other session-time identifiers in the doc are CITATIONS
   ONLY; the document text is authoritative and downstream readers never try
   to resolve a tag.
2. **Every decision, grouped by area**, each citing the question number it
   came from.
3. **The user's elaborations and asides VERBATIM** -- everything the user
   said beyond picking an option, including asides recorded without costing a
   question and everything said inside a `linger` sub-loop.
4. **Constraints and invariants** surfaced during the session.
5. **Open questions** left unresolved, each stated in full.
6. **A proposed session / work breakdown**, if one emerged; otherwise one
   line saying none emerged.

Before the doc counts as written, the session runs the re-audit pass of
`commands/grilling_session.md`'s capture discipline: re-read every user
message of the session and confirm each decision AND each aside is in the
doc -- `linger` asides are the highest-risk for loss and are checked
explicitly.

The doc is written BEFORE the handback is finalized, so a terminal
`PARTIAL` or `COMPLETE` handback always points at a doc that exists.

## Ingest is MANUAL ONLY

`harness/scripts/ingest_handback.py` is NEVER run on a grilling handback: it
has no `## Delta` to apply and would fail closed on the missing section. The
orchestrator ingests by hand:

- it reads the lean handback (it is short by design) -- still never the read
  receipt, per the sibling schema;
- it writes any state rows ITSELF, under its own write-through triggers,
  authoring each row from the requirements doc rather than transcribing the
  handback;
- it copies each `## Structural observations` line to `docs/observations.md`
  in the sibling schema's fixed dated shape;
- it updates the session's `## Dispatched` row per the handback's `Status`.

## The orchestrator reads the requirements doc FREELY

The orchestrator is ALLOWED and ENCOURAGED to read the requirements doc -- in
full or in pieces, as often as it needs. This is the deliberate difference
from the lean-handback reading discipline of the sibling schema: that
discipline exists because an implementation handback's content has already
been reduced to rows the orchestrator never needs to re-read, whereas the
requirements doc IS the content, and the orchestrator is the one that must
turn it into state rows and dispatches. Economising on it would push the
orchestrator into authoring from the lean index alone -- a second author of
facts the doc already states.

## Terminal-state checks (the grill closing hook)

On a stop whose handback carries a TERMINAL status, the hook checks:

- `ABANDONED`: the `Status` line is present -- nothing else is required;
- `PARTIAL` or `COMPLETE`: the five `##` sections are present in the order
  above, there is NO `## Delta` section, each structural-observation line has
  the sibling's machine shape (or the section reads `none`), and the
  requirements doc exists at the path in `## Requirements doc` and is
  non-empty.

On a pass the hook removes the grill marker. The bullet ceiling of
`## Decisions at a glance` is judgement and is never counted by the hook.

## The abandon path -- BINDING CONSTRAINT (INHERITED)

The sibling schema's binding constraint applies unchanged: the abandon path
costs about THREE LINES -- the `Status` field and one sentence -- and the
enforcing hook's block message states that minimal content VERBATIM:

```
Status: ABANDONED

The user ended the grilling before any requirement was settled; no requirements doc was written.
```

Any change that raises this cost is a defect in the change.

## What the handback replaces

As for the sibling schema: NO phase-closing marker, NO per-phase learnings
file, NO ledger merge and no `Last merged` stamp. Additionally, a grilling
session opens no branch, makes no commit and opens no pull request. The lean
handback and the requirements doc are the session's whole durable output.
