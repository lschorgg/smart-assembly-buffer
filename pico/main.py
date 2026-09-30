# Smart Assembly Buffer - TWO plates
# Run on the Pico with MicroPython.
# Keep hx711_pio.py and ssd1306.py on the Pico.

from machine import Pin, SoftI2C
from hx711_pio import HX711
import ssd1306
import time
import json
import os
import binascii

SCALE_FACTOR_1 = 429.16
SCALE_FACTOR_2 = 429.16  # Temporary: calibrate Plate 2 separately.
PLATE_2_CALIBRATED = False

ON_G = 10
OFF_G = 5
STABLE_READINGS = 2

run = binascii.hexlify(os.urandom(8)).decode()
seq = 0
uptime = 0
last_tick = time.ticks_ms()
oled = None

plates = [
    {
        "id": 1,
        "dt": 14,
        "sck": 15,
        "sm": 0,
        "led": Pin(4, Pin.OUT, value=0),
        "factor": SCALE_FACTOR_1,
        "calibrated": True,
    },
    {
        "id": 2,
        "dt": 16,
        "sck": 17,
        "sm": 1,
        "led": Pin(5, Pin.OUT, value=0),
        "factor": SCALE_FACTOR_2,
        "calibrated": PLATE_2_CALIBRATED,
    },
]

for plate in plates:
    plate.update(
        scale=None,
        zero=0,
        occupied=False,
        streak=0,
        state_ms=0,
        plate_seq=0,
        fault=False,
        error="",
    )


def now_ms():
    global uptime, last_tick
    tick = time.ticks_ms()
    uptime += time.ticks_diff(tick, last_tick)
    last_tick = tick
    return uptime


def send(plate, kind, **values):
    global seq
    seq += 1
    plate["plate_seq"] += 1

    packet = {
        "protocol": "SAB2",
        "run": run,
        "seq": seq,
        "plate": plate["id"],
        "plate_seq": plate["plate_seq"],
        "ms": now_ms(),
        "kind": kind,
    }
    packet.update(values)
    print(json.dumps(packet))


def screen(line1, line2=""):
    global oled

    if oled is not None:
        try:
            oled.fill(0)
            oled.text(line1, 0, 16)
            oled.text(line2, 0, 34)
            oled.show()
        except OSError:
            oled = None


def status_screen():
    lines = []

    for plate in plates:
        if plate["fault"]:
            state = "ERROR"
        elif plate["occupied"]:
            state = "Occupied"
        else:
            state = "Free"

        lines.append("P{}: {}".format(plate["id"], state))

    screen(lines[0], lines[1])


def sensor_error(plate, error):
    # A faulty sensor stays disabled until the Pico is restarted.
    # The other sensor can continue working.
    plate["fault"] = True
    plate["error"] = str(error)
    plate["led"].off()
    send(plate, "error", message=plate["error"])


try:
    try:
        i2c = SoftI2C(
            sda=Pin(0),
            scl=Pin(1),
            freq=100_000,
            timeout=100_000,
        )
        oled = ssd1306.SSD1306_I2C(
            128, 64, i2c, addr=0x3D
        )
    except OSError:
        oled = None

    screen("Keep BOTH", "plates empty")

    for _ in range(6):
        for plate in plates:
            send(plate, "calibrating")
        time.sleep_ms(500)

    for plate in plates:
        try:
            if not plate["factor"]:
                raise ValueError("Scale factor must not be zero")

            plate["scale"] = HX711(
                Pin(plate["sck"], Pin.OUT, value=0),
                Pin(plate["dt"], Pin.IN),
                state_machine=plate["sm"],
            )
        except Exception as error:
            sensor_error(plate, error)

    # Determine a separate zero point for each plate.
    for _ in range(20):
        for plate in plates:
            if plate["fault"]:
                continue

            try:
                plate["zero"] += plate["scale"].read()
                send(plate, "calibrating")
            except Exception as error:
                sensor_error(plate, error)

    for plate in plates:
        plate["zero"] /= 20
        plate["state_ms"] = now_ms()

    status_screen()
    last_error_report = now_ms()

    while True:
        display_dirty = False

        for plate in plates:
            if plate["fault"]:
                continue

            try:
                raw = plate["scale"].read()
            except Exception as error:
                sensor_error(plate, error)
                display_dirty = True
                continue

            weight = (
                raw - plate["zero"]
            ) / plate["factor"]

            if plate["occupied"]:
                change = weight <= OFF_G
            else:
                change = weight >= ON_G

            plate["streak"] = (
                plate["streak"] + 1 if change else 0
            )

            if plate["streak"] >= STABLE_READINGS:
                plate["occupied"] = not plate["occupied"]
                plate["state_ms"] = now_ms()
                plate["streak"] = 0
                plate["led"].value(plate["occupied"])
                display_dirty = True

            # Send data before the slower OLED update.
            send(
                plate,
                "sample",
                occupied=plate["occupied"],
                state_ms=plate["state_ms"],
                raw=raw,
                zero=plate["zero"],
                weight_g=round(weight, 2),
                calibrated=plate["calibrated"],
                display_ok=oled is not None,
            )

        # Update the display only when a state changes.
        if display_dirty:
            status_screen()

        if now_ms() - last_error_report >= 1000:
            for plate in plates:
                if plate["fault"]:
                    send(
                        plate,
                        "error",
                        message=plate["error"],
                    )
            last_error_report = now_ms()

        time.sleep_ms(5)

except KeyboardInterrupt:
    for plate in plates:
        send(plate, "stopped")
    screen("Stopped")

except Exception as error:
    for plate in plates:
        send(plate, "error", message=str(error))
    screen("Program error")

finally:
    for plate in plates:
        plate["led"].off()
