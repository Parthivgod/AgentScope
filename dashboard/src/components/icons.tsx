/**
 * icons.tsx — Inline SVG icon set for the AgentScope dashboard.
 *
 * Design constraints (FR-6 / Week 9 a11y pass, kept in the UI redesign):
 *   - Every node TYPE icon is distinguishable by SHAPE, not just color
 *     (colorblind users must never need hue to tell a type or status).
 *   - Every STATUS icon is shape-distinct: spinner = running,
 *     check = complete, X = error, warning triangle = anomalous.
 *   - All icons inherit `currentColor` so status coloring comes from CSS.
 *
 * No icon library dependency: these are small hand-rolled paths
 * (stroke style, 24×24 viewBox, lucide-like geometry).
 */

import type { ReactNode, SVGProps } from 'react';
import './icons.css';

export type IconSize = number;

/** Props every exported icon accepts. */
export interface IconComponentProps extends Omit<SVGProps<SVGSVGElement>, 'children'> {
  size?: IconSize;
}

interface IconProps extends IconComponentProps {
  children: ReactNode;
}

function Svg({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/* ═══ Node TYPE icons — shape encodes type; tint is neutral ═════════ */

/** LLM Call — chat bubble with three dots */
export function IconLLM(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <line x1="8" y1="9" x2="8" y2="9.01" />
      <line x1="12" y1="9" x2="12" y2="9.01" />
      <line x1="16" y1="9" x2="16" y2="9.01" />
    </Svg>
  );
}

/** Tool Call — wrench */
export function IconTool(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </Svg>
  );
}

/** Delegation — branching share nodes */
export function IconDelegation(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </Svg>
  );
}

/** State Update — database cylinder */
export function IconState(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
      <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
    </Svg>
  );
}

/** Unknown span type — layered flow circles */
export function IconFlow(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="3" />
      <line x1="12" y1="4" x2="12" y2="9" />
      <line x1="5" y1="20" x2="10" y2="14" />
      <line x1="19" y1="20" x2="14" y2="14" />
      <circle cx="12" cy="3" r="1" />
      <circle cx="4" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
    </Svg>
  );
}

/* ═══ STATUS icons — shape encodes status ═══════════════════════════ */

/** Running — spinning arc (pair with .icon--spin) */
export function IconSpinner(props: IconComponentProps) {
  return (
    <Svg {...props} className={`icon--spin ${props.className ?? ''}`}>
      <path d="M21 12a9 9 0 1 1-6.22-8.56" />
    </Svg>
  );
}

/** Complete — check mark */
export function IconCheck(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M20 6 9 17l-5-5" />
    </Svg>
  );
}

/** Error — X mark */
export function IconX(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </Svg>
  );
}

/** Anomaly — warning triangle with exclamation */
export function IconWarning(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </Svg>
  );
}

/* ═══ Stat / shell icons ════════════════════════════════════════════ */

/** Nodes stat — hierarchical tree of circles */
export function IconGraph(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="19" r="2.5" />
      <circle cx="19" cy="19" r="2.5" />
      <path d="M12 7.5 6.2 16.8" />
      <path d="M12 7.5l5.8 9.3" />
    </Svg>
  );
}

export function IconCheckCircle(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </Svg>
  );
}

export function IconXCircle(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </Svg>
  );
}

export function IconActivity(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </Svg>
  );
}

export function IconLock(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </Svg>
  );
}

export function IconEye(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  );
}

export function IconClock(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Svg>
  );
}

export function IconArrowRight(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </Svg>
  );
}

export function IconChevronRight(props: IconComponentProps) {
  return (
    <Svg {...props}>
      <path d="m9 18 6-6-6-6" />
    </Svg>
  );
}
