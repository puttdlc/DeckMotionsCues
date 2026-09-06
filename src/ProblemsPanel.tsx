import { ButtonItem, Field, PanelSection, PanelSectionRow } from "@decky/ui";
import { FC, Fragment } from "react";

import { Problem } from "./api";

/**
 * The problem log.
 *
 * Renders nothing at all when there is nothing wrong - no empty state, no
 * "all good" banner - so the panel stays quiet unless it has something worth
 * saying. Each entry can be dismissed individually, and a dismissed problem
 * comes back if the same failure happens again, because hiding a recurring
 * fault permanently would be its own kind of silent failure.
 */

interface Props {
  problems: Problem[];
  busy: boolean;
  onDismiss: (key: string) => void;
  onDismissAll: () => void;
}

const SEVERITY_COLOUR: Record<string, string> = {
  error: "#ff6b6b",
  warning: "#ffc046",
};

function relativeTime(seconds: number): string {
  const delta = Date.now() / 1000 - seconds;
  if (!Number.isFinite(delta) || delta < 0) return "just now";
  if (delta < 45) return "just now";
  if (delta < 90) return "a minute ago";
  if (delta < 3600) return `${Math.round(delta / 60)} minutes ago`;
  if (delta < 7200) return "an hour ago";
  if (delta < 86400) return `${Math.round(delta / 3600)} hours ago`;
  return `${Math.round(delta / 86400)} days ago`;
}

export const ProblemsPanel: FC<Props> = ({ problems, busy, onDismiss, onDismissAll }) => {
  if (problems.length === 0) return null;

  const errors = problems.filter((problem) => problem.severity === "error").length;
  const title =
    errors > 0
      ? `Problems (${problems.length})`
      : `Warnings (${problems.length})`;

  return (
    <PanelSection title={title}>
      {problems.map((problem) => {
        const colour = SEVERITY_COLOUR[problem.severity] ?? SEVERITY_COLOUR.error;
        return (
          <Fragment key={problem.key}>
            <PanelSectionRow>
              <Field
                focusable={false}
                bottomSeparator="none"
                label={
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span
                      style={{
                        display: "inline-block",
                        width: "8px",
                        height: "8px",
                        borderRadius: "50%",
                        backgroundColor: colour,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ color: colour }}>{problem.title}</span>
                    {problem.count > 1 && (
                      <span style={{ opacity: 0.7, fontSize: "0.85em" }}>
                        ×{problem.count}
                      </span>
                    )}
                  </div>
                }
              >
                <div style={{ fontSize: "0.85em", opacity: 0.85, textAlign: "left" }}>
                  {relativeTime(problem.last_seen)}
                </div>
              </Field>
            </PanelSectionRow>

            <PanelSectionRow>
              <Field focusable={false} bottomSeparator="none">
                <div
                  style={{
                    fontSize: "0.85em",
                    lineHeight: 1.45,
                    textAlign: "left",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                >
                  <div>{problem.detail}</div>
                  {problem.hint && (
                    <div style={{ marginTop: "4px", opacity: 0.75 }}>
                      → {problem.hint}
                    </div>
                  )}
                  <div style={{ marginTop: "4px", opacity: 0.5, fontSize: "0.9em" }}>
                    source: {problem.source}
                  </div>
                </div>
              </Field>
            </PanelSectionRow>

            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={() => onDismiss(problem.key)}
              >
                Dismiss
              </ButtonItem>
            </PanelSectionRow>
          </Fragment>
        );
      })}

      {problems.length > 1 && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={onDismissAll}>
            Dismiss all {problems.length}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
};
