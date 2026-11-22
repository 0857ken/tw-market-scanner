# Offline rebound history study

This development branch adds an optional command-line tool. Existing scanner data, frontend, workflow configuration and Pages assets are untouched by the study. Study results, data copies and the source archive stay in a separate private workspace.

Run the local suite with `python3 -m unittest discover -s research/rebound_history -v`.

## Reproduce

1. Start with the separately approved, hash-pinned frozen rule archive. Reuse the archive already authorized for the research. The evaluator checks the archive and every pinned member before running the existing indicators and signals.
2. Save raw data and their receipts in a directory outside this Git worktree. `capture.py RAW calendar futures ohlc turnover` downloads public exchange reports. Optional `capture.py RAW margin --sessions SESSION_DATES` requires an ordered ISO list of observed trading dates. A receipt records HTTP status, raw byte SHA256, retrieval UTC and response timestamps. Publication time stays null without independent evidence.
3. Run `study.py RAW PRIVATE_ARCHIVE APPROVED_ARCHIVE_SHA256 OUTPUT` with both input and output directories outside this Git worktree. A previously captured TWSE 2026 Fact Book table can be verified from `RAW/official_checks/twse-factbook-2026.body` and the matching receipt.

## Analysis definitions

- TAIEX price index. Event day close to the close after 1/3/5/10/20/40/60 observed sessions. Record next-day-through-exit daily high and low relative to the event close. Insufficient tails and input gaps are censored. Break the warmup and outcome path at unresolved quote gaps. Signal counts distinguish true, false and unavailable inputs.
- Compare against all observed eligible trading dates. An additional descriptive comparison uses nontrigger dates in the same calendar year and the same contemporaneous daily return and 20-session drawdown bins. Bins straddle the price-trigger thresholds so controls remain possible near those thresholds. A stratum without controls yields no matched observation.
- Show earliest-trigger non-overlap sensitivity and year-specific results with exits in the same year. Separate early and later historical samples from the post-freeze observations. Results remain exploratory pending publication-time proof and independent out-of-sample validation.
- Exploratory significance compares event versus observable non-event dates. Use a two-sided wild sign score test across contiguous blocks of max(20, 2 × horizon) sessions, with 9,999 seeded draws, at least 10 non-overlap trigger windows and 10 nontrivial blocks. Use Holm adjustment across all 105 planned cells. Report untested cells separately. Matching and joint-event analyses are descriptive. Remaining serial dependence and sample selection can affect all inference.
- Joint analysis requires all price predicates in scope to be observable. Combine nested predicates into families before counting 0, 1 and 2-or-more simultaneous families. Assess the last group against one-family days within the same descriptive matching strata.
- Index points, NTD turnover, market margin in NTD 100 million per frozen input, and exact TXF foreign long/short position counts. No substitute series. Margin inputs use the date's own report, leaving next-report revisions for quality diagnostics.

Private source, captures, detailed results and their rights remain outside public Git. No automatic run or publication integration is configured.

## Next-open sensitivity (descriptive only)

Run `python3 research/rebound_history/sensitivity.py RAW PRIVATE_ARCHIVE APPROVED_ARCHIVE_SHA256 OUT.csv`
with all input/output files **outside** the public Git worktree. Use the same
preapproved frozen archive and identical `--exclude-margin-date DATE` flags
as the five-year exploration. The module recalculates the original frozen
signals without changing the 15 predicates, measuring the T+1 opening TAIEX
index to T+h closing TAIEX index return for horizons 1/3/5/10/20/40/60.
Segment boundaries, expired exits and missing signal data fail closed.

**This is only a price-index entry-timing sensitivity.** The index cannot
itself be traded; publication timestamps, historical as-of revisions, actual
fills, fees, slippage and true out-of-sample predictive ability have not been
independently validated. The module always writes `pit_qualified_n = 0` and
`EXPLORATORY_INDEX_PROXY_NOT_PIT`, never an approved strategy label. No new
permissions, automatic capture, schedule or website publication are involved.


## Forward PIT observation procedure (manual and private)

The five-year historical capture is NOT a PIT dataset. Collection receipts
were generated retrospectively in October/November 2026, not on the original
2021–2026 signal dates. A valid HTTP Date header or SHA256 confirms a retrieved
version, not the first time the underlying value was publicly available.

First, audit the PINNED, authorized private research ZIP using:

    python3 research/rebound_history/pit_guard.py PRIVATE_REVIEW.zip --sha256 APPROVED_PRIVATE_ZIP_SHA256 --out PRIVATE_PIT_AUDIT.json

