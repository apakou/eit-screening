import { Badge } from "@/components/ui/badge";
import type { Status, VerdictLabel } from "@/lib/api";

const VERDICT_STYLE: Record<VerdictLabel, string> = {
  "Interview Invitation": "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  Waitlist: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  "Interview Reject": "bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200",
  "Request Final Review": "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200",
};

export function VerdictBadge({ verdict }: { verdict: VerdictLabel }) {
  return <Badge className={VERDICT_STYLE[verdict]}>{verdict}</Badge>;
}

export function StatusBadge({ status }: { status: Status }) {
  const variant = status === "à traiter" ? "outline" : status === "validé" ? "secondary" : "default";
  return <Badge variant={variant}>{status}</Badge>;
}
