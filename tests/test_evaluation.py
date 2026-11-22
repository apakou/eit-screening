"""Évaluation : outils statistiques et confrontation aux scénarios."""

from eit_screening.evaluation.report import anomaly_detection, cohen_kappa, ranks, spearman

def test_ranks_share_ties():
    assert ranks([10, 20, 20, 5]) == [2.0, 3.5, 3.5, 1.0]

def test_spearman():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert spearman([1, 2], [1, 2]) is None
    assert spearman([1, 1, 1], [1, 2, 3]) is None

def test_cohen_kappa():
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert cohen_kappa([], []) is None

def test_anomaly_detection_counts_found_missed_and_false_alerts():
    scenarios = [
        {"application_id": "1", "anomalie": "age_out_of_range"},
        {"application_id": "2", "anomalie": "age_out_of_range"},
        {"application_id": "3", "anomalie": ""},
        {"application_id": "4", "anomalie": "poor_audio"},
    ]
    result = anomaly_detection(scenarios, {"age_out_of_range": {"1", "3"}})
    assert result["age_out_of_range"] == {
        "expected": 2, "covered": True, "found": 1, "missed": ["2"], "false_alerts": 1,
    }
    assert result["poor_audio"] == {"expected": 1, "covered": False}


def test_counterfactual_swaps_only_whole_place_names():
    from eit_screening.evaluation.counterfactual import SWAPS, _pattern, swap_text, visible_places
    from eit_screening.privacy.anonymize import AnonymizedDossier, AnonymizedText, Metadata

    pattern = _pattern(list(SWAPS))
    text = "Studied at University of Ghana, then Ghanaian Tech in [VILLE]; worked in Lagos."
    assert swap_text(text, pattern) == "Studied at University of Nigeria, then Ghanaian Tech in [VILLE]; worked in Accra."
    dossier = AnonymizedDossier(pseudonym="C-1", metadata=Metadata(), texts=[AnonymizedText(section="essay", text=text)])
    assert visible_places(dossier, pattern) == ["Ghana", "Lagos"]
