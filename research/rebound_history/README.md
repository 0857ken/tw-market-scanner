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
