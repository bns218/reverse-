# trader-news fixtures

All synthetic: fictional companies and made-up headlines, in the layouts of
Yahoo Finance's headline RSS, Google News' search RSS and NSE's corporate
announcements RSS. `chart-DEMO.json` is a Yahoo chart answer with US bars
moved onto the NSE session. The NSE feed's exact field layout is an
assumption (company in `<title>`, subject after `|SUBJECT:` in
`<description>`, an IST `dd-Mon-yyyy hh:mm:ss` date): the parser is written
to tolerate other layouts, but it has not been checked against the live feed.
