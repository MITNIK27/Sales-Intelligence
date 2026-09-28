from app.modules.discovery_agent.heuristics import classify_candidate_name


def test_rejects_top_n_listicle_title() -> None:
    verdict, reason = classify_candidate_name("Top 10 Courier Companies")
    assert verdict == "reject"
    assert reason is not None


def test_rejects_best_n_listicle_title() -> None:
    verdict, _ = classify_candidate_name("Best 5 Logistics Providers in Europe")
    assert verdict == "reject"


def test_rejects_list_of_title() -> None:
    verdict, _ = classify_candidate_name("List of Postal Providers in Europe")
    assert verdict == "reject"


def test_flags_pipe_separated_title_case_page_title() -> None:
    verdict, reason = classify_candidate_name("Best Parcel Firms | Global News Today")
    assert verdict == "flag"
    assert reason is not None


def test_flags_year_alongside_listicle_noun() -> None:
    verdict, _ = classify_candidate_name("Best Logistics Companies in 2026")
    assert verdict == "flag"


def test_no_concern_for_a_plausible_company_name() -> None:
    assert classify_candidate_name("Acme Logistics") == (None, None)
    assert classify_candidate_name("Globex Corp") == (None, None)
