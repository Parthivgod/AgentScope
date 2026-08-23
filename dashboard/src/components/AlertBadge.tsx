import { memo } from 'react';
import { IconWarning } from './icons';
import { ruleLabel } from '../anomalyEvidence';
import './AlertBadge.css';

interface AlertBadgeProps {
  rule: string;
}

/**
 * AlertBadge — anomaly flag chip pinned to a flagged node's corner.
 *
 * Shows the rule's display name (e.g. "Failure Loop") instead of the raw
 * wire key where a friendly label exists (anomalyEvidence.RULE_META).
 */
function AlertBadge({ rule }: AlertBadgeProps) {
  return (
    <div className="alert-badge">
      <span className="alert-badge__icon"><IconWarning size={11} /></span>
      <span className="alert-badge__text">{ruleLabel(rule)}</span>
    </div>
  );
}

export default memo(AlertBadge);