The offline tool checks each raw body SHA256, source host, retrieval timestamps,
year/month/day scope and the historical next observed session. Its statuses
never claim PIT qualification. Missing start times/redirect identities in old
receipts are explicitly quarantined. The audit output must remain outside the
public Git repository.

For a genuinely future TWSE session, use the following once-only, private
manual data capture, after that session closes and before the next session
opens if the two official reports are already available:

    python3 research/rebound_history/forward_capture.py PRIVATE_DIRECTORY YYYY-MM-DD NEXT_SESSION_YYYY-MM-DD PINNED_FROZEN_RULE_ARCHIVE_SHA256

The operator must confirm NEXT_SESSION independently (weekend/holiday
arithmetic is insufficient).
Optional: add --frozen-archive APPROVED_PRIVATE_ARCHIVE.zip to the capture
command. Without this argument, a 64-digit hash is only an unverified reference
and frozen-rule evidence remains false. With the option, before any official
fetch the tool now verifies both the full private ZIP SHA256 and every member
named by data/r25_frozen_rules.json, including the frozen backtest script,
and requires exactly 15 frozen signal names. A self-declared manifest or hash
is still not independently authenticated approval, and neither proves when
those rules were originally frozen. Every record stays PIT_BLOCKED.
 The capture checks the session-specific OHLC and
turnover response, enforces exact two-source closing-price agreement, and
writes both source bodies, receipts, and their SHA256 to a new unique folder
outside this Git checkout. No paid endpoint, schedule, Secrets, Release, state
or publication workflow is used. No historical day is backdated.

A new receipt qualifies at most as evidence of retrieval before the next
opening. The script deliberately NEVER sets PIT-qualified to true, cannot
generate trading advice, and does not claim market index prices are directly
tradable. Independent durable timestamp anchoring, proven original source
publication/version timing, verified exchange calendar, a pre-outcome frozen
signal decision, genuinely future matured outcomes and an executable
instrument/cost model all require separate review. Until then both historical
PIT and true out-of-sample strategy validity remain BLOCKED.


## Tamper-evident local observation capsule (manual, not PIT)

Each successful prospective capture now writes the two raw TWSE bodies, two
complete HTTP receipts, and its PIT_BLOCKED status into a uniquely named
staging directory. It cross-checks those five files, creates a deterministic
SEAL.json file with their SHA256 digests, validates the seal, then atomically
renames the staging directory into its final private location. A failed
validation removes the staging directory; older completed captures are not
overwritten. The command prints local_seal_sha256 for separate safekeeping.

Recheck a capsule later:

    python3 research/rebound_history/capture_seal.py PRIVATE_CAPSULE_DIRECTORY --seal-sha256 PREVIOUSLY_RETAINED_SEAL_SHA256

The checker rejects missing, unexpected, symlinked, size-over-limit or
tampered files, inconsistent TWSE closing prices, unapproved status labels,
and receipt/session mismatches. The optional expected digest must be
previously recorded separately; merely retaining an unanchored local file
and digest together is not independent tamper or time attestation.

This is LOCAL_INTEGRITY_ONLY_PIT_BLOCKED, **not proof of the original
publication time, durable external timestamp or an actual pre-outcome
forecast**. A future human/independent audit must provide an external
timestamp anchor and original source availability proof before considering
any PIT candidate. No schedule, Secrets, public data or live deployment
are created by this feature.


## Evidence and decision review hardening

Calendar capture now follows the official form's `date=YYYY0101` parameter.
The historical `queryYear` request could return the server's default year.
Retain those original responses as excluded evidence. New calendar captures
must pass the existing response-year check before use.

Prospective source receipts must match one of the exact reviewed TWSE endpoint
formats for that observation session, including the effective URL. Date identifiers must be canonical
YYYY-MM-DD. Ambiguous JSON with duplicate keys or non-finite constants is
rejected. A local seal rejects flags that purport to certify an external time
anchor, calendar authenticity, publication time or pre-outcome signal. Frozen
archive verification also rejects duplicate signal identifiers and ambiguous
manifest JSON.

`forward_review.py` adds an offline review step that binds a separately pinned
plan, full civil-date calendar, ordered capsule list and the original frozen
archive. Generate a plan with `make_plan`, serialize it with `canonical`, and
retain its digest separately before the first observation. The calendar must
supply every civil date, a TRADING_SESSION/CLOSED classification and a source
evidence digest per row. The checker establishes internal consistency only.
Those references still need independent human source review.

