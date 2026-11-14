"""Eval asset: a build whose memory keeps growing until something stops it.

Stands in for a real runaway build without touching OCCT: it commits memory in
256 MB steps up to 5 GB and prints the running total.
"""
import cadquery as cq  # noqa: F401  (the real footprint a build starts from)

STEP_MB = 256
STOP_GB = 5.0

held = []
total = 0
print("allocating in 256 MB steps", flush=True)
while total < STOP_GB * 1024:
    held.append(bytearray(STEP_MB * 1024 * 1024))
    total += STEP_MB
    print(f"committed {total / 1024:.2f} GB", flush=True)
print("reached the 5 GB stop", flush=True)
print("DONE", flush=True)
