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
