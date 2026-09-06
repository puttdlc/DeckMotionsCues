const manifest = {"name":"Motion Cues"};
const API_VERSION = 2;
const internalAPIConnection = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
if (!internalAPIConnection) {
    throw new Error('[@decky/api]: Failed to connect to the loader as as the loader API was not initialized. This is likely a bug in Decky Loader.');
}
let api;
try {
    api = internalAPIConnection.connect(API_VERSION, manifest.name);
}
catch {
    api = internalAPIConnection.connect(1, manifest.name);
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version 1. Some features may not work.`);
}
if (api._version != API_VERSION) {
    console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version ${api._version}. Some features may not work.`);
}
const callable = api.callable;
const addEventListener = api.addEventListener;
const removeEventListener = api.removeEventListener;
const routerHook = api.routerHook;
const toaster = api.toaster;
const definePlugin = (fn) => {
    return (...args) => {
        return fn(...args);
    };
};

var DefaultContext = {
  color: undefined,
  size: undefined,
  className: undefined,
  style: undefined,
  attr: undefined
};
var IconContext = SP_REACT.createContext && /*#__PURE__*/SP_REACT.createContext(DefaultContext);

var _excluded = ["attr", "size", "title"];
function _objectWithoutProperties(e, t) { if (null == e) return {}; var o, r, i = _objectWithoutPropertiesLoose(e, t); if (Object.getOwnPropertySymbols) { var n = Object.getOwnPropertySymbols(e); for (r = 0; r < n.length; r++) o = n[r], -1 === t.indexOf(o) && {}.propertyIsEnumerable.call(e, o) && (i[o] = e[o]); } return i; }
function _objectWithoutPropertiesLoose(r, e) { if (null == r) return {}; var t = {}; for (var n in r) if ({}.hasOwnProperty.call(r, n)) { if (-1 !== e.indexOf(n)) continue; t[n] = r[n]; } return t; }
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
function ownKeys(e, r) { var t = Object.keys(e); if (Object.getOwnPropertySymbols) { var o = Object.getOwnPropertySymbols(e); r && (o = o.filter(function (r) { return Object.getOwnPropertyDescriptor(e, r).enumerable; })), t.push.apply(t, o); } return t; }
function _objectSpread(e) { for (var r = 1; r < arguments.length; r++) { var t = null != arguments[r] ? arguments[r] : {}; r % 2 ? ownKeys(Object(t), true).forEach(function (r) { _defineProperty(e, r, t[r]); }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(t)) : ownKeys(Object(t)).forEach(function (r) { Object.defineProperty(e, r, Object.getOwnPropertyDescriptor(t, r)); }); } return e; }
function _defineProperty(e, r, t) { return (r = _toPropertyKey(r)) in e ? Object.defineProperty(e, r, { value: t, enumerable: true, configurable: true, writable: true }) : e[r] = t, e; }
function _toPropertyKey(t) { var i = _toPrimitive(t, "string"); return "symbol" == typeof i ? i : i + ""; }
function _toPrimitive(t, r) { if ("object" != typeof t || !t) return t; var e = t[Symbol.toPrimitive]; if (void 0 !== e) { var i = e.call(t, r); if ("object" != typeof i) return i; throw new TypeError("@@toPrimitive must return a primitive value."); } return ("string" === r ? String : Number)(t); }
function Tree2Element(tree) {
  return tree && tree.map((node, i) => /*#__PURE__*/SP_REACT.createElement(node.tag, _objectSpread({
    key: i
  }, node.attr), Tree2Element(node.child)));
}
function GenIcon(data) {
  return props => /*#__PURE__*/SP_REACT.createElement(IconBase, _extends({
    attr: _objectSpread({}, data.attr)
  }, props), Tree2Element(data.child));
}
function IconBase(props) {
  var elem = conf => {
    var attr = props.attr,
      size = props.size,
      title = props.title,
      svgProps = _objectWithoutProperties(props, _excluded);
    var computedSize = size || conf.size || "1em";
    var className;
    if (conf.className) className = conf.className;
    if (props.className) className = (className ? className + " " : "") + props.className;
    return /*#__PURE__*/SP_REACT.createElement("svg", _extends({
      stroke: "currentColor",
      fill: "currentColor",
      strokeWidth: "0"
    }, conf.attr, attr, svgProps, {
      className: className,
      style: _objectSpread(_objectSpread({
        color: props.color || conf.color
      }, conf.style), props.style),
      height: computedSize,
      width: computedSize,
      xmlns: "http://www.w3.org/2000/svg"
    }), title && /*#__PURE__*/SP_REACT.createElement("title", null, title), props.children);
  };
  return IconContext !== undefined ? /*#__PURE__*/SP_REACT.createElement(IconContext.Consumer, null, conf => elem(conf)) : elem(DefaultContext);
}

