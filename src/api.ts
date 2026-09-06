import { callable } from "@decky/api";

export type Mode = "auto" | "on" | "off";
export type Shape = "circle" | "ring" | "square" | "diamond";
export type Edge = "left" | "right" | "top" | "bottom";
export type Layout = "even" | "corners" | "clustered";
export type SensorSource = "auto" | "evdev" | "iio" | "hidraw" | "synthetic";
export type Axis = "x" | "y" | "z";

export interface Appearance {
  count: number;
  size: number;
  shape: Shape;
  color: string;
  opacity: number;
  edges: Edge[];
  edge_padding: number;
  layout: Layout;
  margin_fraction: number;
  outline: number;
  outline_color: string;
}

export interface Motion {
  gain_x: number;
  gain_y: number;
  gyro_gain: number;
  max_travel: number;
  vertical_weight: number;
  smoothing: number;
  return_speed: number;
  deadzone: number;
  invert_x: boolean;
  invert_y: boolean;
  axis_right: Axis;
  axis_right_sign: number;
  axis_up: Axis;
  axis_up_sign: number;
  gravity_tau: number;
}

export interface AutoSettings {
  enter_threshold: number;
  exit_threshold: number;
  enter_seconds: number;
  exit_seconds: number;
  handling_gyro_dps: number;
  fade_seconds: number;
}

export interface Runtime {
  sensor_source: SensorSource;
  target_fps: number;
  display: string;
  claim_overlay_slot: boolean;
  fallback_steam_ui: boolean;
  debug_readout: boolean;
  synthetic_profile: string;
}

export interface Config {
  version: number;
  mode: Mode;
  active_preset: string;
  appearance: Appearance;
  motion: Motion;
  auto: AutoSettings;
  runtime: Runtime;
}

export type ConfigPatch = {
  [K in keyof Config]?: Config[K] extends object ? Partial<Config[K]> : Config[K];
};

export interface MotionState {
  dx: number;
  dy: number;
  alpha: number;
  engaged: boolean;
  visible: boolean;
  longitudinal: number;
  lateral: number;
  vertical: number;
  yaw_rate: number;
  gravity: number[];
  accel_energy: number;
  gyro_energy: number;
  auto_progress: number;
  rate_hz: number;
}

export interface OverlayStatus {
  running: boolean;
  uptime: number;
  fps: number;
  frames: number;
  draws: number;
  mode: Mode;
  sensor: { source: string; detail: string; ok: boolean };
  window: null | {
    display: string;
    gamescope: boolean;
    width: number;
    height: number;
    mapped: boolean;
    click_through: boolean;
  };
  window_error: string;
  tier: string;
  motion: MotionState;
}

export interface Problem {
  key: string;
  severity: "error" | "warning";
  source: string;
  title: string;
  detail: string;
  hint: string;
  first_seen: number;
  last_seen: number;
  count: number;
}

export interface Status {
  overlay_running: boolean;
  overlay: OverlayStatus | null;
  error: string;
  restarts: number;
  slot: { mangoapp_running: boolean; mangoapp_pids: number[]; detail: string };
  tier: string;
  problems: Problem[];
}

export interface Diagnostics {
  sensors: { source: string; available: boolean; detail: string }[];
  displays: { display: string; open: boolean; gamescope: boolean; detail: string }[];
  display_error?: string;
  slot: { mangoapp_running: boolean; mangoapp_pids: number[]; detail: string };
  python: string;
  settings_dir: string;
}

export interface PresetInfo {
  name: string;
  builtin: boolean;
}

export const getConfig = callable<[], Config>("get_config");
export const setConfig = callable<[patch: ConfigPatch], Config>("set_config");
export const setMode = callable<[mode: Mode], Config>("set_mode");
export const resetConfig = callable<[], Config>("reset_config");

export const listPresets = callable<[], PresetInfo[]>("list_presets");
export const savePreset = callable<[name: string], { ok: boolean; error?: string }>("save_preset");
export const loadPreset = callable<[name: string], { ok: boolean; error?: string; config?: Config }>("load_preset");
export const deletePreset = callable<[name: string], { ok: boolean; error?: string; restored_builtin?: boolean }>("delete_preset");

export const getStatus = callable<[], Status>("get_status");
export const getProblems = callable<[], Problem[]>("get_problems");
export const clearProblems = callable<[key: string | null], { ok: boolean; cleared: number }>("clear_problems");
export const getDiagnostics = callable<[], Diagnostics>("get_diagnostics");
export const calibrateOrientation = callable<[], { ok: boolean; error?: string; config?: Config }>("calibrate_orientation");
export const claimOverlaySlot = callable<[], { ok: boolean; detail: string }>("claim_overlay_slot");
export const releaseOverlaySlot = callable<[], { ok: boolean; detail: string }>("release_overlay_slot");
export const restartOverlay = callable<[], Status>("restart_overlay");

export const subscribeMotion = callable<[], { ok: boolean }>("subscribe_motion");
export const unsubscribeMotion = callable<[], { ok: boolean }>("unsubscribe_motion");

export const EDGES: Edge[] = ["left", "right", "top", "bottom"];

export const SHAPE_OPTIONS: { data: Shape; label: string }[] = [
  { data: "circle", label: "Circle" },
  { data: "ring", label: "Ring" },
  { data: "square", label: "Square" },
  { data: "diamond", label: "Diamond" },
];

export const LAYOUT_OPTIONS: { data: Layout; label: string }[] = [
  { data: "even", label: "Even" },
  { data: "corners", label: "Corners" },
  { data: "clustered", label: "Clustered" },
];

export const COLOR_OPTIONS: { data: string; label: string }[] = [
  { data: "#FFFFFF", label: "White" },
  { data: "#D0D8E0", label: "Cool grey" },
  { data: "#FFD9A0", label: "Warm amber" },
  { data: "#9FE8B0", label: "Soft green" },
  { data: "#A8C8FF", label: "Soft blue" },
  { data: "#000000", label: "Black" },
];

export const SENSOR_OPTIONS: { data: SensorSource; label: string }[] = [
  { data: "auto", label: "Automatic" },
  { data: "evdev", label: "Kernel motion node" },
  { data: "iio", label: "IIO sysfs" },
  { data: "hidraw", label: "hidraw (direct)" },
  { data: "synthetic", label: "Demo (simulated)" },
];

export const DEMO_PROFILES: { data: string; label: string }[] = [
  { data: "city", label: "City driving" },
  { data: "highway", label: "Highway" },
  { data: "train", label: "Train" },
  { data: "boat", label: "Boat" },
  { data: "handling", label: "Handheld (should not engage)" },
  { data: "still", label: "Stationary" },
];
