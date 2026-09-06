import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  Field,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
  ToggleField,
  showModal,
  staticClasses,
} from "@decky/ui";
import { definePlugin, routerHook, toaster } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { FaCarSide } from "react-icons/fa";

import {
  COLOR_OPTIONS,
  Config,
  ConfigPatch,
  DEMO_PROFILES,
  Diagnostics,
  EDGES,
  Edge,
  LAYOUT_OPTIONS,
  Mode,
  PresetInfo,
  Problem,
  SENSOR_OPTIONS,
  SHAPE_OPTIONS,
  Status,
  calibrateOrientation,
  claimOverlaySlot,
  clearProblems,
  deletePreset,
  getConfig,
  getDiagnostics,
  getStatus,
  listPresets,
  loadPreset,
  releaseOverlaySlot,
  resetConfig,
  restartOverlay,
  savePreset,
  setConfig,
  subscribeMotion,
  unsubscribeMotion,
} from "./api";
import { FallbackOverlay } from "./FallbackOverlay";
import { ProblemsPanel } from "./ProblemsPanel";

const MODE_OPTIONS: { data: Mode; label: string }[] = [
  { data: "auto", label: "Automatic" },
  { data: "on", label: "Always On" },
  { data: "off", label: "Off" },
];

/** Shared config cache so the global overlay component can read it too. */
let cachedConfig: Config | null = null;
let fallbackEnabled = false;

function tierLabel(tier: string): string {
  switch (tier) {
    case "gamescope-overlay":
      return "Over games (gamescope overlay)";
    case "x11-overlay":
      return "X11 overlay (not gamescope)";
    case "none":
      return "Steam UI only (fallback)";
    default:
      return tier || "unknown";
  }
}

