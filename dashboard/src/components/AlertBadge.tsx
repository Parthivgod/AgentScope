import { memo } from 'react';
import './AlertBadge.css';

interface AlertBadgeProps {
  rule: string;
}

/**
 * AlertBadge — Week 5/6 Component
 * 
 * Displays a distinct visual warning on a node that has been flagged
 * by the Anomaly Worker (Track B).
 */
function AlertBadge({ rule }: AlertBadgeProps) {
  return (
    <div className="alert-badge">
      <span className="alert-badge__icon">⚠️</span>
      <span className="alert-badge__text">{rule}</span>
    </div>
  );
}

export default memo(AlertBadge);
