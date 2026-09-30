"""Smart Assembly Buffer: local two-plate USB dashboard."""

import argparse
import csv
import io
import json
import math
import sqlite3
import threading
import time

from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(
            path, check_same_thread=False
        )
        self.db.row_factory = sqlite3.Row

        # Compatible with the previous database.
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY,
                plate INTEGER,
                run TEXT,
                start REAL,
                end REAL,
                duration_s REAL,
                start_ms INTEGER,
                status TEXT,
                partial INTEGER,
                last_seen REAL
            );

            CREATE TABLE IF NOT EXISTS samples(
                id INTEGER PRIMARY KEY,
                received REAL,
                plate INTEGER,
                run TEXT,
                seq INTEGER,
                ms INTEGER,
                raw REAL,
                weight_g REAL,
                occupied INTEGER,
                UNIQUE(run, seq)
            );

            UPDATE events
            SET status='interrupted'
            WHERE status='open';
        """)
        self.db.commit()

        self.plates = {
            1: self.empty(),
            2: self.empty(),
        }
        self.message = "Connect the Pico and select its USB port."

    @staticmethod
    def empty(message="Waiting for measurements."):
        return {
            "live": None,
            "current": None,
            "last": None,
            "last_mono": None,
            "message": message,
        }

    def interrupt(self, message, plate=None):
        with self.lock:
            targets = (plate,) if plate is not None else (1, 2)

            for number in targets:
                current = self.plates[number]["current"]

                if current is not None:
                    self.db.execute(
                        "UPDATE events SET status='interrupted' WHERE id=?",
                        (current,),
                    )

                self.plates[number] = self.empty(message)

            self.db.commit()

            if plate is None:
                self.message = message

    def stale(self):
        with self.lock:
            for number, state in list(self.plates.items()):
                last = state["last_mono"]

                if last is not None and time.monotonic() - last > 4:
                    self.interrupt(
                        "No recent data. Check the sensor and USB connection.",
                        number,
                    )

    def accept(self, packet, received=None):
        if not isinstance(packet, dict):
            return

        if packet.get("protocol") not in ("SAB1", "SAB2"):
            return

        plate = packet.get("plate")

        if type(plate) is not int or plate not in (1, 2):
            return

        received = time.time() if received is None else received

        with self.lock:
            kind = packet.get("kind")

            if kind != "sample":
                messages = {
                    "calibrating": "Setting zero: keep BOTH plates empty.",
                    "stopped": "Pico program stopped.",
                    "error": "Sensor error. Check wiring with USB disconnected, then restart.",
                }

                if kind in messages:
                    self.interrupt(messages[kind], plate)
                return

            try:
                run = packet["run"]
                seq = packet["seq"]
                ms = packet["ms"]
                state_ms = packet["state_ms"]

                local_seq = (
                    packet["plate_seq"]
                    if packet["protocol"] == "SAB2"
                    else seq
                )

                if not isinstance(run, str) or not run or len(run) > 100:
                    return

                if any(
                    type(value) is not int or value < 0
                    for value in (seq, local_seq, ms, state_ms)
                ):
                    return

                if state_ms > ms:
                    return

                if type(packet["occupied"]) is not bool:
                    return

                if not all(
                    math.isfinite(float(packet[key]))
                    for key in ("weight_g", "raw")
                ):
                    return

            except (KeyError, TypeError, ValueError, OverflowError):
                return

            duplicate = self.db.execute(
                "SELECT 1 FROM samples WHERE run=? AND seq=?",
                (run, seq),
            ).fetchone()

            if duplicate:
                return

            self.stale()

            state = self.plates[plate]
            previous = state["last"]

            # Check continuity separately for each plate.
            if previous and (
                run != previous["run"]
                or ms < previous["ms"]
                or local_seq != previous["_local_seq"] + 1
            ):
                self.interrupt("Measurement sequence interrupted.", plate)
                state = self.plates[plate]
                previous = None

            if (
                state["current"] is not None
                and packet["occupied"]
                and previous
                and state_ms != previous["state_ms"]
            ):
                self.interrupt("An occupancy transition was missed.", plate)
                state = self.plates[plate]
                previous = None

            if packet["occupied"] and state["current"] is None:
                partial = int(
                    previous is None or previous["occupied"]
                )
                start = received - (ms - state_ms) / 1000

                cursor = self.db.execute(
                    """
                    INSERT INTO events(
                        plate, run, start, start_ms,
                        status, partial, last_seen
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        plate, run, start, state_ms,
                        "open", partial, received,
                    ),
                )
                state["current"] = cursor.lastrowid

            elif not packet["occupied"] and state["current"] is not None:
                event = self.db.execute(
                    "SELECT * FROM events WHERE id=?",
                    (state["current"],),
                ).fetchone()

                duration = (state_ms - event["start_ms"]) / 1000
                valid = duration >= 0 and not event["partial"]

                self.db.execute(
                    """
                    UPDATE events
                    SET end=?, duration_s=?, status=?, last_seen=?
                    WHERE id=?
                    """,
                    (
                        event["start"] + duration if duration >= 0 else None,
                        duration if valid else None,
                        "complete" if valid else "partial",
                        received,
                        state["current"],
                    ),
                )
                state["current"] = None

            if state["current"] is not None:
                self.db.execute(
                    "UPDATE events SET last_seen=? WHERE id=?",
                    (received, state["current"]),
                )

            self.db.execute(
                """
                INSERT INTO samples(
                    received, plate, run, seq,
                    ms, raw, weight_g, occupied
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    received, plate, run, seq, ms,
                    packet["raw"], packet["weight_g"],
                    int(packet["occupied"]),
                ),
            )
            self.db.commit()

            state["last"] = dict(packet, _local_seq=local_seq)
            state["last_mono"] = time.monotonic()
            state["live"] = dict(
                packet,
                received=received,
                elapsed_s=(
                    (ms - state_ms) / 1000
                    if packet["occupied"] else 0
                ),
            )
            state["message"] = (
                "Receiving measurements."
                if packet.get("display_ok", True)
                else "Receiving measurements; OLED unavailable."
            )
            self.message = "Measurements are being saved on this laptop."

    def stats(self, plate=None):
        query = """
            SELECT COUNT(*) AS count,
                   AVG(duration_s) AS average,
                   MAX(duration_s) AS longest
            FROM events WHERE status='complete'
        """

        if plate is not None:
            query += " AND plate=?"
            parameters = (plate,)
        else:
            parameters = ()

        return dict(self.db.execute(query, parameters).fetchone())

    def snapshot(self):
        with self.lock:
            self.stale()
            plates = []

            for number, state in self.plates.items():
                live = dict(state["live"]) if state["live"] else None

                if live:
                    live["age_s"] = max(
                        0, time.monotonic() - state["last_mono"]
                    )

                plates.append({
                    "plate": number,
                    "live": live,
                    "message": state["message"],
                    "stats": self.stats(number),
                })

            events = [
                dict(row)
                for row in self.db.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT 200"
                )
            ]

            return {
                "plates": plates,
                "events": events,
                "stats": self.stats(),
                "message": self.message,
            }

    def export(self, samples=False):
        with self.lock:
            query = (
                "SELECT * FROM samples ORDER BY id"
                if samples else
                """SELECT id,plate,run,start,end,duration_s,
                          status,partial,last_seen
                   FROM events ORDER BY id"""
            )

            cursor = self.db.execute(query)
            names = [column[0] for column in cursor.description]

            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            writer.writerow(names)

            for row in cursor:
                values = list(row)

                for name in ("received", "start", "end", "last_seen"):
                    if name in names:
                        index = names.index(name)
                        if values[index] is not None:
                            values[index] = datetime.fromtimestamp(
                                values[index], timezone.utc
                            ).isoformat()

                writer.writerow(values)

            return ("\ufeff" + output.getvalue()).encode("utf-8")


class Reader:
    def __init__(self, store):
        self.store = store
        self.thread = None
        self.stop = threading.Event()
        self.port = None
        self.control = threading.Lock()

    def disconnect(self):
        self.stop.set()

        if self.thread:
            self.thread.join(timeout=3)

            if self.thread.is_alive():
                raise ValueError("USB reader is stopping. Try again shortly.")

        self.port = None
        self.store.interrupt(
            "Disconnected. Previously saved records are retained."
        )

    def connect(self, port):
        with self.control:
            self.disconnect()

            if port not in [
                item.device for item in list_ports.comports()
            ]:
                raise ValueError("Port unavailable. Refresh the port list.")

            try:
                link = serial.Serial(port, 115200, timeout=0.1)
            except serial.SerialException as error:
                raise ValueError(
                    "Cannot open port. Disconnect MicroPico and other "
                    "serial consoles first. " + str(error)
                )

            self.stop = threading.Event()
            self.port = port
            self.store.message = "Connected. Waiting for Pico measurements."

            self.thread = threading.Thread(
                target=self.read,
                args=(link, self.stop),
                daemon=True,
            )
            self.thread.start()

    def read(self, link, stop):
        buffer = b""

        try:
            while not stop.is_set():
                buffer += link.read(
                    max(1, min(link.in_waiting, 4096))
                )

                if len(buffer) > 65536:
                    buffer = b""

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)

                    try:
                        self.store.accept(
                            json.loads(line.decode("utf-8"))
                        )
                    except (ValueError, UnicodeError):
                        pass

                self.store.stale()

        except (serial.SerialException, OSError, sqlite3.Error):
            self.store.interrupt(
                "Reading or saving failed. Check USB and disk space, "
                "then reconnect."
            )

        finally:
            link.close()
            self.port = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(
        self,
        body,
        content="application/json; charset=utf-8",
        status=200,
        filename=None,
    ):
        if not isinstance(body, bytes):
            body = json.dumps(body, allow_nan=False).encode()

        self.send_response(status)
        self.send_header("Content-Type", content)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))

        if filename:
            self.send_header(
                "Content-Disposition",
                'attachment; filename="' + filename + '"',
            )

        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        port = str(self.server.server_port)
        return self.headers.get("Host") in (
            "127.0.0.1:" + port,
            "localhost:" + port,
        )

    def do_GET(self):
        if not self.allowed():
            return self.respond(
                {"error": "Host not allowed"}, status=403
            )

        path = urlparse(self.path).path

        if path == "/":
            self.respond(
                (ROOT / "index.html").read_bytes(),
                "text/html; charset=utf-8",
            )
        elif path == "/api/state":
            self.respond(dict(
                self.server.store.snapshot(),
                port=self.server.reader.port,
            ))
        elif path == "/api/ports":
            self.respond([
                {"device": port.device, "description": port.description}
                for port in list_ports.comports()
            ])
        elif path in ("/events.csv", "/samples.csv"):
            self.respond(
                self.server.store.export(path == "/samples.csv"),
                "text/csv; charset=utf-8",
                filename=path[1:],
            )
        else:
            self.respond({"error": "Not found"}, status=404)

    def do_POST(self):
        port = str(self.server.server_port)
        origin = self.headers.get("Origin")

        if not self.allowed() or (
            origin and origin not in (
                "http://127.0.0.1:" + port,
                "http://localhost:" + port,
            )
        ):
            return self.respond(
                {"error": "Access denied"}, status=403
            )

        try:
            size = int(self.headers.get("Content-Length", "0"))

            if size < 0 or size > 2048:
                raise ValueError("Invalid request size")

            packet = json.loads(self.rfile.read(size) or b"{}")

            if self.path == "/api/connect":
                self.server.reader.connect(packet.get("port"))
            elif self.path == "/api/disconnect":
                with self.server.reader.control:
                    self.server.reader.disconnect()
            else:
                return self.respond(
                    {"error": "Not found"}, status=404
                )

            self.respond({"ok": True})

        except (ValueError, TypeError, AttributeError) as error:
            self.respond({"error": str(error)}, status=400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=str(ROOT / "buffer.sqlite3"))
    args = parser.parse_args()

    store = Store(args.db)
    reader = Reader(store)

    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), Handler
    )
    server.store = store
    server.reader = reader

    print("Dashboard: http://127.0.0.1:" + str(args.port), flush=True)
    print("Database:", args.db, flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        reader.disconnect()
        server.server_close()
        store.db.close()


if __name__ == "__main__":
    main()