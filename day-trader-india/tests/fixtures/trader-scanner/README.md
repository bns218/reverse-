# trader-scanner fixtures

Everything here is synthetic test data, not real NSE data:

- `EQUITY_L-sample.csv`, `ind_sample50list.csv`: fictional companies in the
  column layouts of NSE's `EQUITY_L.csv` and a niftyindices.com constituents
  CSV (the ISINs are made up).
- The Yahoo chart files (`wall5m-*`, `*spark*`, `DEMO-*`) are real US bars
  moved onto the NSE session (9:30 ET -> 9:15 IST), with NSE-holiday days
  dropped and every symbol renamed (TSLA -> DEMO, others -> `<TICKER>SYN`).
  The "live" Oct 20 files are dated Oct 21, because Oct 20 2026 is an NSE
  holiday (Dussehra).
