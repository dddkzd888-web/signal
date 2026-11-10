# Ledger — implementation-plan.md
Pre-flight: enrich/match_signals output is consumed by scan service and chart; shared JSON fields match.
Ruling: execute directly under user's explicit start-development request; no additional approval — avoids repeating authorization.
Ruling: red upward column means BBUY per user formula; MACD positive bars remain optional — chart displays both to remove ambiguity.
Ruling: retain application in newly created local project on feature/volume-bbuy branch; no shared existing checkout needs another worktree.
Task 1: in progress.
Task 1: complete; 10 indicator tests passed; commit a1c2c63.
Task 2: complete; 21 tests passed including exchange early closes, cache persistence, invalid imports, failure status and cancellation; live integration pending frontend.
Ruling: core volume/BBUY requires max(30, volume window) bars, not 330 — user's latest screenshot requests core pair; 330-bar trend is marked as partial for new listings.
Task 3: in progress.

Task 3: complete; real-data browser verification, 20-symbol scan, CSV download, narrow layout, restart and 22 tests passed.
Final review: Important stale-signal and stale-chart findings reproduced RED then fixed GREEN. Minor wrong-chart display and saved-scan age were regraded user-visible and fixed. KDJ/RSI top labels and label toggles deferred as documented in verification.md.
Browser observed volume default step mismatch; changed step to .01, browser validity true and rule apply verified.
Final handoff: local server kept running; default settings restored; preview.jpg and verification summaries saved.
