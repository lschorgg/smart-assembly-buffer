# Code documentation

## Architecture

The Pico samples two HX711 interfaces and performs threshold-based state detection. It emits newline-delimited JSON over USB. A background reader on the laptop parses these messages into a SQLite-backed store. A local HTTP server provides the HTML interface and JSON/CSV endpoints. The browser polls the server; no cloud service or Wi-Fi is used by this implementation.

## Firmware: pico/main.py

| Element | Responsibility |
| --- | --- |
| `plates` | Per-position pins, distinct PIO state machines 0/1, LED, factor and runtime state |
| `now_ms()` | Accumulate elapsed Pico milliseconds using `ticks_diff` |
| `send()` | Increment global and per-position sequence counters; output a SAB2 JSON line |
| `screen()` | Draw two lines; disable further OLED writes after an OSError |
| `status_screen()` | Map both position states to Free, Occupied or ERROR |
| `sensor_error()` | Latch the affected sensor fault, turn its LED off, emit an error packet |
| Startup | Initialise display and sensors; determine each sensor's zero point |
| Main loop | Read each healthy sensor, convert weight, confirm threshold transitions, send samples |
| Cleanup | Turn both LEDs off when execution exits |

Each position maintains `zero`, `occupied`, `streak`, `state_ms`, `plate_seq`, `fault` and `error`. A sensor fault disables only that sensor until restart; faults are reported again approximately once per second. An outer program exception stops the overall loop. A failed OLED does not intentionally stop weighing.

The loop uses one `read()` per healthy sensor, not `read_average()`. A threshold transition requires two consecutive qualifying samples. Its timestamp is recorded on confirmation, not at the first physical contact. Messages are sent before a potentially slow display update. The display is updated on state changes or newly detected sensor faults, not continuously. The loop's 5 ms sleep is only one timing component; sensor reads, serial output and OLED transfers also contribute.

### Constants in this submitted version

| Setting | Value |
| --- | --- |
| `SCALE_FACTOR_1` | 429.16 |
| `SCALE_FACTOR_2` | 429.16, temporary |
| `PLATE_2_CALIBRATED` | False |
| Plate 1 calibrated flag | True, hard-coded |
| `ON_G` / `OFF_G` | 10 / 5 |
| `STABLE_READINGS` | 2 |
| OLED | SoftI2C GP0/GP1, 100 kHz, timeout 100000 µs, 0x3D, 128 × 64 |

Changing constants would be a firmware change and is outside this documentation-only package. The HTML threshold description is literal text: future threshold changes must also be reflected in the interface text.

## Serial protocol

Each message is a JSON object terminated by a newline. The firmware sends SAB2. The desktop parser also accepts legacy SAB1.

| Field | Meaning |
| --- | --- |
| `protocol` | `SAB2` for this firmware |
| `run` | Random identifier generated when the Pico program starts |
| `seq` | Global sequence across all messages from both positions |
| `plate` | Integer 1 or 2 |
| `plate_seq` | Per-position sequence across all messages for that position |
| `ms` | Pico uptime in milliseconds at sending |
| `kind` | `calibrating`, `sample`, `error` or `stopped` |
| `occupied` | Sample state, Boolean |
| `state_ms` | Time of most recent confirmed state change, or initial state time |
| `raw`, `zero` | Raw HX711 sample and startup baseline |
| `weight_g` | Converted weight rounded to two decimals, not guaranteed accuracy |
| `calibrated` | Firmware calibration flag |
| `display_ok` | Whether the OLED object is still enabled |
| `message` | Diagnostic string on error messages |

`display_ok` is a software availability flag, not proof that pixels were visually checked. A sample sent before a failing OLED write may still carry true. Non-JSON console output is ignored by the desktop reader.

## Desktop: laptop/app.py

### Store

`Store` owns the database and independent live state for positions 1 and 2, protected by a re-entrant lock. `accept()` validates protocol, plate identity, sequence/timestamp types, Boolean occupancy and finite numeric values. Duplicate `(run, seq)` samples are ignored.

Continuity is checked per position using `plate_seq` for SAB2. A run change, backward timestamp or sequence gap interrupts that position's current event. A changed state timestamp while an occupied event remains open also signals a missed transition. Calibration, stopped and error packets clear that position's live state and interrupt an active event.

`stale()` invalidates a position after more than four seconds without accepted measurements. `snapshot()` returns both positions, statistics and the latest 200 events. `stats()` counts only complete events. `export()` returns all selected table records as semicolon-separated UTF-8 CSV with a BOM; wall-clock date fields are ISO-formatted UTC.

### Event lifecycle and timing

