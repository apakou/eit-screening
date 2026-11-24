import type { Status, VerdictLabel } from "@/lib/api";

// Une couleur par décision, la même partout (badges, cartes, barres).
export const DECISION_STYLE: Record<VerdictLabel, { bg: string; ink: string; bar: string }> = {
  "Interview Invitation": { bg: "bg-invite", ink: "text-invite-ink", bar: "bg-invite-ink" },
  Waitlist: { bg: "bg-waitlist", ink: "text-waitlist-ink", bar: "bg-waitlist-ink" },
  "Interview Reject": { bg: "bg-reject", ink: "text-reject-ink", bar: "bg-reject-ink" },
};

const STATUS_LABELS: Record<Status, string> = { pending: "To review", validated: "Validated", modified: "Modified" };

const pill = "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap";

export function VerdictBadge({ verdict }: { verdict: VerdictLabel | null }) {
  if (verdict === null) {
    return <span className={`${pill} border border-dashed border-input text-muted-foreground`}>No proposal</span>;
  }
  const style = DECISION_STYLE[verdict];
  return <span className={`${pill} ${style.bg} ${style.ink}`}>{verdict}</span>;
}

export function ReviewBadge({ review }: { review: boolean | null }) {
  if (!review) return null;
  return <span className={`${pill} bg-review text-review-ink`}>Further review</span>;
}

export function StatusBadge({ status }: { status: Status }) {
  const style =
    status === "pending"
      ? "border border-input text-muted-foreground"
      : status === "validated"
        ? "bg-ink text-white"
        : "bg-white text-ink ring-1 ring-ink";
  return <span className={`${pill} ${style}`}>{STATUS_LABELS[status]}</span>;
}

export function ScoreBar({
  value,
  max,
  verdict,
  label,
}: {
  value: number | null;
  max: number;
  verdict?: VerdictLabel | null;
  label: string;
}) {
  const share = value === null ? 0 : Math.max(0, Math.min(1, value / max));
  const bar = verdict ? DECISION_STYLE[verdict].bar : "bg-ink";
  return (
    <div className="flex items-center gap-2">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value ?? undefined}
        className="h-1.5 w-full min-w-16 overflow-hidden rounded-full bg-[#ece5d8]"
      >
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${share * 100}%` }} />
      </div>
      <span className="w-12 shrink-0 text-right text-sm tabular-nums">
        {value ?? "–"}
        <span className="text-muted-foreground">/{max}</span>
      </span>
    </div>
  );
}
