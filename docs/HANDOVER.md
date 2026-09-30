# Handover

This repository package contains the exact application source from smart_buffer_komplett(3).zip and the subsequently supplied HX711 and SSD1306 drivers. Driver filenames have been normalised to their import names; file contents are unchanged.

## Before submission

1. Confirm that these files match the copies running on the Pico. No remote hardware comparison was possible here.
2. Record the actual MicroPython and desktop Python versions, resistor values and physical test results.
3. Document Plate 2's provisional factor honestly: startup zeroing does not perform known-mass calibration.
4. Check consistency with the presentation: this index.html implements duration bars, not a combined occupancy timeline.
5. Choose whether selected example CSVs should be published. Raw database history is intentionally excluded from this package, and remains in your earlier archives.
6. Before public redistribution, confirm the original source/licence of the SSD1306 driver. Its supplied file credits Adafruit but includes no full licence text. The HX711 file includes an MIT notice; retain it. No blanket project licence has been invented.

## GitHub package contents

Source, drivers, README, technical documentation, test checklist and .gitignore are included. Local virtual environments, database files, caches and the obsolete START_HIER.md are omitted. There is no new calibration utility and no change to factors, thresholds, pin assignments, timings or dashboard behaviour.

This is a local USB application. Uploading its source to GitHub does not host the Python server or enable browser access to the Pico. Continue running app.py on the laptop.