| Status | Meaning | Included in duration statistics? |
| --- | --- | --- |
| `open` | Occupied; removal not yet observed | No |
| `complete` | Observed start and removal with accepted continuity and nonnegative duration | Yes |
| `partial` | Removal observed, but start was not fully observed | No |
| `interrupted` | Connection, sequence, sensor or application continuity lost | No |

A first received occupied sample opens an event with `partial=1`. A free-to-occupied transition after a previous free sample opens a fully observed event. At removal, duration is `(removal state_ms - start_ms) / 1000`. Wall-clock start is estimated from laptop receipt time minus Pico elapsed time since the transition; transport delays can affect this absolute time estimate. Duration uses Pico transition timestamps rather than browser timing.

Complete means complete **in the software's observation rules**; it does not certify the sensor signal, physical calibration or absence of contact faults.

### Reader and HTTP server

`Reader` manages a serial connection and background thread, accumulates bytes until newlines, parses JSON and forwards packets. Disconnecting interrupts active events while retaining data. Parsing errors are ignored; USB/storage errors are reported to the store. Port operations are serialised with a control lock.

`Handler` serves the UI and endpoints below. Host checks restrict requests to localhost/127.0.0.1 with the configured port; POST requests also check Origin when provided. The server binds to 127.0.0.1. It is a local prototype without user accounts, not a publicly deployable authenticated service.

| Method | Path | Result |
| --- | --- | --- |
| GET | `/` | Dashboard HTML |
| GET | `/api/ports` | Available serial port device names and descriptions |
| GET | `/api/state` | Live positions, statistics, recent events and connection port |
| POST | `/api/connect` | Connect using JSON `{"port":"COM6"}`; substitute actual port |
| POST | `/api/disconnect` | Close serial connection |
| GET | `/events.csv` | All event records |
| GET | `/samples.csv` | All saved measurements |

Command-line options: `--port` selects the HTTP port (default 8765), not the USB port; `--db` selects the database (default beside app.py).

## SQLite schema

| Table | Columns |
| --- | --- |
| `events` | id, plate, run, start, end, duration_s, start_ms, status, partial, last_seen |
| `samples` | id, received, plate, run, seq, ms, raw, weight_g, occupied |

`samples` has a uniqueness constraint on `(run, seq)`. Wall-clock fields are epoch seconds in SQLite; Pico fields ending in `_ms` and `ms` are elapsed milliseconds. Missing event end/duration values may be null.

Not all protocol metadata is persisted: `zero`, `calibrated`, `display_ok`, `plate_seq` and sample `state_ms` are not columns of `samples`. Calibration provenance cannot therefore be reconstructed from the measurement CSV alone. Store the exact source/configuration and experiment notes with exported data. There is no automatic retention limit or offline Pico replay buffer in this application.

## Browser: laptop/index.html

Plain HTML, CSS and JavaScript; no frontend build step. `ports()` loads devices; `action()` connects/disconnects; `update()` obtains state; `tick()` updates live labels and extrapolated duration; `history()` draws the table and duration bars. A new state request is scheduled 200 ms after the previous update finishes, not at a guaranteed fixed 5 Hz. Timer rendering runs every 100 ms. Requests have a three-second abort timeout; stale live readings are hidden after four seconds.

Statistics are per-position and combined across complete events. The history table is limited to the latest 200 events, while CSV exports include all records. The bar chart selects up to 12 complete events from that window. It is not an occupancy-over-time or overlap timeline. Browser dates use the viewer's timezone; CSV dates use UTC. Plate 2's false calibration flag produces the label “Estimated weight”.

## Diagnostic and external dependencies

`tempo_test.py` targets Plate 1 only (GP14/GP15, state machine 0), zeros over 20 reads and prints 60 readings with read durations and a 20 ms sleep. It is not a dashboard-compatible streaming replacement for main.py. Stop the main program before running a diagnostic.

`hx711_pio.py` and `ssd1306.py` are now included from the user's separately uploaded files, unchanged. The HX711 driver uses a 1 MHz PIO state machine, a one-second read timeout and signed raw-value conversion. It exposes read, averaging, filtering, tare and scale methods. main.py handles its own zero/factor conversion and calls read directly. The OLED driver exposes I2C and SPI classes; this project uses its I2C implementation, overriding the driver's default address with 0x3D.

Compatibility notes retained without code changes: the HX711 gain selection uses `is` comparisons with integer literals. The OLED driver uses `const` without an explicit import and the older `framebuf.FrameBuffer1` interface. These are details of the supplied baseline, not portable Python guarantees. Preserve the working MicroPython environment; a fresh firmware installation requires a hardware test. Syntax parsing does not validate runtime names or PIO execution. The desktop requirement is pyserial==3.5; other desktop imports are Python standard library modules.
