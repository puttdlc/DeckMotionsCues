#!/usr/bin/env bash
#
# Motion Cues - Steam Deck setup wizard.
#
# Run it from Konsole in Desktop Mode:
#
#     bash install.sh
#
# or double-click "Install Motion Cues.desktop" next to it.
#
# Non-interactive use:
#
#     bash install.sh --yes --preset Car --mode auto
#     bash install.sh --uninstall --yes
#
# Nothing is written until you confirm a summary of exactly what will happen.

set -uo pipefail

VERSION="1.0.0"
PLUGIN_DIR_NAME="motion-cues"
PLUGIN_LABEL="Motion Cues"

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Files the plugin actually needs on the Deck.
REQUIRED_ITEMS=(plugin.json main.py package.json dist py_modules)
OPTIONAL_ITEMS=(README.md TECHNICAL.md defaults docs)

# ---------------------------------------------------------------------------
# options (overridable by flags, for scripted installs and for testing)
# ---------------------------------------------------------------------------
DECKY_HOME="${DECKY_HOME:-$HOME/homebrew}"
TARGET_DIR=""
ASSUME_YES=0
DRY_RUN=0
DO_UNINSTALL=0
RESTART_DECKY=1
OPT_PRESET="Car"
OPT_MODE="auto"
OPT_FALLBACK="true"
OPT_DEBUG="false"
OPT_FREE_SLOT=0
NONINTERACTIVE=0

# ---------------------------------------------------------------------------
# presentation
# ---------------------------------------------------------------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
    RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
    BLUE=$'\033[36m'; MAGENTA=$'\033[35m'
else
    BOLD=""; DIM=""; RESET=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; MAGENTA=""
fi

WARNINGS=()
FAILURES=()
PYTHON_BIN=""

# Finding an interpreter that exists is not the same as finding one that runs:
# on some systems "python3" is a stub that only offers to install Python.
find_python() {
    local candidate
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1            && "$candidate" -c 'import sys' >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            return 0
        fi
    done
    return 1
}

say()   { printf '%s\n' "$*"; }
info()  { printf '  %s\n' "$*"; }
ok()    { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn()  { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$*"; WARNINGS+=("$*"); }
fail()  { printf '  %s✗%s %s\n' "$RED" "$RESET" "$*"; FAILURES+=("$*"); }
step()  { printf '\n%s%s%s\n' "$BOLD" "$*" "$RESET"; }

rule() {
    printf '%s' "$DIM"
    printf '─%.0s' $(seq 1 64)
    printf '%s\n' "$RESET"
}

banner() {
    printf '\n%s' "$BLUE$BOLD"
    cat <<'ART'
   __  __      _   _              ___
  |  \/  |___ | |_(_)___ _ _     / __|  _ ___ ___
  | |\/| / _ \|  _| / _ \ ' \   | (_| || / -_|_-<
  |_|  |_\___/ \__|_\___/_||_|   \___\_,_\___/__/
  Motion Cues - v1.0.0
ART
    printf '%s' "$RESET"
    printf '  %sSteam Deck setup wizard  ·  v%s%s\n' "$DIM" "$VERSION" "$RESET"
}

die() {
    printf '\n%s%s%s\n' "$RED$BOLD" "Setup stopped: $*" "$RESET"
    printf '%sNothing was changed.%s\n\n' "$DIM" "$RESET"
    pause_if_windowed
    exit 1
}

# Keep a double-clicked window open so the user can read the result.
pause_if_windowed() {
    if [ "$NONINTERACTIVE" -eq 0 ] && [ -t 0 ]; then
        printf '%sPress Enter to close.%s ' "$DIM" "$RESET"
        read -r _ || true
    fi
}

ask() {
    # ask "Question" default_yes(0|1) -> returns 0 for yes
    local prompt="$1" default="${2:-1}" reply suffix
    if [ "$ASSUME_YES" -eq 1 ]; then return "$default"; fi
    if [ "$default" -eq 0 ]; then suffix="[Y/n]"; else suffix="[y/N]"; fi
    while true; do
        printf '  %s %s ' "$prompt" "$suffix"
        read -r reply || reply=""
        case "${reply,,}" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            "")    return "$default" ;;
            *)     printf '  %sPlease answer y or n.%s\n' "$DIM" "$RESET" ;;
        esac
    done
}

