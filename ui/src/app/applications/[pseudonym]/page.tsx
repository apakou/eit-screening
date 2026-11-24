import { Suspense } from "react";

import { CandidateView } from "./candidate-view";

// Next.js 16 : lire `params` hors d'une frontière <Suspense> bloque le pré-rendu de la page.
export default function CandidatePage({ params }: PageProps<"/applications/[pseudonym]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Chargement…</p>}>
      <Candidate params={params} />
    </Suspense>
  );
}

async function Candidate({ params }: { params: PageProps<"/applications/[pseudonym]">["params"] }) {
  const { pseudonym } = await params;
  return <CandidateView pseudonym={decodeURIComponent(pseudonym)} />;
}
