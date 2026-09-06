import { addEventListener, removeEventListener } from "@decky/api";
import { FC, useEffect, useState } from "react";

import { Config, MotionState } from "./api";

/**
 * The fallback rendering tier.
 *
 * This draws the dots as DOM elements inside Steam's own UI layer. It is
 * genuinely useful - it covers the library, settings, the Quick Access Menu
 * and Big Picture generally - but Steam's UI is not composited over a running
 * game, so this tier cannot cover gameplay. The gamescope overlay window in
 * the helper process is what does that; this exists for when that window
 * cannot be created, and as a live preview while tuning settings.
 */

interface Props {
  getConfig: () => Config | null;
  getEnabled: () => boolean;
}

function edgePositions(config: Config, width: number, height: number) {
  const { count, edge_padding, edges, margin_fraction, layout } = config.appearance;
  const spread: number[] = [];

  if (layout === "corners") {
    const half = Math.floor(count / 2);
    const extra = count - half * 2;
    const cluster = (1 - 2 * margin_fraction) * 0.28;
    for (let group = 0; group < 2; group += 1) {
      const n = half + (group === 0 ? extra : 0);
      if (n <= 0) continue;
      const base = group === 0 ? margin_fraction : 1 - margin_fraction - cluster;
      const step = n > 1 ? cluster / (n - 1) : 0;
      for (let i = 0; i < n; i += 1) spread.push(base + step * i);
    }
  } else {
    const span = 1 - 2 * margin_fraction;
    for (let i = 0; i < count; i += 1) {
      const t = (i + 0.5) / count;
      const eased = layout === "clustered" ? t * t * (3 - 2 * t) : t;
      spread.push(margin_fraction + span * eased);
    }
  }

  const points: { x: number; y: number }[] = [];
  for (const edge of edges) {
    for (const t of spread) {
      if (edge === "left") points.push({ x: edge_padding, y: t * height });
      else if (edge === "right") points.push({ x: width - edge_padding, y: t * height });
      else if (edge === "top") points.push({ x: t * width, y: edge_padding });
      else points.push({ x: t * width, y: height - edge_padding });
    }
  }
  return points;
}

function borderRadiusFor(shape: string): string {
  if (shape === "circle" || shape === "ring") return "50%";
  return "0";
}

export const FallbackOverlay: FC<Props> = ({ getConfig, getEnabled }) => {
  const [motion, setMotion] = useState<MotionState | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const listener = addEventListener<[MotionState]>("motion", (state) => {
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
  if (!config || !getEnabled() || !motion || motion.alpha <= 0.004) return null;
  void tick;

  const width = window.innerWidth || 1280;
  const height = window.innerHeight || 800;
  const points = edgePositions(config, width, height);
  const { size, color, opacity, shape, outline, outline_color } = config.appearance;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 7000,
        opacity: motion.alpha,
      }}
    >
      {points.map((point, index) => (
        <div
          key={index}
          style={{
            position: "absolute",
            left: `${point.x + motion.dx - size / 2}px`,
            top: `${point.y + motion.dy - size / 2}px`,
            width: `${size}px`,
            height: `${size}px`,
            borderRadius: borderRadiusFor(shape),
            backgroundColor: shape === "ring" ? "transparent" : color,
            border:
              shape === "ring"
                ? `${Math.max(1, size * 0.22)}px solid ${color}`
                : outline > 0
                  ? `${outline}px solid ${outline_color}`
                  : undefined,
            opacity,
            transform: shape === "diamond" ? "rotate(45deg)" : undefined,
            willChange: "left, top",
          }}
        />
      ))}
    </div>
  );
};