function Content() {
  const [config, setConfigState] = useState<Config | null>(cachedConfig);
  const [status, setStatus] = useState<Status | null>(null);
  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [presetName, setPresetName] = useState("");
  const [showAppearance, setShowAppearance] = useState(false);
  const [showMotion, setShowMotion] = useState(false);
  const [showAuto, setShowAuto] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<Problem[]>([]);
  // Raised when the panel itself cannot reach the backend, so a dead backend
  // is visible rather than looking like "nothing is wrong".
  const [panelProblem, setPanelProblem] = useState<Problem | null>(null);

  const pending = useRef<ConfigPatch>({});
  const timer = useRef<number | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const next = await getStatus();
      setStatus(next);
      setProblems(next.problems ?? []);
      setPanelProblem(null);
    } catch (error) {
      // The backend is unreachable; nothing else in the panel can report it,
      // so synthesise an entry locally.
      const now = Date.now() / 1000;
      setPanelProblem((current) => ({
        key: "panel:backend-unreachable",
        severity: "error",
        source: "panel",
        title: "Cannot reach the Motion Cues backend",
        detail: String(error),
        hint: "Reload the plugin from Decky's settings, or restart Steam.",
        first_seen: current?.first_seen ?? now,
        last_seen: now,
        count: (current?.count ?? 0) + 1,
      }));
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [cfg, presetList] = await Promise.all([getConfig(), listPresets()]);
        cachedConfig = cfg;
        setConfigState(cfg);
        setPresets(presetList);
      } catch (error) {
        toaster.toast({ title: "Motion Cues", body: `Could not load settings: ${error}` });
        const now = Date.now() / 1000;
        setPanelProblem({
          key: "panel:settings-load",
          severity: "error",
          source: "panel",
          title: "Settings could not be loaded",
          detail: String(error),
          hint: "The panel is showing defaults; changes may not stick.",
          first_seen: now,
          last_seen: now,
          count: 1,
        });
      }
      await refreshStatus();
    })();
    const interval = window.setInterval(refreshStatus, 2000);
    return () => window.clearInterval(interval);
  }, [refreshStatus]);

  /**
   * Sliders fire continuously, so patches are merged and flushed on a short
   * timer. The local state updates immediately, which is what keeps the panel
   * feeling responsive while still writing every change through to disk.
   */
  const patch = useCallback((update: ConfigPatch) => {
    setConfigState((current) => {
      if (!current) return current;
      const next: Config = { ...current };
      for (const [key, value] of Object.entries(update)) {
        const typedKey = key as keyof Config;
        if (value && typeof value === "object" && !Array.isArray(value)) {
          (next[typedKey] as unknown) = {
            ...(current[typedKey] as unknown as object),
            ...(value as object),
          };
        } else {
          (next[typedKey] as unknown) = value;
        }
      }
      cachedConfig = next;
      return next;
    });

    for (const [key, value] of Object.entries(update)) {
      const typedKey = key as keyof ConfigPatch;
      if (value && typeof value === "object" && !Array.isArray(value)) {
        pending.current[typedKey] = {
          ...((pending.current[typedKey] as object) ?? {}),
          ...(value as object),
        } as never;
      } else {
        pending.current[typedKey] = value as never;
      }
    }

    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      const body = pending.current;
      pending.current = {};
      timer.current = null;
      try {
        const saved = await setConfig(body);
        cachedConfig = saved;
        setConfigState(saved);
      } catch (error) {
        toaster.toast({ title: "Motion Cues", body: `Could not save: ${error}` });
        const now = Date.now() / 1000;
        setPanelProblem({
          key: "panel:settings-save",
          severity: "error",
          source: "panel",
          title: "A setting could not be saved",
          detail: String(error),
          hint: "The change is applied locally but may be lost on restart.",
          first_seen: now,
          last_seen: now,
          count: 1,
        });
      }
    }, 180) as unknown as number;
  }, []);

  const withBusy = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  }, []);

  const dismissProblem = useCallback(async (key: string) => {
    if (key.startsWith("panel:")) {
      setPanelProblem(null);
      return;
    }
    setProblems((current) => current.filter((problem) => problem.key !== key));
    try {
      await clearProblems(key);
    } catch {
      // The backend is unreachable, which refreshStatus will report on its
      // next pass; the entry is already gone from the list locally.
    }
  }, []);

  const dismissAllProblems = useCallback(async () => {
    setPanelProblem(null);
    setProblems([]);
    try {
      await clearProblems(null);
    } catch {
      /* same as above: reported by the next status poll */
    }
  }, []);

  // Panel-local failures lead, because if the backend is unreachable the
  // entries from it are stale by definition.
  const allProblems = panelProblem ? [panelProblem, ...problems] : problems;

  if (!config) {
    return (
      <>
        <ProblemsPanel
          problems={allProblems}
          busy={busy}
          onDismiss={(key) => void dismissProblem(key)}
          onDismissAll={() => void dismissAllProblems()}
        />
        <PanelSection title="Motion Cues">
          <PanelSectionRow>
            <Field label={allProblems.length ? "Not available" : "Loading…"} />
          </PanelSectionRow>
        </PanelSection>
      </>
    );
  }

  const appearance = config.appearance;
  const motion = config.motion;
  const auto = config.auto;
  const runtime = config.runtime;
  const overlay = status?.overlay ?? null;
  const engaged = overlay?.motion.engaged ?? false;

  const toggleEdge = (edge: Edge, enabled: boolean) => {
    const next = enabled
      ? [...appearance.edges, edge]
      : appearance.edges.filter((item) => item !== edge);
    patch({ appearance: { edges: next.length ? next : appearance.edges } });
  };

  return (
    <>
      <ProblemsPanel
        problems={allProblems}
        busy={busy}
        onDismiss={(key) => void dismissProblem(key)}
        onDismissAll={() => void dismissAllProblems()}
      />

      <PanelSection title="Motion Cues">
        <PanelSectionRow>
          <DropdownItem
            label="Mode"
            description={
              config.mode === "auto"
                ? engaged
                  ? "Automatic — vehicle motion detected, cues active"
                  : "Automatic — waiting for sustained vehicle motion"
                : config.mode === "on"
                  ? "Cues are always visible"
                  : "Cues are off and the overlay process is stopped"
            }
            rgOptions={MODE_OPTIONS.map((option) => ({
              data: option.data,
              label: option.label,
            }))}
            selectedOption={config.mode}
            onChange={(option) => patch({ mode: option.data as Mode })}
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <Field
            label="Rendering"
            description={
              overlay?.window_error
                ? overlay.window_error
                : status?.slot.mangoapp_running
                  ? "mangoapp also wants gamescope's overlay slot — see Advanced if dots don't appear over games"
                  : undefined
            }
            focusable={false}
          >
            {tierLabel(status?.tier ?? "none")}
          </Field>
        </PanelSectionRow>

        <PanelSectionRow>
          <Field
            label="Sensor"
            description={overlay?.sensor.detail}
            focusable={false}
          >
            {overlay
              ? `${overlay.sensor.source} · ${overlay.motion.rate_hz.toFixed(0)} Hz · ${overlay.fps.toFixed(0)} fps`
              : status?.overlay_running
                ? "starting…"
                : "overlay not running"}
          </Field>
        </PanelSectionRow>

        {runtime.debug_readout && overlay && (
          <PanelSectionRow>
            <Field label="Live motion" focusable={false}>
              <div style={{ fontFamily: "monospace", fontSize: "0.8em", lineHeight: 1.5 }}>
                <div>
                  dx {overlay.motion.dx.toFixed(1)} dy {overlay.motion.dy.toFixed(1)} α{" "}
                  {overlay.motion.alpha.toFixed(2)}
                </div>
                <div>
                  lon {overlay.motion.longitudinal.toFixed(3)} lat{" "}
                  {overlay.motion.lateral.toFixed(3)} yaw {overlay.motion.yaw_rate.toFixed(1)}
                </div>
                <div>
                  gravity [{overlay.motion.gravity.map((v) => v.toFixed(2)).join(", ")}]
                </div>
                <div>
                  energy {overlay.motion.accel_energy.toFixed(4)} g · gyro{" "}
                  {overlay.motion.gyro_energy.toFixed(1)} °/s · auto{" "}
                  {(overlay.motion.auto_progress * 100).toFixed(0)}%
                </div>
              </div>
            </Field>
          </PanelSectionRow>
        )}
      </PanelSection>

      <PanelSection title="Presets">
        <PanelSectionRow>
          <DropdownItem
            label="Load preset"
            rgOptions={presets.map((preset) => ({
              data: preset.name,
              label: preset.builtin ? preset.name : `${preset.name} *`,
            }))}
            selectedOption={config.active_preset}
            strDefaultLabel="Select a preset"
            onChange={(option) =>
              withBusy(async () => {
                const result = await loadPreset(option.data as string);
                if (result.ok && result.config) {
                  cachedConfig = result.config;
                  setConfigState(result.config);
                  toaster.toast({ title: "Motion Cues", body: `Loaded “${option.data}”` });
                } else {
                  toaster.toast({ title: "Motion Cues", body: result.error ?? "Load failed" });
                }
              })
            }
          />
        </PanelSectionRow>

        <PanelSectionRow>
          <TextField
            label="Save current settings as"
            description="Name this configuration, then press Save preset"
            value={presetName}
            onChange={(event) => setPresetName(event.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || presetName.trim().length === 0}
            onClick={() =>
              withBusy(async () => {
                const result = await savePreset(presetName.trim());
                if (result.ok) {
                  setPresets(await listPresets());
                  setPresetName("");
                  toaster.toast({ title: "Motion Cues", body: "Preset saved" });
                } else {
                  toaster.toast({ title: "Motion Cues", body: result.error ?? "Save failed" });
                }
              })
            }
          >
            Save preset
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || !config.active_preset}
            onClick={() => {
              const name = config.active_preset;
              showModal(
                <ConfirmModal
                  strTitle={`Delete “${name}”?`}
                  strDescription={
                    presets.find((preset) => preset.name === name)?.builtin
                      ? "This is a built-in preset. Deleting it restores the shipped defaults for that preset."
                      : "This removes the saved preset. Your current settings are not changed."
                  }
                  onOK={() =>
                    withBusy(async () => {
                      const result = await deletePreset(name);
                      if (result.ok) {
                        setPresets(await listPresets());
                        setConfigState(await getConfig());
                        toaster.toast({
                          title: "Motion Cues",
                          body: result.restored_builtin
                            ? "Built-in preset restored to defaults"
                            : "Preset deleted",
                        });
                      } else {
                        toaster.toast({ title: "Motion Cues", body: result.error ?? "Delete failed" });
                      }
                    })
                  }
                />,
              );
            }}
          >
            Delete “{config.active_preset || "—"}”
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Appearance">
        <PanelSectionRow>
          <ToggleField
            label="Show controls"
            checked={showAppearance}
            onChange={setShowAppearance}
          />
        </PanelSectionRow>
        {showAppearance && (
          <>
            <PanelSectionRow>
              <SliderField
                label="Dots per edge"
                value={appearance.count}
                min={1}
                max={40}
                step={1}
                showValue
                onChange={(value) => patch({ appearance: { count: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Dot size"
                value={appearance.size}
                min={2}
                max={40}
                step={0.5}
                showValue
                valueSuffix=" px"
                onChange={(value) => patch({ appearance: { size: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Opacity"
                value={Math.round(appearance.opacity * 100)}
                min={2}
                max={100}
                step={1}
                showValue
                valueSuffix="%"
                onChange={(value) => patch({ appearance: { opacity: value / 100 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <DropdownItem
                label="Shape"
                rgOptions={SHAPE_OPTIONS}
                selectedOption={appearance.shape}
                onChange={(option) => patch({ appearance: { shape: option.data } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <DropdownItem
                label="Colour"
                rgOptions={COLOR_OPTIONS}
                selectedOption={appearance.color}
                onChange={(option) => patch({ appearance: { color: option.data } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <TextField
                label="Custom colour (hex)"
                value={appearance.color}
                onChange={(event) => {
                  const value = event.target.value.trim();
                  if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value)) {
                    patch({ appearance: { color: value } });
                  }
                }}
              />
            </PanelSectionRow>
            {EDGES.map((edge) => (
              <PanelSectionRow key={edge}>
                <ToggleField
                  label={`${edge[0].toUpperCase()}${edge.slice(1)} edge`}
                  checked={appearance.edges.includes(edge)}
                  onChange={(checked) => toggleEdge(edge, checked)}
                />
              </PanelSectionRow>
            ))}
            <PanelSectionRow>
              <SliderField
                label="Edge padding"
                value={appearance.edge_padding}
                min={0}
                max={200}
                step={1}
                showValue
                valueSuffix=" px"
                onChange={(value) => patch({ appearance: { edge_padding: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <DropdownItem
                label="Distribution"
                rgOptions={LAYOUT_OPTIONS}
                selectedOption={appearance.layout}
                onChange={(option) => patch({ appearance: { layout: option.data } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="End margin"
                value={Math.round(appearance.margin_fraction * 100)}
                min={0}
                max={45}
                step={1}
                showValue
                valueSuffix="%"
                onChange={(value) => patch({ appearance: { margin_fraction: value / 100 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Outline width"
                value={appearance.outline}
                min={0}
                max={4}
                step={0.5}
                showValue
                valueSuffix=" px"
                onChange={(value) => patch({ appearance: { outline: value } })}
              />
            </PanelSectionRow>
          </>
        )}
      </PanelSection>

      <PanelSection title="Motion response">
        <PanelSectionRow>
          <ToggleField label="Show controls" checked={showMotion} onChange={setShowMotion} />
        </PanelSectionRow>
        {showMotion && (
          <>
            <PanelSectionRow>
              <SliderField
                label="Sideways sensitivity"
                description="Dot travel per g of lateral acceleration"
                value={motion.gain_x}
                min={0}
                max={400}
                step={5}
                showValue
                onChange={(value) => patch({ motion: { gain_x: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Fore/aft sensitivity"
                description="Dot travel per g of braking or acceleration"
                value={motion.gain_y}
                min={0}
                max={400}
                step={5}
                showValue
                onChange={(value) => patch({ motion: { gain_y: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Turn (gyro) sensitivity"
                value={motion.gyro_gain}
                min={0}
                max={4}
                step={0.05}
                showValue
                onChange={(value) => patch({ motion: { gyro_gain: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Maximum travel"
                value={motion.max_travel}
                min={4}
                max={200}
                step={2}
                showValue
                valueSuffix=" px"
                onChange={(value) => patch({ motion: { max_travel: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Smoothing"
                description="Higher is smoother but slower to respond"
                value={Math.round(motion.smoothing * 100)}
                min={0}
                max={99}
                step={1}
                showValue
                valueSuffix="%"
                onChange={(value) => patch({ motion: { smoothing: value / 100 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Return-to-centre speed"
                value={Math.round(motion.return_speed * 100)}
                min={1}
                max={100}
                step={1}
                showValue
                valueSuffix="%"
                onChange={(value) => patch({ motion: { return_speed: value / 100 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Dead zone"
                description="Ignore motion below this level"
                value={Math.round(motion.deadzone * 1000)}
                min={0}
                max={100}
                step={1}
                showValue
                valueSuffix=" mg"
                onChange={(value) => patch({ motion: { deadzone: value / 1000 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Bump response"
                description="How much vertical jolts move the dots"
                value={Math.round(motion.vertical_weight * 100)}
                min={0}
                max={200}
                step={5}
                showValue
                valueSuffix="%"
                onChange={(value) => patch({ motion: { vertical_weight: value / 100 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ToggleField
                label="Invert sideways"
                checked={motion.invert_x}
                onChange={(checked) => patch({ motion: { invert_x: checked } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ToggleField
                label="Invert fore/aft"
                checked={motion.invert_y}
                onChange={(checked) => patch({ motion: { invert_y: checked } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={() =>
                  withBusy(async () => {
                    const result = await calibrateOrientation();
                    if (result.ok && result.config) {
                      cachedConfig = result.config;
                      setConfigState(result.config);
                      toaster.toast({
                        title: "Motion Cues",
                        body: "Orientation calibrated from gravity",
                      });
                    } else {
                      toaster.toast({
                        title: "Motion Cues",
                        body: result.error ?? "Calibration failed",
                      });
                    }
                  })
                }
              >
                Calibrate orientation (hold the Deck normally)
              </ButtonItem>
            </PanelSectionRow>
          </>
        )}
      </PanelSection>

      <PanelSection title="Automatic detection">
        <PanelSectionRow>
          <ToggleField label="Show controls" checked={showAuto} onChange={setShowAuto} />
        </PanelSectionRow>
        {showAuto && (
          <>
            <PanelSectionRow>
              <SliderField
                label="Engage threshold"
                description="Vehicle motion energy needed to turn cues on"
                value={Math.round(auto.enter_threshold * 1000)}
                min={2}
                max={200}
                step={1}
                showValue
                valueSuffix=" mg"
                onChange={(value) => patch({ auto: { enter_threshold: value / 1000 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Disengage threshold"
                value={Math.round(auto.exit_threshold * 1000)}
                min={1}
                max={200}
                step={1}
                showValue
                valueSuffix=" mg"
                onChange={(value) => patch({ auto: { exit_threshold: value / 1000 } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Time before engaging"
                value={auto.enter_seconds}
                min={0.5}
                max={30}
                step={0.5}
                showValue
                valueSuffix=" s"
                onChange={(value) => patch({ auto: { enter_seconds: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Time before disengaging"
                value={auto.exit_seconds}
                min={1}
                max={120}
                step={1}
                showValue
                valueSuffix=" s"
                onChange={(value) => patch({ auto: { exit_seconds: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Handling rejection"
                description="Rotation above this is treated as you moving the Deck, not the vehicle"
                value={auto.handling_gyro_dps}
                min={5}
                max={300}
                step={5}
                showValue
                valueSuffix=" °/s"
                onChange={(value) => patch({ auto: { handling_gyro_dps: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <SliderField
                label="Fade time"
                value={auto.fade_seconds}
                min={0}
                max={6}
                step={0.1}
                showValue
                valueSuffix=" s"
                onChange={(value) => patch({ auto: { fade_seconds: value } })}
              />
            </PanelSectionRow>
          </>
        )}
      </PanelSection>

      <PanelSection title="Advanced">
        <PanelSectionRow>
          <ToggleField label="Show controls" checked={showAdvanced} onChange={setShowAdvanced} />
        </PanelSectionRow>
        {showAdvanced && (
          <>
            <PanelSectionRow>
              <DropdownItem
                label="Sensor source"
                rgOptions={SENSOR_OPTIONS}
                selectedOption={runtime.sensor_source}
                onChange={(option) => patch({ runtime: { sensor_source: option.data } })}
              />
            </PanelSectionRow>
            {runtime.sensor_source === "synthetic" && (
              <PanelSectionRow>
                <DropdownItem
                  label="Demo motion"
                  rgOptions={DEMO_PROFILES}
                  selectedOption={runtime.synthetic_profile}
                  onChange={(option) => patch({ runtime: { synthetic_profile: option.data } })}
                />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <SliderField
                label="Overlay frame rate"
                value={runtime.target_fps}
                min={15}
                max={144}
                step={1}
                showValue
                valueSuffix=" fps"
                onChange={(value) => patch({ runtime: { target_fps: value } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ToggleField
                label="Draw in Steam UI when the overlay can't"
                description="Fallback tier: covers Steam's own screens, not games"
                checked={runtime.fallback_steam_ui}
                onChange={(checked) => patch({ runtime: { fallback_steam_ui: checked } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ToggleField
                label="Show live motion readout"
                checked={runtime.debug_readout}
                onChange={(checked) => patch({ runtime: { debug_readout: checked } })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={() => withBusy(async () => setStatus(await restartOverlay()))}
              >
                Restart overlay process
              </ButtonItem>
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy || !status?.slot.mangoapp_running}
                onClick={() =>
                  showModal(
                    <ConfirmModal
                      strTitle="Take gamescope's overlay slot?"
                      strDescription={
                        "gamescope allows only one external overlay. mangoapp (Steam's performance overlay) normally holds it. " +
                        "Stopping mangoapp frees the slot for Motion Cues, but the performance overlay will stay off until you restart the Steam session."
                      }
                      onOK={() =>
                        withBusy(async () => {
                          const result = await claimOverlaySlot();
                          toaster.toast({ title: "Motion Cues", body: result.detail });
                          await refreshStatus();
                        })
                      }
                    />,
                  )
                }
              >
                Take overlay slot from mangoapp
              </ButtonItem>
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy || !!status?.slot.mangoapp_running}
                onClick={() =>
                  withBusy(async () => {
                    const result = await releaseOverlaySlot();
                    toaster.toast({ title: "Motion Cues", body: result.detail });
                    await refreshStatus();
                  })
                }
              >
                Restore performance overlay
              </ButtonItem>
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={() => withBusy(async () => setDiagnostics(await getDiagnostics()))}
              >
                Run diagnostics
              </ButtonItem>
            </PanelSectionRow>
            {diagnostics && (
              <PanelSectionRow>
                <Field label="Diagnostics" focusable={false}>
                  <div style={{ fontFamily: "monospace", fontSize: "0.75em", lineHeight: 1.5 }}>
                    {diagnostics.sensors.map((entry) => (
                      <div key={entry.source}>
                        {entry.available ? "✓" : "✗"} {entry.source}: {entry.detail}
                      </div>
                    ))}
                    {diagnostics.displays.map((entry) => (
                      <div key={entry.display}>
                        {entry.open ? "✓" : "✗"} {entry.display}: {entry.detail}
                      </div>
                    ))}
                    <div>{diagnostics.slot.detail}</div>
                  </div>
                </Field>
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={() =>
                  showModal(
                    <ConfirmModal
                      strTitle="Reset all settings?"
                      strDescription="Every option returns to its shipped default. Saved presets are kept."
                      onOK={() =>
                        withBusy(async () => {
                          const cfg = await resetConfig();
                          cachedConfig = cfg;
                          setConfigState(cfg);
                        })
                      }
                    />,
                  )
                }
              >
                Reset settings to defaults
              </ButtonItem>
            </PanelSectionRow>
          </>
        )}
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  // The fallback renderer only subscribes to motion while it can actually be
  // useful, so the event stream costs nothing in the normal case where the
  // gamescope overlay is doing the drawing.
  let subscribed = false;

  const evaluate = async () => {
    try {
      const [cfg, status] = await Promise.all([getConfig(), getStatus()]);
      cachedConfig = cfg;
      const needed =
        cfg.mode !== "off" &&
        cfg.runtime.fallback_steam_ui &&
        (status.tier === "none" || cfg.runtime.debug_readout);
      fallbackEnabled = needed;
      if (needed && !subscribed) {
        await subscribeMotion();
        subscribed = true;
      } else if (!needed && subscribed) {
        await unsubscribeMotion();
        subscribed = false;
      }
    } catch (error) {
      // The panel reports backend failures itself; this loop only manages the
      // fallback subscription, so log rather than fight over the UI.
      console.error("[Motion Cues] could not evaluate fallback state:", error);
    }
  };

  void evaluate();
  const interval = window.setInterval(evaluate, 5000);

  routerHook.addGlobalComponent(
    "MotionCuesOverlay",
    () => (
      <FallbackOverlay getConfig={() => cachedConfig} getEnabled={() => fallbackEnabled} />
    ),
  );

  return {
    name: "Motion Cues",
    titleView: <div className={staticClasses.Title}>Motion Cues</div>,
    content: <Content />,
    icon: <FaCarSide />,
    onDismount() {
      window.clearInterval(interval);
      routerHook.removeGlobalComponent("MotionCuesOverlay");
      if (subscribed) void unsubscribeMotion();
    },
  };
});
