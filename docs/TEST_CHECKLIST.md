# Verification and demonstration checklist

These are checks to perform on the physical prototype, not claims that this documentation task executed them. Record date, firmware copy, factors, object/reference mass, observations and any failures.

| Check | Expected result | Evidence to record |
| --- | --- | --- |
| Startup with both empty | Both positions become Free with near-zero readings | Startup duration, empty readings |
| Load Plate 1 only | LED 1 and P1 occupied; P2 remains free | Screenshot and event export |
| Load Plate 2 only | LED 2 and P2 occupied; P1 remains free | Screenshot; note estimated weight |
| Load both | Both show occupied and separate timers | Screenshot |
| Remove only Plate 1 | P1 completes; P2 remains occupied | Two event rows / timestamps |
| Remove Plate 2 | P2 completes independently | Event export |
| Repeat placement/removal | No missed or spurious state changes under normal handling | Trial count and failures, not just a successful example |
| Connect when already occupied | Start-not-observed record, excluded from complete statistics | Status and export |
| Disconnect during occupancy | Event interrupted; history retained | Interrupted row |
| Close/reopen app | Saved records remain; previous open events interrupted | Before/after history |
| Export | Event and measurement CSV open correctly; UTC dates understood | Saved CSVs |
| Known reference mass | Repeatable empty/loaded values for each plate | Reference mass, repeats, deviations |

Do not deliberately pull individual sensor wires while powered. For fault investigations, unplug USB before changing connections. A movement-sensitive reading is a hardware reliability issue to repair before relying on event records.

For response time, compare physical placement/removal to LED, OLED and browser separately, ideally with a timestamped video. The diagnostic's sensor read duration alone is not end-to-end latency. Do not describe 0.1-second display increments as 0.1-second measurement accuracy.

For a clean experiment, start with a new database using `--db`; keep your historical database backed up outside this repository. Include both successful and failed trials in your evaluation notes.
