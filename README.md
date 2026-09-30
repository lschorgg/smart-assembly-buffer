# Smart Assembly Buffer

## Two-position occupancy monitoring prototype

This project detects occupancy at two weighing positions, controls one LED per position, shows both states on an OLED, and records measurements and occupancy durations in a local Windows dashboard.

This documentation describes **smart_buffer_komplett(3).zip**, supplied on 30 September 2026. The application source files and the two subsequently supplied driver files have not been modified. It documents the submitted implementation, not the separate calibration package proposed earlier.

## Start here

| File | Purpose |
| --- | --- |
| `pico/main.py` | MicroPython application for both positions |
| `pico/tempo_test.py` | Optional single-sensor timing diagnostic; not the main application |
| `laptop/app.py` | USB reader, event processing, SQLite storage and local HTTP server |
| `laptop/index.html` | English browser dashboard |
| `laptop/requirements.txt` | Desktop dependency: pyserial 3.5 |
| `laptop/buffer.sqlite3` | Created locally on first launch; excluded from this repository |
| `docs/CODE_DOCUMENTATION.md` | Architecture, functions, protocol and data model |
| `docs/TEST_CHECKLIST.md` | Repeatable checks and evidence to collect |
| `docs/HANDOVER.md` | Remaining tasks, dependencies and preservation notes |
| `.gitignore` | Excludes local environments, database files and caches |
| `pico/hx711_pio.py`, `pico/ssd1306.py` | Supplied HX711 and OLED drivers, unchanged |

## Included drivers and repository scope

The two supplied drivers are included under the exact import names `pico/hx711_pio.py` and `pico/ssd1306.py`. Only their download suffixes were removed; contents and notices are unchanged. Upload them alongside `main.py` to the Pico root when restoring firmware.

This GitHub package excludes the machine-specific virtual environment, the historical measurement database and the superseded START_HIER.md. Your original archive and documented backup retain those files. A fresh database is created by the app. For repository upload, extract this ZIP and upload the contents of `smart_buffer` so that README.md is at the repository root. This package has not been published to GitHub.

## Hardware and wiring

Hardware: Raspberry Pi Pico WH, two load cells with one HX711 each, two LEDs with individual series resistors, a 128 × 64 I2C OLED, breadboard and connecting wires.

The following mapping matches the firmware and the wiring described for this project. Physical pin numbers refer to the Pico header, **not** breadboard row numbers. Disconnect USB before changing wiring.

| Component | Connection | Pico GPIO / supply | Physical pin |
| --- | --- | --- | --- |
| HX711 1 | DT | GP14 | 19 |
| HX711 1 | SCK | GP15 | 20 |
| HX711 2 | DT | GP16 | 21 |
| HX711 2 | SCK | GP17 | 22 |
| Both HX711s | VCC | 3V3 OUT via positive rail | 36 |
| Both HX711s | GND | Common GND | 23 |
| OLED | SDA | GP0 | 1 |
| OLED | SCL | GP1 | 2 |
| OLED | VCC | 3V3 OUT via positive rail | 36 |
| OLED | GND | GND | 38 |
| LED 1 | Series resistor → anode | GP4 | 6 |
| LED 1 | Cathode | GND | 8 |
| LED 2 | Series resistor → anode | GP5 | 7 |
| LED 2 | Cathode | GND | 13 |

Each LED needs its own suitable series resistor; the planned project value was 220 Ω. Verify the actual fitted value rather than assuming it. Keep the existing load-cell-to-HX711 wiring; wire colours alone do not establish terminal identity. Loose fine wires are not reliable breadboard connections. Do not reuse a smoking or overheating assembly without inspection.

## Windows setup

Use the existing working installation if it already runs. Do not replace a working environment just to add documentation.

For a separate installation, extract the ZIP to a new folder. Open that folder in VS Code, choose **Terminal → New Terminal**, and change into its `laptop` folder. Replace the example path with the real location:

```powershell
cd "C:\path\to\smart_buffer\laptop"
py --version
py -m venv .venv_local
.\.venv_local\Scripts\python.exe -m pip install -r requirements.txt
.\.venv_local\Scripts\python.exe app.py
```

The local `.venv_local` is excluded by .gitignore. A Windows Python 3.14 installation was shown during project setup; a fresh installation has not been tested as part of this documentation task.

Open **http://127.0.0.1:8765/** in the browser. Keep the terminal running. Opening `index.html` directly does not start the server.

### Pico installation / upload

If the Pico already runs correctly, no firmware upload is needed for this documentation.