// THIS FILE IS AUTO GENERATED
function FaCarSide (props) {
  return GenIcon({"attr":{"viewBox":"0 0 640 512"},"child":[{"tag":"path","attr":{"d":"M544 192h-16L419.22 56.02A64.025 64.025 0 0 0 369.24 32H155.33c-26.17 0-49.7 15.93-59.42 40.23L48 194.26C20.44 201.4 0 226.21 0 256v112c0 8.84 7.16 16 16 16h48c0 53.02 42.98 96 96 96s96-42.98 96-96h128c0 53.02 42.98 96 96 96s96-42.98 96-96h48c8.84 0 16-7.16 16-16v-80c0-53.02-42.98-96-96-96zM160 432c-26.47 0-48-21.53-48-48s21.53-48 48-48 48 21.53 48 48-21.53 48-48 48zm72-240H116.93l38.4-96H232v96zm48 0V96h89.24l76.8 96H280zm200 240c-26.47 0-48-21.53-48-48s21.53-48 48-48 48 21.53 48 48-21.53 48-48 48z"},"child":[]}]})(props);
}

const getConfig = callable("get_config");
const setConfig = callable("set_config");
callable("set_mode");
const resetConfig = callable("reset_config");
const listPresets = callable("list_presets");
const savePreset = callable("save_preset");
const loadPreset = callable("load_preset");
const deletePreset = callable("delete_preset");
const getStatus = callable("get_status");
callable("get_problems");
const clearProblems = callable("clear_problems");
const getDiagnostics = callable("get_diagnostics");
const calibrateOrientation = callable("calibrate_orientation");
const claimOverlaySlot = callable("claim_overlay_slot");
const releaseOverlaySlot = callable("release_overlay_slot");
const restartOverlay = callable("restart_overlay");
const subscribeMotion = callable("subscribe_motion");
const unsubscribeMotion = callable("unsubscribe_motion");
const EDGES = ["left", "right", "top", "bottom"];
const SHAPE_OPTIONS = [
    { data: "circle", label: "Circle" },
    { data: "ring", label: "Ring" },
    { data: "square", label: "Square" },
    { data: "diamond", label: "Diamond" },
];
const LAYOUT_OPTIONS = [
    { data: "even", label: "Even" },
    { data: "corners", label: "Corners" },
    { data: "clustered", label: "Clustered" },
];
const COLOR_OPTIONS = [
    { data: "#FFFFFF", label: "White" },
    { data: "#D0D8E0", label: "Cool grey" },
    { data: "#FFD9A0", label: "Warm amber" },
    { data: "#9FE8B0", label: "Soft green" },
    { data: "#A8C8FF", label: "Soft blue" },
    { data: "#000000", label: "Black" },
];
const SENSOR_OPTIONS = [
    { data: "auto", label: "Automatic" },
    { data: "evdev", label: "Kernel motion node" },
    { data: "iio", label: "IIO sysfs" },
    { data: "hidraw", label: "hidraw (direct)" },
    { data: "synthetic", label: "Demo (simulated)" },
];
const DEMO_PROFILES = [
    { data: "city", label: "City driving" },
    { data: "highway", label: "Highway" },
    { data: "train", label: "Train" },
    { data: "boat", label: "Boat" },
    { data: "handling", label: "Handheld (should not engage)" },
    { data: "still", label: "Stationary" },
];

