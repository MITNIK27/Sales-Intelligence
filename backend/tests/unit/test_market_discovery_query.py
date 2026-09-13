from app.modules.ingestion.market_discovery import _build_search_query


def test_build_search_query_includes_industry_and_location() -> None:
    parsed_fields = {
        "industry_keywords": {"value": ["SaaS", "fintech"], "confidence": "confident"},
        "location": {"value": "Bangalore", "confidence": "confident"},
        "employee_size_range": {"value": "50-200", "confidence": "confident"},
    }
    query = _build_search_query(parsed_fields)
    assert query == "SaaS fintech companies in Bangalore"


def test_build_search_query_handles_missing_location() -> None:
    parsed_fields = {
        "industry_keywords": {"value": ["SaaS"], "confidence": "confident"},
        "location": {"value": None, "confidence": "could_not_determine"},
        "employee_size_range": {"value": None, "confidence": "could_not_determine"},
    }
    query = _build_search_query(parsed_fields)
    assert query == "SaaS companies"


def test_build_search_query_handles_empty_fields() -> None:
    assert _build_search_query({}) == "companies"