choose() {
    # choose VAR_NAME "Prompt" current  opt1 opt2 ...
    local __var="$1" prompt="$2" current="$3"; shift 3
    local options=("$@") index=1 reply
    if [ "$ASSUME_YES" -eq 1 ]; then return 0; fi
    printf '\n  %s%s%s\n' "$BOLD" "$prompt" "$RESET"
    for opt in "${options[@]}"; do
        if [ "$opt" = "$current" ]; then
            printf '    %s%2d) %s  (current)%s\n' "$GREEN" "$index" "$opt" "$RESET"
        else
            printf '    %2d) %s\n' "$index" "$opt"
        fi
        index=$((index + 1))
    done
    while true; do
        printf '  Choose 1-%d, or Enter to keep "%s": ' "${#options[@]}" "$current"
        read -r reply || reply=""
        if [ -z "$reply" ]; then return 0; fi
        if [[ "$reply" =~ ^[0-9]+$ ]] && [ "$reply" -ge 1 ] \
           && [ "$reply" -le "${#options[@]}" ]; then
            printf -v "$__var" '%s' "${options[$((reply - 1))]}"
            return 0
        fi
        printf '  %sNot one of the options.%s\n' "$DIM" "$RESET"
    done
}

run() {
    # Execute unless this is a dry run.
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  %s[dry-run]%s %s\n' "$DIM" "$RESET" "$*"
        return 0
    fi
    "$@"
}

# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
${BOLD}Motion Cues setup wizard${RESET}

  bash install.sh [options]

Options:
  --yes, -y             Accept every prompt (non-interactive install)
  --uninstall           Remove the plugin instead of installing it
  --preset NAME         Starting preset: Car, Train/Bus, Boat, Subtle, Strong
  --mode MODE           Starting mode: auto, on, off
  --no-fallback         Disable drawing cues inside the Steam UI
  --debug-readout       Turn on the live motion readout
  --free-overlay-slot   Stop mangoapp so gamescope's overlay slot is free
  --target DIR          Install to DIR instead of \$HOME/homebrew/plugins/$PLUGIN_DIR_NAME
  --no-restart          Do not restart Decky at the end
  --dry-run             Show what would happen, change nothing
  --help, -h            This message
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -y|--yes)            ASSUME_YES=1; NONINTERACTIVE=1 ;;
        --uninstall)         DO_UNINSTALL=1 ;;
        --preset)            OPT_PRESET="${2:-}"; shift ;;
        --mode)              OPT_MODE="${2:-}"; shift ;;
        --no-fallback)       OPT_FALLBACK="false" ;;
        --debug-readout)     OPT_DEBUG="true" ;;
        --free-overlay-slot) OPT_FREE_SLOT=1 ;;
        --target)            TARGET_DIR="${2:-}"; shift ;;
        --no-restart)        RESTART_DECKY=0 ;;
        --dry-run)           DRY_RUN=1 ;;
        -h|--help)           usage; exit 0 ;;
        *) printf 'Unknown option: %s\n\n' "$1"; usage; exit 2 ;;
    esac
    shift
done

[ -n "$TARGET_DIR" ] || TARGET_DIR="$DECKY_HOME/plugins/$PLUGIN_DIR_NAME"

# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
check_source() {
    step "1. Checking the files to install"
    local missing=0
    for item in "${REQUIRED_ITEMS[@]}"; do
        if [ -e "$SOURCE_DIR/$item" ]; then
            ok "$item"
        else
            fail "$item is missing"
            missing=1
        fi
    done
    if [ "$missing" -eq 1 ]; then
        say ""
        info "Run this script from inside the Motion Cues folder."
        if [ ! -e "$SOURCE_DIR/dist" ]; then
            info "'dist' (the built plugin panel) is missing. It ships pre-built in"
            info "releases, so this normally only happens if you deleted it, or you"
            info "cloned the source and skipped the one-time build step:"
            info "    npm install && npm run build"
        fi
        die "the source folder is incomplete"
    fi
    local count
    count=$(find "$SOURCE_DIR/py_modules" -name '*.py' 2>/dev/null | wc -l | tr -d ' ')
    ok "py_modules contains $count Python files"
}

check_system() {
    step "2. Checking this system"

    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        local pretty
        pretty=$(. /etc/os-release && printf '%s' "${PRETTY_NAME:-unknown}")
        if printf '%s' "$pretty" | grep -qi "steamos"; then
            ok "SteamOS detected ($pretty)"
        else
            warn "This does not look like SteamOS ($pretty)"
            info "  The plugin is built for SteamOS; installing anyway is fine,"
            info "  but the gamescope overlay will not be available."
        fi
    else
        warn "Could not identify the operating system"
    fi

    if [ -d "$DECKY_HOME/plugins" ]; then
        ok "Decky Loader found at $DECKY_HOME"
    else
        fail "No Decky Loader at $DECKY_HOME"
        info "  Install Decky Loader first: https://decky.xyz"
        die "Decky Loader is required"
    fi

    if find_python; then
        ok "$PYTHON_BIN is $("$PYTHON_BIN" --version 2>&1 | awk '{print $2}')"
    else
        warn "no working Python found on PATH"
        info "  Decky runs plugins with its own interpreter, so this only means"
        info "  the wizard cannot self-test the install."
    fi

    # The overlay binds these through ctypes at runtime.
    local libs_ok=1
    for lib in libX11 libXfixes; do
        if ldconfig -p 2>/dev/null | grep -q "$lib\.so"; then
            ok "$lib is present"
        else
            libs_ok=0
        fi
    done
    if [ "$libs_ok" -eq 0 ]; then
        warn "libX11 / libXfixes were not found by ldconfig"
        info "  They are standard on SteamOS. If the overlay cannot start,"
        info "  the plugin will say so in its Problems panel."
    fi

    if pgrep -x mangoapp >/dev/null 2>&1; then
        warn "mangoapp is running and holds gamescope's only overlay slot"
        info "  Motion Cues competes for it by opacity, which may be enough."
        info "  The wizard can also stop it for you (option below)."
    else
        ok "gamescope's external overlay slot looks free"
    fi
}

detect_existing() {
    if [ -d "$TARGET_DIR" ]; then
        EXISTING=1
        ok "Existing installation found at $TARGET_DIR"
    else
        EXISTING=0
    fi
}

# ---------------------------------------------------------------------------
# wizard
# ---------------------------------------------------------------------------
configure() {
    step "3. Setup options"

    if [ "$ASSUME_YES" -eq 1 ]; then
        info "Using defaults (non-interactive)."
        return
    fi

    choose OPT_PRESET "Which starting preset?" "$OPT_PRESET" \
        "Car" "Train/Bus" "Boat" "Subtle" "Strong"

    local mode_label="Automatic"
    case "$OPT_MODE" in on) mode_label="Always On" ;; off) mode_label="Off" ;; esac
    choose mode_label "How should the cues activate?" "$mode_label" \
        "Automatic" "Always On" "Off"
    case "$mode_label" in
        "Automatic") OPT_MODE="auto" ;;
        "Always On") OPT_MODE="on" ;;
        "Off")       OPT_MODE="off" ;;
    esac

    say ""
    if ask "Draw cues inside the Steam UI when the game overlay is unavailable?" 0; then
        OPT_FALLBACK="true"
    else
        OPT_FALLBACK="false"
    fi

    if ask "Show the live motion readout in the panel (useful for first setup)?" 1; then
        OPT_DEBUG="true"
    else
        OPT_DEBUG="false"
    fi

    if pgrep -x mangoapp >/dev/null 2>&1; then
        say ""
        printf '  %sgamescope allows only one external overlay, and mangoapp\n' "$DIM"
        printf '  (Steam'\''s performance overlay) currently holds it. Stopping it\n'
        printf '  frees the slot, but the performance overlay stays off until you\n'
        printf '  restart the Steam session.%s\n' "$RESET"
        if ask "Stop mangoapp now to free the overlay slot?" 1; then
            OPT_FREE_SLOT=1
        fi
    fi
}

