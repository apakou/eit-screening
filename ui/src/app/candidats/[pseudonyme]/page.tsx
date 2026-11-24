import { Suspense } from "react";

import { CandidateView } from "./candidate-view";

// Next.js 16 : lire `params` hors d'une frontière <Suspense> bloque le pré-rendu de la page.
export default function CandidatePage({ params }: PageProps<"/candidats/[pseudonyme]">) {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Chargement…</p>}>
      <Candidate params={params} />
    </Suspense>
  );
}

async function Candidate({ params }: { params: PageProps<"/candidats/[pseudonyme]">["params"] }) {
  const { pseudonyme } = await params;
  return <CandidateView pseudonym={decodeURIComponent(pseudonyme)} />;
}
