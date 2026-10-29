import type { CSSProperties } from 'react'

/** Shown while a plan is computed: the message, a moving bar and placeholders in the shape of the
 * results. Screen readers get the message from the page's live region instead. */
export function PlanLoading({ message }: { message: string }) {
  return (
    <div className="plan-loading" aria-hidden="true">
      <p className="status">
        {/* A new key per step, so each message fades in. */}
        <span key={message} className="status-text">
          {message}
        </span>
      </p>
      <div className="progress">
        <span />
      </div>
      <div className="skeleton skeleton-recommendation" />
      {[0, 1, 2].map((index) => (
        <div key={index} className="skeleton-card" style={{ '--order': index } as CSSProperties}>
          <div className="skeleton skeleton-title" />
          <div className="skeleton-stats">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
          <div className="skeleton skeleton-bar" />
        </div>
      ))}
    </div>
  )
}