summary() {
    step "4. Ready to install"
    rule
    printf '  %-22s %s\n' "Action:"        "$([ "$EXISTING" -eq 1 ] && echo "Update existing install" || echo "Fresh install")"
    printf '  %-22s %s\n' "From:"          "$SOURCE_DIR"
    printf '  %-22s %s\n' "To:"            "$TARGET_DIR"
    printf '  %-22s %s\n' "Preset:"        "$OPT_PRESET"
    printf '  %-22s %s\n' "Mode:"          "$OPT_MODE"
    printf '  %-22s %s\n' "Steam UI cues:" "$OPT_FALLBACK"
    printf '  %-22s %s\n' "Motion readout:" "$OPT_DEBUG"
    printf '  %-22s %s\n' "Stop mangoapp:" "$([ "$OPT_FREE_SLOT" -eq 1 ] && echo "yes" || echo "no")"
    printf '  %-22s %s\n' "Restart Decky:" "$([ "$RESTART_DECKY" -eq 1 ] && echo "yes (needs sudo)" || echo "no")"
    rule
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  %sDRY RUN - nothing will actually be written.%s\n' "$YELLOW" "$RESET"
    fi
    say ""
    if ! ask "Proceed?" 0; then
        say ""
        info "Cancelled. Nothing was changed."
        pause_if_windowed
        exit 0
    fi
}

# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------
write_first_run_defaults() {
    local dir="$SOURCE_DIR/defaults"
    run mkdir -p "$dir" || return 1
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  %s[dry-run]%s write %s/first_run.json\n' "$DIM" "$RESET" "$dir"
        return 0
    fi
    cat > "$dir/first_run.json" <<EOF
{
  "preset": "$OPT_PRESET",
  "mode": "$OPT_MODE",
  "runtime": {
    "fallback_steam_ui": $OPT_FALLBACK,
    "debug_readout": $OPT_DEBUG
  }
}
EOF
}

install_plugin() {
    step "5. Installing"

    if ! write_first_run_defaults; then
        fail "Could not write the first-run defaults"
        die "the source folder is not writable"
    fi
    ok "Recorded your choices for first launch"

    if [ "$EXISTING" -eq 1 ]; then
        # Keep nothing from the old copy: stale .py files from a previous
        # version are exactly the sort of thing that causes confusing bugs.
        if ! run rm -rf "$TARGET_DIR"; then
            fail "Could not remove the previous installation"
            die "check permissions on $TARGET_DIR"
        fi
        ok "Removed the previous installation"
    fi

    if ! run mkdir -p "$TARGET_DIR"; then
        fail "Could not create $TARGET_DIR"
        die "check permissions on $DECKY_HOME/plugins"
    fi

    local item
    for item in "${REQUIRED_ITEMS[@]}" "${OPTIONAL_ITEMS[@]}"; do
        [ -e "$SOURCE_DIR/$item" ] || continue
        if run cp -r "$SOURCE_DIR/$item" "$TARGET_DIR/"; then
            ok "copied $item"
        else
            fail "could not copy $item"
            die "the copy failed part-way; $TARGET_DIR may be incomplete"
        fi
    done

    # Python caches from a development machine are worse than useless here.
    if [ "$DRY_RUN" -eq 0 ]; then
        find "$TARGET_DIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
        find "$TARGET_DIR" -name '*.pyc' -delete 2>/dev/null
    fi

    # Under `set -u`, an unset USER would abort the installer here, which is a
    # silly way to fail after everything has already been copied.
    local owner="${SUDO_USER:-${USER:-${LOGNAME:-$(id -un 2>/dev/null || echo deck)}}}"
    if [ "$DRY_RUN" -eq 0 ] && command -v chown >/dev/null 2>&1; then
        chown -R "$owner":"$owner" "$TARGET_DIR" 2>/dev/null \
            && ok "ownership set to $owner" \
            || warn "could not set ownership (usually harmless)"
    fi
}