The decision CLI takes PLAN PLAN_SHA CALENDAR CALENDAR_SHA CAPSULE_LIST
CAPSULE_LIST_SHA FROZEN_ARCHIVE DECISION_UTC NEW_PRIVATE_OUTPUT. All JSON inputs
use `canonical` bytes. Every capsule-list entry supplies directory and a
separately retained seal_sha256. It rejects a missing session, changed plan,
wrong source month, incomplete capture at the decision cutoff, future market
date and a decision made after the next session has opened. It uses only
the session row from each pinned capture. It never merges later monthly
response versions into earlier observations or silently loads retrospective
warmup. Missing warmup and absent chip inputs stay unknown.

The resulting private record stores 15 unchanged predicates, all seven fixed
horizons, input pins and a decision timestamp. Exclusive output creation
requires revisions to use new filenames. It contains no future outcomes.
Source-publication proof, calendar authenticity, external registration time
and genuine sample-out maturation remain separate review requirements.
Local timestamps can be forged by a caller with control of the files or
fetcher. Whole-directory deletion or coordinated rollback cannot be detected
without an independently retained highest accepted record. This tool is not
an external time service or immutable storage.


## Reviewed TWSE route compatibility and 2026-11-20 provenance

The original TWSE OHLC path `/indicesReport/MI_5MINS_HIST` remains
recognized for `date=YYYYMM01`. Its reviewed official successor
`/rwd/zh/TAIEX/MI_5MINS_HIST` permits `date=YYYYMMDD` matching the
requested session or `date=YYYYMM01` for that same month. Turnover remains
`/exchangeReport/FMTQIK?response=json&date=YYYYMM01`. The source URL
and HTTP redirect target are checked **independently**, and both must use
HTTPS, host `www.twse.com.tw` exactly, a reviewed path and exactly one
`response=json` plus exactly one session-matching `date` parameter.
Additional/duplicated query keys, unrelated same-host endpoints, host aliases,
URL fragments, other months and invalid dates are rejected. Receipt bytes
and the original requested/effective URLs are never rewritten during review.

This compatibility change permits *integrity validation* of an already
sealed 2026-11-20 one-signal observation whose OHLC request used the
reviewed official RWD path. It does **not** certify its source publication
time, external timestamp, calendar status or frozen rule identity. The
observation's saved `frozen_rule_archive_sha256` differs from the
recovered full 15-signal research rules ZIP, whose complete original
bytes are pinned independently. `forward_review.build_decision` rejects
that mismatch. The earlier single `day_drop3` observation must remain
separate, `DESCRIPTIVE_ONLY`, and not be counted in the 15-predicate
pre-registered OOS population. No historical PIT qualification changes.


## Separate day_drop3 T+1 observation after an actual next session

Manual-only command `single_signal_outcome.py` reconciles the separately
sealed 2026-11-20 one-signal event ZIP with an independently pinned
future **official two-source** outcome capsule. It MUST NOT run before
the actual next trading session has closed and the TWSE rows are available.
Prepare the future capsule with `forward_capture.py` outside the Git tree
using the unchanged claimed rule-reference SHA from the source event.
Retain the returned outcome `local_seal_sha256` separately.
Since no original full rules ZIP is pinned for the old one-signal event,
do not pass an unrelated recovered R3.6 frozen ZIP to imply verification.

Example using already obtained private files (placeholders are not passwords):

```sh
python3 research/rebound_history/single_signal_outcome.py \
  /private/REBOUND-PROSPECTIVE-20261120.zip \
  361ee487f2c721531e19bfde3c8cb426f3300ca6f800952b3e5151e8fc49fd92 \
  /private/2026-11-23/<captured-unique-directory> \
  <independently-retained-outcome-local-seal-sha256> \
  /private/t1-day-drop3-report.json
```

The verification rechecks the original eight ZIP members, whole-ZIP SHA256,
the five-file local seal, receipt/source consistency, both official closes,
the registered -3% event calculation, exact next-session date, and the
separately retained seal hash of the later observation. It produces two
**distinct** descriptive index changes: next-session open-to-close and
signal-day close-to-next-session close, each rounded to six decimal places.
Missing future reports, altered receipts, wrong pins, conflicting source
closes and a different frozen-rule reference fail closed. Output uses
exclusive creation outside the public Git repository.

This does **not** establish a source's first-publication time, an
independent cryptographic timestamp, calendar authenticity, execution
prices, or predictive validity. The index itself is not directly tradable.
The 3/5/10/20/40/60-session outcomes remain unobserved; the one-signal
event remains `DESCRIPTIVE_ONLY_PIT_BLOCKED` and outside the 15-signal
study, regardless of its T+1 price change.
