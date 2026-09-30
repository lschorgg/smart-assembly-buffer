from machine import Pin
from hx711_pio import HX711
import time

scale = HX711(
    Pin(15, Pin.OUT, value=0),
    Pin(14, Pin.IN),
    state_machine=0
)

print("Waage leer lassen.")
time.sleep(3)
zero = scale.read_average(20)

print("JETZT Gegenstand auflegen und wieder entfernen.")

for _ in range(60):
    start = time.ticks_ms()
    raw = scale.read()
    read_ms = time.ticks_diff(time.ticks_ms(), start)
    weight = (raw - zero) / 429.16

    print("Lesedauer: {} ms | Gewicht: {:.1f} g".format(
        read_ms, weight
    ))

    time.sleep_ms(20)