verify_install() {
    step "6. Verifying"
    if [ "$DRY_RUN" -eq 1 ]; then
        info "Skipped (dry run)."
        return
    fi

    local item bad=0
    for item in "${REQUIRED_ITEMS[@]}"; do
        if [ -e "$TARGET_DIR/$item" ]; then ok "$item is in place"; else fail "$item did not arrive"; bad=1; fi
    done
    [ "$bad" -eq 0 ] || die "the installation is incomplete"

    if [ -n "$PYTHON_BIN" ]; then
        if "$PYTHON_BIN" -c "
import sys
sys.path.insert(0, '$TARGET_DIR/py_modules')
from motioncues import config, sensors, engine, sprites, layout, problems
config.validate({})
" 2>/dev/null; then
            ok "the Python pipeline imports cleanly"
        else
            warn "the Python modules did not import here"
            info "  Decky uses its own interpreter, so this may still be fine."
        fi

        local report
        report=$("$PYTHON_BIN" -c "
import sys
sys.path.insert(0, '$TARGET_DIR/py_modules')
from motioncues import sensors
for entry in sensors.probe():
    mark = 'yes' if entry['available'] else 'no '
    print('    %-10s %s  %s' % (entry['source'], mark, entry['detail'][:44]))
" 2>/dev/null)
        if [ -n "$report" ]; then
            info "Sensor backends detected:"
            printf '%s\n' "$report"
        fi
    fi
}

free_overlay_slot() {
    [ "$OPT_FREE_SLOT" -eq 1 ] || return 0
    step "7. Freeing gamescope's overlay slot"
    if ! pgrep -x mangoapp >/dev/null 2>&1; then
        ok "mangoapp is not running; nothing to do"
        return 0
    fi
    if run pkill -TERM -x mangoapp; then
        ok "mangoapp stopped"
        info "  The performance overlay stays off until the Steam session restarts."
    else
        warn "could not stop mangoapp"
        info "  You can do it later from the plugin's Advanced section."
    fi
}

restart_decky() {
    [ "$RESTART_DECKY" -eq 1 ] || { info "Skipping the Decky restart (--no-restart)."; return 0; }
    step "8. Restarting Decky Loader"

    if ! command -v systemctl >/dev/null 2>&1; then
        warn "systemctl not available; restart Decky yourself"
        return 0
    fi

    say ""
    info "This needs administrator rights. You will be asked for your Deck password."
    info "(If you have never set one: run 'passwd' in Konsole first.)"
    say ""

    if [ "$DRY_RUN" -eq 1 ]; then
        printf '  %s[dry-run]%s sudo systemctl restart plugin_loader\n' "$DIM" "$RESET"
        return 0
    fi

    if sudo -v 2>/dev/null && sudo systemctl restart plugin_loader 2>/dev/null; then
        ok "Decky restarted - the plugin is loading now"
    else
        warn "could not restart Decky automatically"
        info "  Run this yourself, or just reboot:"
        info "      sudo systemctl restart plugin_loader"
    fi
}

# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------
uninstall_plugin() {
    banner
    step "Uninstall $PLUGIN_LABEL"
    if [ ! -d "$TARGET_DIR" ]; then
        info "Nothing installed at $TARGET_DIR"
        pause_if_windowed
        exit 0
    fi
    info "This will delete: $TARGET_DIR"
    info "Your saved settings and presets live in Decky's settings folder and"
    info "are left alone, so reinstalling keeps your configuration."
    say ""
    # `ask` defaults destructive prompts to "no" under --yes, which is right
    # everywhere except here: "--uninstall --yes" is already an explicit
    # instruction to remove it, so obey that rather than silently doing nothing.
    if [ "$ASSUME_YES" -eq 0 ] && ! ask "Remove it?" 1; then
        info "Cancelled."
        pause_if_windowed
        exit 0
    fi
    if run rm -rf "$TARGET_DIR"; then
        ok "removed"
    else
        fail "could not remove $TARGET_DIR"
        die "check permissions"
    fi
    RESTART_DECKY=1
    restart_decky
    say ""
    ok "$PLUGIN_LABEL uninstalled."
    pause_if_windowed
    exit 0
}

# ---------------------------------------------------------------------------
# closing advice
# ---------------------------------------------------------------------------
finish() {
    say ""
    rule
    if [ ${#FAILURES[@]} -gt 0 ]; then
        printf '%s%s%s\n' "$RED$BOLD" "  Finished with errors." "$RESET"
        for line in "${FAILURES[@]}"; do printf '    %s✗%s %s\n' "$RED" "$RESET" "$line"; done
    else
        printf '%s%s%s\n' "$GREEN$BOLD" "  $PLUGIN_LABEL is installed." "$RESET"
    fi
    if [ ${#WARNINGS[@]} -gt 0 ]; then
        say ""
        printf '  %sWorth knowing:%s\n' "$YELLOW" "$RESET"
        for line in "${WARNINGS[@]}"; do printf '    %s!%s %s\n' "$YELLOW" "$RESET" "$line"; done
    fi
    rule

    cat <<EOF

  ${BOLD}Next steps on the Deck${RESET}

    1. Go back to Game Mode.
    2. Press the ${BOLD}...${RESET} (Quick Access) button.
    3. Open the plug icon (Decky) and choose "${PLUGIN_LABEL}".
    4. Check the two rows at the top:
         Rendering  should say  "Over games (gamescope overlay)"
         Sensor     should show a backend and about 250 Hz
    5. Set Mode to "Always On" and tilt the Deck - the dots should
       drift against the motion.

  ${BOLD}If the dots do not move${RESET}

    Steam only enables the gyro when a controller layout uses it:
      Steam > controller settings > Gyro Behaviour > anything but "None"

    To check everything else works, set
      Advanced > Sensor source > Demo (simulated)

  ${BOLD}If the dots show in Steam but not over a game${RESET}

    Advanced > "Take overlay slot from mangoapp"

  ${DIM}Anything that goes wrong appears in a Problems section at the top of
  the plugin panel, with a suggested fix. If it is not there, nothing
  has failed.${RESET}

EOF
    pause_if_windowed
}

# ---------------------------------------------------------------------------
main() {
    if [ "$DO_UNINSTALL" -eq 1 ]; then
        detect_existing
        uninstall_plugin
    fi

    banner
    say ""
    info "This wizard installs the $PLUGIN_LABEL plugin for Decky Loader."
    info "It will check your system, ask a few questions, show you a summary,"
    info "and change nothing until you confirm."

    check_source
    check_system
    detect_existing

    if [ "$EXISTING" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ]; then
        say ""
        if ask "$PLUGIN_LABEL is already installed. Reinstall/update it?" 0; then
            :
        else
            info "Cancelled."
            pause_if_windowed
            exit 0
        fi
    fi

    configure
    summary
    install_plugin
    verify_install
    free_overlay_slot
    restart_decky
    finish
}

main "$@"
