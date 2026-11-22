import { CandidateView } from "./candidate-view";

export default async function CandidatePage({ params }: PageProps<"/candidats/[pseudonyme]">) {
  const { pseudonyme } = await params;
  return <CandidateView pseudonym={decodeURIComponent(pseudonyme)} />;
}
