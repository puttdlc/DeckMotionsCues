#!/usr/bin/env python3
"""Off-hardware harness for the Motion Cues pipeline.

Three jobs:

* ``preview``   - render what the dots will look like, as a PNG.
* ``trace``     - print the motion response to a chosen motion profile.
* ``benchmark`` - measure the CPU cost of the sensor and render paths.

The point is that everything except the X11 blit itself can be exercised
without a Steam Deck, so the numbers and the behaviour are measured rather
than assumed.

    python tools/simulate.py benchmark
    python tools/simulate.py trace --profile city --seconds 20
    python tools/simulate.py preview --out preview.png --displace 20 -14
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
import time
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "py_modules"))

from motioncues import config as config_module  # noqa: E402
from motioncues import layout, sensors, sprites  # noqa: E402
from motioncues.engine import MotionEngine  # noqa: E402
from motioncues.overlay import TILE_PADDING  # noqa: E402

SCREEN = (1280, 800)


def build_config(args: argparse.Namespace) -> dict:
    cfg = config_module.validate({})
    if args.preset:
        cfg = config_module.merge(cfg, config_module.BUILTIN_PRESETS[args.preset])
    cfg["mode"] = args.mode
    return cfg


# --------------------------------------------------------------------------
def cmd_preview(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    appearance = cfg["appearance"]
    sprite = sprites.sprite_for(appearance)
    points = layout.dot_positions(*SCREEN, appearance)
    dx, dy = args.displace
    moved = [(x + dx, y + dy) for x, y in points]

    buffer = sprites.compose_preview(SCREEN[0], SCREEN[1], moved, sprite)
    sprites.write_png(args.out, SCREEN[0], SCREEN[1], buffer)
    print(f"wrote {args.out}: {len(points)} dots, "
          f"{sprite.width}x{sprite.height} px tiles, displaced ({dx}, {dy})")
    return 0


# --------------------------------------------------------------------------
def cmd_trace(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    engine = MotionEngine(cfg)
    source = sensors.SyntheticSensor(args.profile, rate_hz=args.rate, realtime=False)

    dt = 1.0 / args.rate
    t = 0.0
    rows: List[tuple] = []
    engaged_at = None

    for _ in range(int(args.rate * args.seconds)):
        t += dt
        sample = source.sample_at(t)
        state = engine.ingest(t, sample.accel, sample.gyro)
        if engaged_at is None and state.engaged:
            engaged_at = t
        rows.append((t, state.dx, state.dy, state.alpha, state.engaged,
                     state.accel_energy, state.gyro_energy))

    step = max(1, len(rows) // args.lines)
    print(f"profile={args.profile} preset={args.preset or 'defaults'} mode={cfg['mode']}")
    print(f"{'t':>7} {'dx':>8} {'dy':>8} {'alpha':>6} {'eng':>4} "
          f"{'accelE':>8} {'gyroE':>7}")
    for row in rows[::step]:
        print(f"{row[0]:7.2f} {row[1]:8.2f} {row[2]:8.2f} {row[3]:6.2f} "
              f"{str(row[4]):>4} {row[5]:8.4f} {row[6]:7.2f}")

    radii = [math.hypot(row[1], row[2]) for row in rows if row[0] > 8.0]
    if radii:
        print()
        print(f"travel: mean {statistics.mean(radii):.1f} px, "
              f"p95 {sorted(radii)[int(0.95 * len(radii))]:.1f} px, "
              f"max {max(radii):.1f} px "
              f"(limit {cfg['motion']['max_travel']:.0f} px)")
    print(f"automatic mode engaged: "
          f"{f'after {engaged_at:.1f} s' if engaged_at else 'never'}")
    return 0


# --------------------------------------------------------------------------
def cmd_benchmark(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    cfg["mode"] = "on"

    # -- sensor + filter cost, per sample --------------------------------
    engine = MotionEngine(cfg)
    source = sensors.SyntheticSensor("city", rate_hz=250.0, realtime=False)
    samples = [source.sample_at(index * 0.004) for index in range(args.iterations)]

    start = time.perf_counter()
    for index, sample in enumerate(samples):
        engine.ingest(index * 0.004, sample.accel, sample.gyro)
    elapsed = time.perf_counter() - start
    per_sample_us = elapsed / len(samples) * 1e6
    sensor_load = per_sample_us * 250.0 / 1e6 * 100.0

    # -- render preparation cost, per frame ------------------------------
    appearance = cfg["appearance"]
    sprite = sprites.sprite_for(appearance, padding=TILE_PADDING)
    points = layout.dot_positions(*SCREEN, appearance)
    payload = bytes(sprite.data)

    frames = max(1000, args.iterations // 10)
    start = time.perf_counter()
    total_bytes = 0
    for frame in range(frames):
        state = engine.state
        dx = state.dx + frame * 0.001
        tiles = [(int(round(x + dx - sprite.center_x)),
                  int(round(y + state.dy - sprite.center_y))) for x, y in points]
        for _tile in tiles:
            total_bytes += len(payload)
    elapsed = time.perf_counter() - start
    per_frame_us = elapsed / frames * 1e6
    render_load = per_frame_us * cfg["runtime"]["target_fps"] / 1e6 * 100.0

    # -- sprite rasterisation (only on settings changes) -----------------
    start = time.perf_counter()
    for _ in range(50):
        sprites.sprite_for(appearance, padding=TILE_PADDING)
    raster_ms = (time.perf_counter() - start) / 50 * 1000.0

    bytes_per_frame = len(points) * len(payload)

    print("Motion Cues - pipeline benchmark")
    print(f"  host python           : {sys.version.split()[0]}")
    print(f"  dots                  : {len(points)} "
          f"({appearance['count']} per edge x {len(appearance['edges'])} edges)")
    print(f"  sprite tile           : {sprite.width}x{sprite.height} px "
          f"({len(payload)} bytes)")
    print()
    print(f"  sensor+filter         : {per_sample_us:8.2f} us/sample "
          f"-> {sensor_load:5.2f}% of one core at 250 Hz")
    print(f"  render prep           : {per_frame_us:8.2f} us/frame  "
          f"-> {render_load:5.2f}% of one core at "
          f"{cfg['runtime']['target_fps']} fps")
    print(f"  total steady-state    : {sensor_load + render_load:5.2f}% of one core")
    print()
    print(f"  blit traffic          : {bytes_per_frame / 1024:.1f} KiB/frame "
          f"-> {bytes_per_frame * cfg['runtime']['target_fps'] / 1e6:.2f} MB/s "
          f"to the X server while moving")
    print(f"  sprite rasterisation  : {raster_ms:.2f} ms "
          f"(only on an appearance change)")
    print()
    print("  Not included: the X11 blit and gamescope's composite of one extra")
    print("  overlay plane, which need real hardware to measure.")
    return 0


# --------------------------------------------------------------------------
def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preset", choices=sorted(config_module.BUILTIN_PRESETS))
    parser.add_argument("--mode", default="on", choices=["auto", "on", "off"])
    sub = parser.add_subparsers(dest="command", required=True)

    preview = sub.add_parser("preview", help="render a PNG of the dot field")
    preview.add_argument("--out", default="preview.png")
    preview.add_argument("--displace", nargs=2, type=float, default=[0.0, 0.0],
                         metavar=("DX", "DY"))
    preview.set_defaults(func=cmd_preview)

    trace = sub.add_parser("trace", help="print the response to a motion profile")
    trace.add_argument("--profile", default="city",
                       choices=sorted(sensors.SyntheticSensor.PROFILES))
    trace.add_argument("--seconds", type=float, default=30.0)
    trace.add_argument("--rate", type=float, default=250.0)
    trace.add_argument("--lines", type=int, default=30)
    trace.set_defaults(func=cmd_trace)

    benchmark = sub.add_parser("benchmark", help="measure pipeline CPU cost")
    benchmark.add_argument("--iterations", type=int, default=50000)
    benchmark.set_defaults(func=cmd_benchmark)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