function edgePositions(config, width, height) {
    const { count, edge_padding, edges, margin_fraction, layout } = config.appearance;
    const spread = [];
    if (layout === "corners") {
        const half = Math.floor(count / 2);
        const extra = count - half * 2;
        const cluster = (1 - 2 * margin_fraction) * 0.28;
        for (let group = 0; group < 2; group += 1) {
            const n = half + (group === 0 ? extra : 0);
            if (n <= 0)
                continue;
            const base = group === 0 ? margin_fraction : 1 - margin_fraction - cluster;
            const step = n > 1 ? cluster / (n - 1) : 0;
            for (let i = 0; i < n; i += 1)
                spread.push(base + step * i);
        }
    }
    else {
        const span = 1 - 2 * margin_fraction;
        for (let i = 0; i < count; i += 1) {
            const t = (i + 0.5) / count;
            const eased = layout === "clustered" ? t * t * (3 - 2 * t) : t;
            spread.push(margin_fraction + span * eased);
        }
    }
    const points = [];
    for (const edge of edges) {
        for (const t of spread) {
            if (edge === "left")
                points.push({ x: edge_padding, y: t * height });
            else if (edge === "right")
                points.push({ x: width - edge_padding, y: t * height });
            else if (edge === "top")
                points.push({ x: t * width, y: edge_padding });
            else
                points.push({ x: t * width, y: height - edge_padding });
        }
    }
    return points;
}
function borderRadiusFor(shape) {
    if (shape === "circle" || shape === "ring")
        return "50%";
    return "0";
}
const FallbackOverlay = ({ getConfig, getEnabled }) => {
    const [motion, setMotion] = SP_REACT.useState(null);
    const [tick, setTick] = SP_REACT.useState(0);
    SP_REACT.useEffect(() => {
        const listener = addEventListener("motion", (state) => {
            setMotion(state);
        });
        // Config changes arrive through the panel, not the event bus; a slow tick
        // keeps this component in step without polling the backend.
        const timer = window.setInterval(() => setTick((value) => value + 1), 500);
        return () => {
            removeEventListener("motion", listener);
            window.clearInterval(timer);
        };
    }, []);
    const config = getConfig();
    if (!config || !getEnabled() || !motion || motion.alpha <= 0.004)
        return null;
    const width = window.innerWidth || 1280;
    const height = window.innerHeight || 800;
    const points = edgePositions(config, width, height);
    const { size, color, opacity, shape, outline, outline_color } = config.appearance;
    return (SP_JSX.jsx("div", { style: {
            position: "fixed",
            inset: 0,
            pointerEvents: "none",
            zIndex: 7000,
            opacity: motion.alpha,
        }, children: points.map((point, index) => (SP_JSX.jsx("div", { style: {
                position: "absolute",
                left: `${point.x + motion.dx - size / 2}px`,
                top: `${point.y + motion.dy - size / 2}px`,
                width: `${size}px`,
                height: `${size}px`,
                borderRadius: borderRadiusFor(shape),
                backgroundColor: shape === "ring" ? "transparent" : color,
                border: shape === "ring"
                    ? `${Math.max(1, size * 0.22)}px solid ${color}`
                    : outline > 0
                        ? `${outline}px solid ${outline_color}`
                        : undefined,
                opacity,
                transform: shape === "diamond" ? "rotate(45deg)" : undefined,
                willChange: "left, top",
            } }, index))) }));
};

const SEVERITY_COLOUR = {
    error: "#ff6b6b",
    warning: "#ffc046",
};
function relativeTime(seconds) {
    const delta = Date.now() / 1000 - seconds;
    if (!Number.isFinite(delta) || delta < 0)
        return "just now";
    if (delta < 45)
        return "just now";
    if (delta < 90)
        return "a minute ago";
    if (delta < 3600)
        return `${Math.round(delta / 60)} minutes ago`;
    if (delta < 7200)
        return "an hour ago";
    if (delta < 86400)
        return `${Math.round(delta / 3600)} hours ago`;
    return `${Math.round(delta / 86400)} days ago`;
}
const ProblemsPanel = ({ problems, busy, onDismiss, onDismissAll }) => {
    if (problems.length === 0)
        return null;
    const errors = problems.filter((problem) => problem.severity === "error").length;
    const title = errors > 0
        ? `Problems (${problems.length})`
        : `Warnings (${problems.length})`;
    return (SP_JSX.jsxs(DFL.PanelSection, { title: title, children: [problems.map((problem) => {
                const colour = SEVERITY_COLOUR[problem.severity] ?? SEVERITY_COLOUR.error;
                return (SP_JSX.jsxs(SP_REACT.Fragment, { children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { focusable: false, bottomSeparator: "none", label: SP_JSX.jsxs("div", { style: { display: "flex", alignItems: "center", gap: "6px" }, children: [SP_JSX.jsx("span", { style: {
                                                display: "inline-block",
                                                width: "8px",
                                                height: "8px",
                                                borderRadius: "50%",
                                                backgroundColor: colour,
                                                flexShrink: 0,
                                            } }), SP_JSX.jsx("span", { style: { color: colour }, children: problem.title }), problem.count > 1 && (SP_JSX.jsxs("span", { style: { opacity: 0.7, fontSize: "0.85em" }, children: ["\u00D7", problem.count] }))] }), children: SP_JSX.jsx("div", { style: { fontSize: "0.85em", opacity: 0.85, textAlign: "left" }, children: relativeTime(problem.last_seen) }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { focusable: false, bottomSeparator: "none", children: SP_JSX.jsxs("div", { style: {
                                        fontSize: "0.85em",
                                        lineHeight: 1.45,
                                        textAlign: "left",
                                        whiteSpace: "pre-wrap",
                                        wordBreak: "break-word",
                                    }, children: [SP_JSX.jsx("div", { children: problem.detail }), problem.hint && (SP_JSX.jsxs("div", { style: { marginTop: "4px", opacity: 0.75 }, children: ["\u2192 ", problem.hint] })), SP_JSX.jsxs("div", { style: { marginTop: "4px", opacity: 0.5, fontSize: "0.9em" }, children: ["source: ", problem.source] })] }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy, onClick: () => onDismiss(problem.key), children: "Dismiss" }) })] }, problem.key));
            }), problems.length > 1 && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsxs(DFL.ButtonItem, { layout: "below", disabled: busy, onClick: onDismissAll, children: ["Dismiss all ", problems.length] }) }))] }));
};

