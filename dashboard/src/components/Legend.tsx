/**
 * Legend.tsx — STATUS + NODE TYPE legend overlaying the graph canvas.
 *
 * Accessibility move kept from the design reference: every status and
 * node type is shown with its actual icon SHAPE alongside its color, so
 * the graph is readable without color vision and without clicking
 * anything (FR-6 "explain at a glance").
 *
 * Collapsible to keep canvas space; purely visual — no data dependency,
 * so it renders identically in live and historical modes (invariant #5).
 */

import { useState } from 'react';
import {
  IconSpinner,
  IconCheck,
  IconX,
  IconWarning,
  IconLLM,
  IconTool,
  IconDelegation,
  IconState,
  IconChevronRight,
} from './icons';
import './Legend.css';

const STATUS_ITEMS = [
  { label: 'Running', icon: IconSpinner, className: 'legend__swatch--running' },
  { label: 'Completed', icon: IconCheck, className: 'legend__swatch--complete' },
  { label: 'Error', icon: IconX, className: 'legend__swatch--error' },
  { label: 'Anomaly', icon: IconWarning, className: 'legend__swatch--anomaly' },
];

const TYPE_ITEMS = [
  { label: 'LLM Call', icon: IconLLM },
  { label: 'Tool Call', icon: IconTool },
  { label: 'Delegation', icon: IconDelegation },
  { label: 'State Update', icon: IconState },
];

export default function Legend() {
  const [open, setOpen] = useState(true);

  return (
    <div className={`legend ${open ? 'legend--open' : ''}`}>
      <button
        className="legend__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? 'Collapse legend' : 'Expand legend'}
        title={open ? 'Collapse legend' : 'Expand legend'}
      >
        <IconChevronRight size={14} className={`legend__chevron ${open ? 'legend__chevron--open' : ''}`} />
      </button>

      {open && (
        <div className="legend__body">
          <h2 className="legend__title">Status</h2>
          <ul className="legend__list">
            {STATUS_ITEMS.map(({ label, icon: Icon, className }) => (
              <li key={label} className="legend__item">
                <span className={`legend__swatch ${className}`}>
                  <Icon size={12} />
                </span>
                <span className="legend__label">{label}</span>
              </li>
            ))}
          </ul>

          <h2 className="legend__title">Node type</h2>
          <ul className="legend__list">
            {TYPE_ITEMS.map(({ label, icon: Icon }) => (
              <li key={label} className="legend__item">
                <span className="legend__swatch legend__swatch--type">
                  <Icon size={12} />
                </span>
                <span className="legend__label">{label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
