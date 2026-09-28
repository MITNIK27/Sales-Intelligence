from app.modules.enrichment.providers.search_contacts import (
    _parse_result,
    build_contact_search_query,
)


def test_build_contact_search_query_quotes_multiword_titles_and_scopes_to_trusted_sites() -> None:
    query = build_contact_search_query("Acme Inc", ["linkedin.com"])
    assert '"Acme Inc"' in query
    assert '"vice president"' in query  # multi-word keyword quoted
    assert "ceo" in query  # single-word keyword left unquoted
    assert "site:linkedin.com" in query


def test_build_contact_search_query_supports_multiple_trusted_domains() -> None:
    query = build_contact_search_query("Acme Inc", ["linkedin.com", "crunchbase.com"])
    assert "site:linkedin.com OR site:crunchbase.com" in query


def test_parse_result_extracts_name_and_title_from_linkedin_style_title() -> None:
    contact = _parse_result(
        {
            "title": "Jane Doe - CEO - Acme Inc | LinkedIn",
            "link": "https://www.linkedin.com/in/janedoe",
            "snippet": "Jane Doe is the CEO of Acme Inc, leading...",
        }
    )
    assert contact is not None
    assert contact.full_name == "Jane Doe"
    assert contact.role_title == "CEO"
    assert contact.email is None


def test_parse_result_falls_back_to_snippet_for_role_title() -> None:
    contact = _parse_result(
        {
            "title": "John Smith | LinkedIn",
            "link": "https://www.linkedin.com/in/johnsmith",
            "snippet": "John Smith is the founder and president of Acme Inc.",
        }
    )
    assert contact is not None
    assert contact.full_name == "John Smith"
    assert contact.role_title is not None


def test_parse_result_rejects_non_person_name_titles() -> None:
    # A company/product page, not a person profile.
    assert (
        _parse_result(
            {
                "title": "Acme Inc - CEO Search Services",
                "link": "https://www.linkedin.com/company/acme",
                "snippet": "We help companies find their next CEO.",
            }
        )
        is None
    )


def test_parse_result_rejects_result_with_no_decision_maker_keyword() -> None:
    # A name-shaped title with no evident role anywhere — too weak a signal to surface.
    assert (
        _parse_result(
            {
                "title": "Jane Doe | LinkedIn",
                "link": "https://www.linkedin.com/in/janedoe",
                "snippet": "Jane Doe's profile on LinkedIn. Jane Doe has 3 jobs listed.",
            }
        )
        is None
    )


def test_parse_result_handles_missing_title() -> None:
    assert _parse_result({"link": "https://www.linkedin.com/in/x", "snippet": "..."}) is None