const MODE_OPTIONS = [
    { data: "auto", label: "Automatic" },
    { data: "on", label: "Always On" },
    { data: "off", label: "Off" },
];
/** Shared config cache so the global overlay component can read it too. */
let cachedConfig = null;
let fallbackEnabled = false;
function tierLabel(tier) {
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
    const [config, setConfigState] = SP_REACT.useState(cachedConfig);
    const [status, setStatus] = SP_REACT.useState(null);
    const [presets, setPresets] = SP_REACT.useState([]);
    const [diagnostics, setDiagnostics] = SP_REACT.useState(null);
    const [presetName, setPresetName] = SP_REACT.useState("");
    const [showAppearance, setShowAppearance] = SP_REACT.useState(false);
    const [showMotion, setShowMotion] = SP_REACT.useState(false);
    const [showAuto, setShowAuto] = SP_REACT.useState(false);
    const [showAdvanced, setShowAdvanced] = SP_REACT.useState(false);
    const [busy, setBusy] = SP_REACT.useState(false);
    const [problems, setProblems] = SP_REACT.useState([]);
    // Raised when the panel itself cannot reach the backend, so a dead backend
    // is visible rather than looking like "nothing is wrong".
    const [panelProblem, setPanelProblem] = SP_REACT.useState(null);
    const pending = SP_REACT.useRef({});
    const timer = SP_REACT.useRef(null);
    const refreshStatus = SP_REACT.useCallback(async () => {
        try {
            const next = await getStatus();
            setStatus(next);
            setProblems(next.problems ?? []);
            setPanelProblem(null);
        }
        catch (error) {
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
    SP_REACT.useEffect(() => {
        (async () => {
            try {
                const [cfg, presetList] = await Promise.all([getConfig(), listPresets()]);
                cachedConfig = cfg;
                setConfigState(cfg);
                setPresets(presetList);
            }
            catch (error) {
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
    const patch = SP_REACT.useCallback((update) => {
        setConfigState((current) => {
            if (!current)
                return current;
            const next = { ...current };
            for (const [key, value] of Object.entries(update)) {
                const typedKey = key;
                if (value && typeof value === "object" && !Array.isArray(value)) {
                    next[typedKey] = {
                        ...current[typedKey],
                        ...value,
                    };
                }
                else {
                    next[typedKey] = value;
                }
            }
            cachedConfig = next;
            return next;
        });
        for (const [key, value] of Object.entries(update)) {
            const typedKey = key;
            if (value && typeof value === "object" && !Array.isArray(value)) {
                pending.current[typedKey] = {
                    ...(pending.current[typedKey] ?? {}),
                    ...value,
                };
            }
            else {
                pending.current[typedKey] = value;
            }
        }
        if (timer.current !== null)
            window.clearTimeout(timer.current);
        timer.current = window.setTimeout(async () => {
            const body = pending.current;
            pending.current = {};
            timer.current = null;
            try {
                const saved = await setConfig(body);
                cachedConfig = saved;
                setConfigState(saved);
            }
            catch (error) {
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
        }, 180);
    }, []);
    const withBusy = SP_REACT.useCallback(async (action) => {
        setBusy(true);
        try {
            await action();
        }
        finally {
            setBusy(false);
        }
    }, []);
    const dismissProblem = SP_REACT.useCallback(async (key) => {
        if (key.startsWith("panel:")) {
            setPanelProblem(null);
            return;
        }
        setProblems((current) => current.filter((problem) => problem.key !== key));
        try {
            await clearProblems(key);
        }
        catch {
            // The backend is unreachable, which refreshStatus will report on its
            // next pass; the entry is already gone from the list locally.
        }
    }, []);
    const dismissAllProblems = SP_REACT.useCallback(async () => {
        setPanelProblem(null);
        setProblems([]);
        try {
            await clearProblems(null);
        }
        catch {
            /* same as above: reported by the next status poll */
        }
    }, []);
    // Panel-local failures lead, because if the backend is unreachable the
    // entries from it are stale by definition.
    const allProblems = panelProblem ? [panelProblem, ...problems] : problems;
    if (!config) {
        return (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(ProblemsPanel, { problems: allProblems, busy: busy, onDismiss: (key) => void dismissProblem(key), onDismissAll: () => void dismissAllProblems() }), SP_JSX.jsx(DFL.PanelSection, { title: "Motion Cues", children: SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: allProblems.length ? "Not available" : "Loading…" }) }) })] }));
    }
    const appearance = config.appearance;
    const motion = config.motion;
    const auto = config.auto;
    const runtime = config.runtime;
    const overlay = status?.overlay ?? null;
    const engaged = overlay?.motion.engaged ?? false;
    const toggleEdge = (edge, enabled) => {
        const next = enabled
            ? [...appearance.edges, edge]
            : appearance.edges.filter((item) => item !== edge);
        patch({ appearance: { edges: next.length ? next : appearance.edges } });
    };
    return (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(ProblemsPanel, { problems: allProblems, busy: busy, onDismiss: (key) => void dismissProblem(key), onDismissAll: () => void dismissAllProblems() }), SP_JSX.jsxs(DFL.PanelSection, { title: "Motion Cues", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Mode", description: config.mode === "auto"
                                ? engaged
                                    ? "Automatic — vehicle motion detected, cues active"
                                    : "Automatic — waiting for sustained vehicle motion"
                                : config.mode === "on"
                                    ? "Cues are always visible"
                                    : "Cues are off and the overlay process is stopped", rgOptions: MODE_OPTIONS.map((option) => ({
                                data: option.data,
                                label: option.label,
                            })), selectedOption: config.mode, onChange: (option) => patch({ mode: option.data }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Rendering", description: overlay?.window_error
                                ? overlay.window_error
                                : status?.slot.mangoapp_running
                                    ? "mangoapp also wants gamescope's overlay slot — see Advanced if dots don't appear over games"
                                    : undefined, focusable: false, children: tierLabel(status?.tier ?? "none") }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Sensor", description: overlay?.sensor.detail, focusable: false, children: overlay
                                ? `${overlay.sensor.source} · ${overlay.motion.rate_hz.toFixed(0)} Hz · ${overlay.fps.toFixed(0)} fps`
                                : status?.overlay_running
                                    ? "starting…"
                                    : "overlay not running" }) }), runtime.debug_readout && overlay && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Live motion", focusable: false, children: SP_JSX.jsxs("div", { style: { fontFamily: "monospace", fontSize: "0.8em", lineHeight: 1.5 }, children: [SP_JSX.jsxs("div", { children: ["dx ", overlay.motion.dx.toFixed(1), " dy ", overlay.motion.dy.toFixed(1), " \u03B1", " ", overlay.motion.alpha.toFixed(2)] }), SP_JSX.jsxs("div", { children: ["lon ", overlay.motion.longitudinal.toFixed(3), " lat", " ", overlay.motion.lateral.toFixed(3), " yaw ", overlay.motion.yaw_rate.toFixed(1)] }), SP_JSX.jsxs("div", { children: ["gravity [", overlay.motion.gravity.map((v) => v.toFixed(2)).join(", "), "]"] }), SP_JSX.jsxs("div", { children: ["energy ", overlay.motion.accel_energy.toFixed(4), " g \u00B7 gyro", " ", overlay.motion.gyro_energy.toFixed(1), " \u00B0/s \u00B7 auto", " ", (overlay.motion.auto_progress * 100).toFixed(0), "%"] })] }) }) }))] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Presets", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Load preset", rgOptions: presets.map((preset) => ({
                                data: preset.name,
                                label: preset.builtin ? preset.name : `${preset.name} *`,
                            })), selectedOption: config.active_preset, strDefaultLabel: "Select a preset", onChange: (option) => withBusy(async () => {
                                const result = await loadPreset(option.data);
                                if (result.ok && result.config) {
                                    cachedConfig = result.config;
                                    setConfigState(result.config);
                                    toaster.toast({ title: "Motion Cues", body: `Loaded “${option.data}”` });
                                }
                                else {
                                    toaster.toast({ title: "Motion Cues", body: result.error ?? "Load failed" });
                                }
                            }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Save current settings as", description: "Name this configuration, then press Save preset", value: presetName, onChange: (event) => setPresetName(event.target.value) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy || presetName.trim().length === 0, onClick: () => withBusy(async () => {
                                const result = await savePreset(presetName.trim());
                                if (result.ok) {
                                    setPresets(await listPresets());
                                    setPresetName("");
                                    toaster.toast({ title: "Motion Cues", body: "Preset saved" });
                                }
                                else {
                                    toaster.toast({ title: "Motion Cues", body: result.error ?? "Save failed" });
                                }
                            }), children: "Save preset" }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsxs(DFL.ButtonItem, { layout: "below", disabled: busy || !config.active_preset, onClick: () => {
                                const name = config.active_preset;
                                DFL.showModal(SP_JSX.jsx(DFL.ConfirmModal, { strTitle: `Delete “${name}”?`, strDescription: presets.find((preset) => preset.name === name)?.builtin
                                        ? "This is a built-in preset. Deleting it restores the shipped defaults for that preset."
                                        : "This removes the saved preset. Your current settings are not changed.", onOK: () => withBusy(async () => {
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
                                        }
                                        else {
                                            toaster.toast({ title: "Motion Cues", body: result.error ?? "Delete failed" });
                                        }
                                    }) }));
                            }, children: ["Delete \u201C", config.active_preset || "—", "\u201D"] }) })] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Appearance", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Show controls", checked: showAppearance, onChange: setShowAppearance }) }), showAppearance && (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Dots per edge", value: appearance.count, min: 1, max: 40, step: 1, showValue: true, onChange: (value) => patch({ appearance: { count: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Dot size", value: appearance.size, min: 2, max: 40, step: 0.5, showValue: true, valueSuffix: " px", onChange: (value) => patch({ appearance: { size: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Opacity", value: Math.round(appearance.opacity * 100), min: 2, max: 100, step: 1, showValue: true, valueSuffix: "%", onChange: (value) => patch({ appearance: { opacity: value / 100 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Shape", rgOptions: SHAPE_OPTIONS, selectedOption: appearance.shape, onChange: (option) => patch({ appearance: { shape: option.data } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Colour", rgOptions: COLOR_OPTIONS, selectedOption: appearance.color, onChange: (option) => patch({ appearance: { color: option.data } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.TextField, { label: "Custom colour (hex)", value: appearance.color, onChange: (event) => {
                                        const value = event.target.value.trim();
                                        if (/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value)) {
                                            patch({ appearance: { color: value } });
                                        }
                                    } }) }), EDGES.map((edge) => (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: `${edge[0].toUpperCase()}${edge.slice(1)} edge`, checked: appearance.edges.includes(edge), onChange: (checked) => toggleEdge(edge, checked) }) }, edge))), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Edge padding", value: appearance.edge_padding, min: 0, max: 200, step: 1, showValue: true, valueSuffix: " px", onChange: (value) => patch({ appearance: { edge_padding: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Distribution", rgOptions: LAYOUT_OPTIONS, selectedOption: appearance.layout, onChange: (option) => patch({ appearance: { layout: option.data } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "End margin", value: Math.round(appearance.margin_fraction * 100), min: 0, max: 45, step: 1, showValue: true, valueSuffix: "%", onChange: (value) => patch({ appearance: { margin_fraction: value / 100 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Outline width", value: appearance.outline, min: 0, max: 4, step: 0.5, showValue: true, valueSuffix: " px", onChange: (value) => patch({ appearance: { outline: value } }) }) })] }))] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Motion response", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Show controls", checked: showMotion, onChange: setShowMotion }) }), showMotion && (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Sideways sensitivity", description: "Dot travel per g of lateral acceleration", value: motion.gain_x, min: 0, max: 400, step: 5, showValue: true, onChange: (value) => patch({ motion: { gain_x: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Fore/aft sensitivity", description: "Dot travel per g of braking or acceleration", value: motion.gain_y, min: 0, max: 400, step: 5, showValue: true, onChange: (value) => patch({ motion: { gain_y: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Turn (gyro) sensitivity", value: motion.gyro_gain, min: 0, max: 4, step: 0.05, showValue: true, onChange: (value) => patch({ motion: { gyro_gain: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Maximum travel", value: motion.max_travel, min: 4, max: 200, step: 2, showValue: true, valueSuffix: " px", onChange: (value) => patch({ motion: { max_travel: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Smoothing", description: "Higher is smoother but slower to respond", value: Math.round(motion.smoothing * 100), min: 0, max: 99, step: 1, showValue: true, valueSuffix: "%", onChange: (value) => patch({ motion: { smoothing: value / 100 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Return-to-centre speed", value: Math.round(motion.return_speed * 100), min: 1, max: 100, step: 1, showValue: true, valueSuffix: "%", onChange: (value) => patch({ motion: { return_speed: value / 100 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Dead zone", description: "Ignore motion below this level", value: Math.round(motion.deadzone * 1000), min: 0, max: 100, step: 1, showValue: true, valueSuffix: " mg", onChange: (value) => patch({ motion: { deadzone: value / 1000 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Bump response", description: "How much vertical jolts move the dots", value: Math.round(motion.vertical_weight * 100), min: 0, max: 200, step: 5, showValue: true, valueSuffix: "%", onChange: (value) => patch({ motion: { vertical_weight: value / 100 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Invert sideways", checked: motion.invert_x, onChange: (checked) => patch({ motion: { invert_x: checked } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Invert fore/aft", checked: motion.invert_y, onChange: (checked) => patch({ motion: { invert_y: checked } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy, onClick: () => withBusy(async () => {
                                        const result = await calibrateOrientation();
                                        if (result.ok && result.config) {
                                            cachedConfig = result.config;
                                            setConfigState(result.config);
                                            toaster.toast({
                                                title: "Motion Cues",
                                                body: "Orientation calibrated from gravity",
                                            });
                                        }
                                        else {
                                            toaster.toast({
                                                title: "Motion Cues",
                                                body: result.error ?? "Calibration failed",
                                            });
                                        }
                                    }), children: "Calibrate orientation (hold the Deck normally)" }) })] }))] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Automatic detection", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Show controls", checked: showAuto, onChange: setShowAuto }) }), showAuto && (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Engage threshold", description: "Vehicle motion energy needed to turn cues on", value: Math.round(auto.enter_threshold * 1000), min: 2, max: 200, step: 1, showValue: true, valueSuffix: " mg", onChange: (value) => patch({ auto: { enter_threshold: value / 1000 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Disengage threshold", value: Math.round(auto.exit_threshold * 1000), min: 1, max: 200, step: 1, showValue: true, valueSuffix: " mg", onChange: (value) => patch({ auto: { exit_threshold: value / 1000 } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Time before engaging", value: auto.enter_seconds, min: 0.5, max: 30, step: 0.5, showValue: true, valueSuffix: " s", onChange: (value) => patch({ auto: { enter_seconds: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Time before disengaging", value: auto.exit_seconds, min: 1, max: 120, step: 1, showValue: true, valueSuffix: " s", onChange: (value) => patch({ auto: { exit_seconds: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Handling rejection", description: "Rotation above this is treated as you moving the Deck, not the vehicle", value: auto.handling_gyro_dps, min: 5, max: 300, step: 5, showValue: true, valueSuffix: " \u00B0/s", onChange: (value) => patch({ auto: { handling_gyro_dps: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Fade time", value: auto.fade_seconds, min: 0, max: 6, step: 0.1, showValue: true, valueSuffix: " s", onChange: (value) => patch({ auto: { fade_seconds: value } }) }) })] }))] }), SP_JSX.jsxs(DFL.PanelSection, { title: "Advanced", children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Show controls", checked: showAdvanced, onChange: setShowAdvanced }) }), showAdvanced && (SP_JSX.jsxs(SP_JSX.Fragment, { children: [SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Sensor source", rgOptions: SENSOR_OPTIONS, selectedOption: runtime.sensor_source, onChange: (option) => patch({ runtime: { sensor_source: option.data } }) }) }), runtime.sensor_source === "synthetic" && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.DropdownItem, { label: "Demo motion", rgOptions: DEMO_PROFILES, selectedOption: runtime.synthetic_profile, onChange: (option) => patch({ runtime: { synthetic_profile: option.data } }) }) })), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.SliderField, { label: "Overlay frame rate", value: runtime.target_fps, min: 15, max: 144, step: 1, showValue: true, valueSuffix: " fps", onChange: (value) => patch({ runtime: { target_fps: value } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Draw in Steam UI when the overlay can't", description: "Fallback tier: covers Steam's own screens, not games", checked: runtime.fallback_steam_ui, onChange: (checked) => patch({ runtime: { fallback_steam_ui: checked } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ToggleField, { label: "Show live motion readout", checked: runtime.debug_readout, onChange: (checked) => patch({ runtime: { debug_readout: checked } }) }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy, onClick: () => withBusy(async () => setStatus(await restartOverlay())), children: "Restart overlay process" }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy || !status?.slot.mangoapp_running, onClick: () => DFL.showModal(SP_JSX.jsx(DFL.ConfirmModal, { strTitle: "Take gamescope's overlay slot?", strDescription: "gamescope allows only one external overlay. mangoapp (Steam's performance overlay) normally holds it. " +
                                            "Stopping mangoapp frees the slot for Motion Cues, but the performance overlay will stay off until you restart the Steam session.", onOK: () => withBusy(async () => {
                                            const result = await claimOverlaySlot();
                                            toaster.toast({ title: "Motion Cues", body: result.detail });
                                            await refreshStatus();
                                        }) })), children: "Take overlay slot from mangoapp" }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy || !!status?.slot.mangoapp_running, onClick: () => withBusy(async () => {
                                        const result = await releaseOverlaySlot();
                                        toaster.toast({ title: "Motion Cues", body: result.detail });
                                        await refreshStatus();
                                    }), children: "Restore performance overlay" }) }), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy, onClick: () => withBusy(async () => setDiagnostics(await getDiagnostics())), children: "Run diagnostics" }) }), diagnostics && (SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.Field, { label: "Diagnostics", focusable: false, children: SP_JSX.jsxs("div", { style: { fontFamily: "monospace", fontSize: "0.75em", lineHeight: 1.5 }, children: [diagnostics.sensors.map((entry) => (SP_JSX.jsxs("div", { children: [entry.available ? "✓" : "✗", " ", entry.source, ": ", entry.detail] }, entry.source))), diagnostics.displays.map((entry) => (SP_JSX.jsxs("div", { children: [entry.open ? "✓" : "✗", " ", entry.display, ": ", entry.detail] }, entry.display))), SP_JSX.jsx("div", { children: diagnostics.slot.detail })] }) }) })), SP_JSX.jsx(DFL.PanelSectionRow, { children: SP_JSX.jsx(DFL.ButtonItem, { layout: "below", disabled: busy, onClick: () => DFL.showModal(SP_JSX.jsx(DFL.ConfirmModal, { strTitle: "Reset all settings?", strDescription: "Every option returns to its shipped default. Saved presets are kept.", onOK: () => withBusy(async () => {
                                            const cfg = await resetConfig();
                                            cachedConfig = cfg;
                                            setConfigState(cfg);
                                        }) })), children: "Reset settings to defaults" }) })] }))] })] }));
}
var index = definePlugin(() => {
    // The fallback renderer only subscribes to motion while it can actually be
    // useful, so the event stream costs nothing in the normal case where the
    // gamescope overlay is doing the drawing.
    let subscribed = false;
    const evaluate = async () => {
        try {
            const [cfg, status] = await Promise.all([getConfig(), getStatus()]);
            cachedConfig = cfg;
            const needed = cfg.mode !== "off" &&
                cfg.runtime.fallback_steam_ui &&
                (status.tier === "none" || cfg.runtime.debug_readout);
            fallbackEnabled = needed;
            if (needed && !subscribed) {
                await subscribeMotion();
                subscribed = true;
            }
            else if (!needed && subscribed) {
                await unsubscribeMotion();
                subscribed = false;
            }
        }
        catch (error) {
            // The panel reports backend failures itself; this loop only manages the
            // fallback subscription, so log rather than fight over the UI.
            console.error("[Motion Cues] could not evaluate fallback state:", error);
        }
    };
    void evaluate();
    const interval = window.setInterval(evaluate, 5000);
    routerHook.addGlobalComponent("MotionCuesOverlay", () => (SP_JSX.jsx(FallbackOverlay, { getConfig: () => cachedConfig, getEnabled: () => fallbackEnabled })));
    return {
        name: "Motion Cues",
        titleView: SP_JSX.jsx("div", { className: DFL.staticClasses.Title, children: "Motion Cues" }),
        content: SP_JSX.jsx(Content, {}),
        icon: SP_JSX.jsx(FaCarSide, {}),
        onDismount() {
            window.clearInterval(interval);
            routerHook.removeGlobalComponent("MotionCuesOverlay");
            if (subscribed)
                void unsubscribeMotion();
        },
    };
});

export { index as default };
//# sourceMappingURL=index.js.map
