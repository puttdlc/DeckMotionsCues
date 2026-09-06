# Motion Cues for Steam Deck

A Steam Deck plug-in inspired from Apple's **"Vehicle Motion Cues"** accessibility feature, rebuilt as a Decky
Loader plugin for SteamOS. Small dots near the screen edges move in
counter-response to real device motion, giving your eyes a stable reference to
the vehicle you are travelling in. That is what reduces motion sickness when
you play on the Deck in a car, train, bus, boat, plane or wherever you please.
---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [First run](#first-run)
- [Using it](#using-it)
- [Customisation reference](#customisation-reference)
- [Troubleshooting](#troubleshooting)
- [Performance](#performance)
- [Verification status](#verification-status)
- [Development](#development)

---

## Features

### Motion sensing
- Reads the Deck's built-in accelerometer **and** gyroscope at the
  controller's native rate (~250 Hz) through the kernel's own motion-sensor
  device, with no polling loop, no udev rules and no background daemon.
- **Four sensor backends** with automatic selection and graceful fallback:
  the kernel motion node, IIO sysfs, direct `hidraw` reports, and a built-in
  motion simulator.
- **Complementary filtering** separates gravity from linear acceleration, with
  a gyro-adaptive time constant so repositioning the Deck doesn't fling the
  dots across the screen.
- **Vehicle-frame resolution**: acceleration is resolved into fore/aft,
  sideways and vertical components relative to the *vehicle*, so the cues stay
  correct however you happen to be holding the Deck.
- **Yaw-rate lead term** so the cue starts moving as you enter a corner rather
  than after the lateral force builds.

### Rendering
- **True over-game overlay** via gamescope's external-overlay plane, the same
  mechanism Steam's own performance overlay uses.
- **Click-through**: an empty XFixes input region means the overlay cannot
  intercept touch, trackpad, clicks or gyro aiming. If pass-through can't be
  established, the overlay refuses to appear at all rather than eat your input.
- **Steam-UI fallback tier** draws the cues inside Steam's own screens when no
  overlay window is possible, and the panel always tells you which tier is live.
- **Cheap by construction**: dots are rasterised once into small antialiased
  tiles and blitted; when nothing moves, zero X traffic is sent; when the cues
  are inactive, the overlay window is unmapped entirely.
- Antialiased **circle, ring, square and diamond** dots with optional outlines.

### Activation
- **Automatic**: engages only when motion looks like vehicle travel, using
  sustained low-frequency acceleration energy plus a rotation test that rejects
  you simply picking the Deck up. Hysteresis on both thresholds and dwell times
  so it doesn't flicker.
- **Always On** and **Off**, both one tap from the top of the panel.
- Smooth fade in/out on every transition.

### Customisation
- **34 user-editable controls** across appearance, motion response, automatic
  detection and runtime behaviour. Every one applies live and persists.
- **Presets**: five sensible built-ins (Car, Train/Bus, Boat, Subtle, Strong),
  plus save / load / delete of your own. Overwrite a built-in and deleting it
  restores the shipped version.
- **Orientation calibration** derives the screen-up axis from gravity, with
  invert toggles for the remaining directions.
- **Demo mode** drives the whole pipeline from simulated car, train or boat
  motion so you can preview and tune indoors.

### Diagnostics
- **A problem log that stays out of your way.** When nothing is wrong the panel
  shows nothing at all. When something fails (no sensor, no overlay window,
  unwritable settings, a crashed helper process), a dismissible entry appears
  with what broke, where, how many times, and what to do about it. Conditions
  that recover withdraw themselves; a dismissed fault returns if it recurs.
- **Live motion readout** (optional) showing raw gravity, resolved axes, sensor
  rate and detector progress.
- **Diagnostics button** listing every sensor backend and X display found.

---

## Requirements

| | |
| --- | --- |
| Device | Steam Deck (LCD or OLED) running SteamOS 3.x |
| Plugin loader | [Decky Loader](https://decky.xyz) |
| Kernel | One whose `hid-steam` driver exposes IMU (current SteamOS does). Older kernels fall back to `hidraw`. |
| Setup | None beyond the wizard. The overlay uses the system `libX11`/`libXfixes` through `ctypes`, so there is no binary to compile or install. |

---

## Installation

### Option A: the setup wizard (recommended)

The plugin ships with an interactive installer that checks your system, asks a
few questions, shows a summary, and changes nothing until you confirm.

1. Switch the Deck to **Desktop Mode**.
2. `git clone` this repo to your Steam Deck, anywhere is fine. `Desktop` is recommended.
   ```bash
   git clone https://github.com/puttdlc/DeckMotionsCues.git
   ```
3. Either **double-click `Install Motion Cues.desktop`** in the folder, or open
   **Konsole** in that folder and run:

   ```bash
   bash install.sh
   ```

4. Answer the wizard's questions and confirm. It will:
   - verify the files, Decky Loader, Python and the X libraries;
   - let you pick a starting **preset** and **mode**;
   - offer to free gamescope's overlay slot if `mangoapp` holds it;
   - copy the plugin, self-test the Python pipeline, list the sensors it found;
   - restart Decky for you (this is the one step that asks for your password).

Non-interactive, if you'd rather not answer anything:

```bash
bash install.sh --yes --preset Car --mode auto
```

Useful flags: `--dry-run` (show what would happen, change nothing),
`--uninstall`, `--no-restart`, `--target DIR`, `--free-overlay-slot`,
`--debug-readout`, `--help`.

> If you have never set a Deck password, run `passwd` in Konsole first, because
> the Decky restart needs `sudo`. You can also pass `--no-restart` and just reboot.

### Option B: copy it manually

The wizard only automates what you could do by hand:

```bash
mkdir -p ~/homebrew/plugins/motion-cues
cp -r plugin.json main.py package.json dist py_modules ~/homebrew/plugins/motion-cues/
sudo chown -R deck:deck ~/homebrew/plugins/motion-cues
sudo systemctl restart plugin_loader
```

### Option C: copy from another machine over SSH

Enable SSH on the Deck first (Desktop Mode → Konsole → `passwd`, then
`sudo systemctl enable --now sshd`), then from your PC:

```bash
rsync -av --exclude node_modules --exclude .git ./ deck@<deck-ip>:~/homebrew/plugins/motion-cues/
ssh deck@<deck-ip> "sudo systemctl restart plugin_loader"
```

### Modifying the frontend (optional, not needed to install)

The plugin panel comes pre-built: `dist/index.js` is committed in the repo, so
`git clone` on the Deck already has everything the installer needs. Nothing
here needs Node.js or npm on the Deck itself, ever.

Node.js is only relevant if you want to change the panel's source
(`src/*.tsx`) yourself, on your own PC:

```bash
npm install
npm run build          # rebuilds dist/index.js from src/
npm run typecheck
python -m pytest tests # 122 Python tests
```

### Uninstalling

```bash
bash install.sh --uninstall
```

or delete `~/homebrew/plugins/motion-cues` and restart Decky. Your settings and
presets live in Decky's settings folder and are kept, so reinstalling restores
your configuration.

---

## First run

1. Open **Motion Cues** in the Quick Access Menu.
2. Check the **Rendering** row. It should say *Over games (gamescope overlay)*.
   Anything else is explained in [Troubleshooting](#troubleshooting).
3. Check the **Sensor** row. It should show a backend and a rate around
   250 Hz. If it shows an error, see
   [The dots never move](#the-dots-never-move).
4. Set **Mode** to **Always On** and gently tilt the Deck. The dots should
   drift against the motion.
5. If a direction feels backwards, open **Motion response** and use
   **Calibrate orientation**, then the **Invert** toggles.
6. Set **Mode** back to **Automatic** for normal use.

Apart from running the installer itself, there is no permissions setup and
there are no udev rules to add at any point.

---

## Using it

### Modes

| Mode | Behaviour |
| --- | --- |
| **Automatic** | Cues appear only when sustained vehicle-like motion is detected, and fade out when it stops. |
| **Always On** | Cues are always visible. Best for very smooth highway or rail travel. |
| **Off** | Cues hidden and the overlay helper process stopped entirely. |


### Presets

| Preset | Tuned for |
| --- | --- |
| **Car** | General road use. Left/right edges, moderate travel, quick return. |
| **Train/Bus** | Rail sway: more sideways sensitivity, damped vertical, slower return. |
| **Boat** | Slow swell: all four edges, long travel, heavy smoothing, lazy return. |
| **Subtle** | Minimal: fewer, smaller, dimmer dots. |
| **Strong** | Maximum visibility, always on. |

- **Load**: pick from the *Load preset* dropdown.
- **Save**: type a name in *Save current settings as*, press **Save preset**.
- **Delete**: removes a user preset; deleting a built-in you overwrote
  restores the shipped version.

Presets store mode, appearance, motion and detection settings, but deliberately
*not* runtime settings like the sensor source, so switching presets never
changes how the plugin talks to hardware.

### How Automatic mode decides

Vehicle travel means **sustained, low-frequency acceleration with little
rotation**. Picking the Deck up is the opposite: a burst of large rotation. The
detector tracks both energies over a ~2 s window and engages only when
acceleration energy holds above the threshold for the dwell time *while*
rotation stays low, with a lower threshold and longer dwell for disengaging.

Measured against the built-in profiles: city engages after ~9 s, train ~6 s,
boat ~8 s; stationary and "someone is waving it around" never engage.

**Limitations:** very smooth cruising can stay below the threshold (use Always
On); vigorous handheld play can occasionally trip it; it can't tell a stopped
car from standing still, so cues fade at long traffic lights; it is purely
inertial, with no GPS or speed input.

---

## Customisation reference

Everything below applies live and is saved immediately.

**Appearance**: dots per edge (1–40) · dot size · opacity · shape (circle,
ring, square, diamond) · colour (palette or custom hex) · which of the four
edges · edge padding · distribution (even / corners / clustered) · end margin ·
outline width.

**Motion response**: sideways sensitivity · fore/aft sensitivity · turn (gyro)
sensitivity · maximum travel · smoothing · return-to-centre speed · dead zone ·
bump response · invert sideways · invert fore/aft · calibrate orientation.

**Automatic detection**: engage threshold · disengage threshold · time before
engaging · time before disengaging · handling rejection · fade time.

**Advanced**: sensor source · demo motion profile · overlay frame rate ·
Steam-UI fallback · live motion readout · restart overlay · overlay-slot
management · diagnostics · reset to defaults.

---

## Troubleshooting

**The panel tells you first.** If anything fails, a **Problems** section
appears at the top of the panel with the cause and a suggested fix. When it
isn't there, nothing has gone wrong. Each entry can be dismissed; one that
recurs comes back.

### The dots never move?

Almost always the IMU gating. `hid-steam` only enables raw IMU reporting when
no userspace client holds the controller exclusively, and in Game Mode Steam
does. The fix:

> Steam → controller settings for the running game → **Gyro Behaviour** → set
> to anything other than **None**.

To confirm the rest of the plugin works, set *Advanced → Sensor source* to
**Demo (simulated)**; if the dots move then, the pipeline is fine and it is
purely a sensor-availability issue.

### The dots show in the Steam UI but not over games?

gamescope allows exactly **one** external overlay, and on SteamOS `mangoapp`
(the performance overlay) normally holds it and never releases it. Motion Cues
competes for the slot by declaring full opacity, which current gamescope uses
to rank claimants, but that may not win on every build.

If it doesn't: *Advanced → **Take overlay slot from mangoapp***. This stops
mangoapp and frees the slot. The performance overlay stays off until you
restart the Steam session; **Restore performance overlay** attempts to bring it
back.

### Direction feels inverted?

Use **Calibrate orientation** while holding the Deck normally, then **Invert
sideways** / **Invert fore/aft**. The IMU axis *directions* are the one thing
that could not be confirmed without hardware, which is exactly why these
controls exist.

### The effect is too subtle or too strong?

Load the **Strong** or **Subtle** preset, or raise the two sensitivity sliders
in *Motion response*. Maximum travel caps how far the dots can ever go.

---

## Performance

Measured with `python tools/simulate.py benchmark` on the development machine
(desktop x86-64, Python 3.13) at default settings of 24 dots, 60 fps and
250 Hz:

| Path | Cost |
| --- | --- |
| Sensor read + filtering | 15.5 µs/sample → **0.39 %** of one core at 250 Hz |
| Render preparation | 11.8 µs/frame → **0.07 %** of one core at 60 fps |
| **Total steady state** | **≈ 0.46 % of one core** |
| Blit traffic while moving | 45 KiB/frame → 2.8 MB/s to the X server |
| Sprite rasterisation | 2.4 ms, only when appearance changes |

Budget roughly **1–2 % of one core** on the Deck's slower cores. The frame-time
cost of one extra gamescope overlay plane has not been measured, because that
needs hardware.