For a restore: first back up the working `main.py`, `hx711_pio.py` and `ssd1306.py` from the Pico. Use a Pico-compatible MicroPython installation and MicroPico in VS Code. Upload the project `main.py` and the backed-up driver files to the Pico filesystem root. Do not run this firmware with Windows Python. Do not upload the `laptop` folder or its virtual environment to the Pico.

Only one program can use the serial port at a time. Stop the dashboard with **Ctrl+C** before using MicroPico. After uploading, disconnect MicroPico before connecting the dashboard. COM6 was used in this project, but select the actual Pico port shown on your laptop.

## Normal operation

1. Leave both weighing positions empty, with their normal permanent platforms fitted.
2. Restart the Pico. Keep both positions empty throughout startup zeroing.
3. Start `app.py`, open the dashboard, select the Pico USB port and click **Connect**.
4. Wait until both positions show **Free** and measurements arrive before placing objects. Starting observation while already occupied produces an incomplete-start record.
5. Place an object on either position. Its LED and OLED line indicate occupancy; the dashboard shows that position's timer.
6. Remove the object. A fully observed event is stored with its duration.
7. Use **Export events CSV** or **Export measurements CSV** to save data for analysis.
8. Keep the laptop awake and the app connected during recording. After recording, disconnect and stop the app with Ctrl+C before backing up its database.

## Zeroing is not weight calibration

At every startup, the firmware waits approximately three seconds, then gathers **20 readings per sensor** to compute separate zero points. Total startup takes longer because sensor initialisation and readings also take time.

Weight is calculated as `(raw - zero) / factor`. The submitted code uses 429.16 for both factors. Plate 1 is marked calibrated in the code; this flag is not an independent calibration certificate. **Plate 2 is explicitly marked uncalibrated**, so the dashboard labels its weight as estimated. Automatic zeroing of Plate 2 still works; it does not determine a new scale factor.

Do not claim verified gram accuracy for Plate 2 without a separate known-mass calibration and repeatability check. No automatic known-mass calibration utility or saved calibration file is part of this submitted version. The working constants have deliberately not been changed.

## What the data means

Occupancy turns on after two consecutive readings at or above 10 g and turns off after two consecutive readings at or below 5 g. These are provisional physical thresholds where the scale factor is unverified. Between the thresholds, the previous state remains.

Durations describe **detected occupancy**, not component identity, productive work time or reasons for waiting. The two positions are processed separately but read sequentially. Browser refresh and displayed decimal seconds do not imply equivalent physical measurement accuracy.

The dashboard includes independent live cards, combined statistics, a duration bar chart and event history. This version does **not** implement a simultaneous-occupancy timeline. The chart shows up to 12 complete events drawn from the latest 200 history entries. Summary statistics include all complete events in the selected database, including older trials.

## Existing data and fresh sessions

No measurement database is included in this GitHub package. The app creates `laptop/buffer.sqlite3` on first launch and reuses it on later launches. Your historical records remain in your original project/archive.

To record a separate session without clearing an existing database, start:

```powershell
.\.venv_local\Scripts\python.exe app.py --db session_new.sqlite3
```

Use a new filename for each intentionally separate session. Stop the app before copying a database. Opening a database with this app changes previously open events to interrupted. Keep local backups and deliberately select any anonymised example CSVs you wish to publish; no measurement exports are included here.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Browser cannot open localhost | Start `app.py`; keep its terminal open; inspect its printed address and errors |
| COM port access denied | Disconnect MicroPico, other serial terminals and other dashboard instances |
| `No module named serial` | Install requirements using the same Python environment used to start the app |
| `No module named hx711_pio` / `ssd1306` | Restore the exact working driver file to the Pico root |
| Wrong empty weight | Restart with both positions empty; check stable contacts and mechanical loading |
| Values jump when wires move | Repair electrical connections before changing software or calibration |
| Plate 2 says estimated weight | Expected: its calibration flag is false in this source |
| OLED unavailable | Verify disconnected wiring; this source uses software I2C and address 0x3D |
| Sensor error persists | Repair with USB disconnected, then restart; failed sensors are latched off |
| No live data | Check USB/app/sensor; more than four seconds without samples invalidates live data |
| Dim LEDs | Inspect resistor values and connections; never bypass resistors or move GPIO wiring to 5 V |

## Documentation scope

Prepared from source inspection of the supplied ZIP. Preservation and syntax checks are documented in `docs/VERIFICATION.md`. No new physical hardware validation, brightness repair, calibration or performance measurement is claimed.
