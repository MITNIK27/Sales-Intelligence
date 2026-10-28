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


# --- strict filtering: real profile, company association, confidence ---

from app.modules.enrichment.providers.search_contacts import (  # noqa: E402
    normalize_linkedin_profile_url,
)


def test_linkedin_url_normalization_accepts_only_person_profiles() -> None:
    assert (
        normalize_linkedin_profile_url("https://de.linkedin.com/in/Jane-Doe-123/?trk=x")
        == "https://www.linkedin.com/in/jane-doe-123"
    )
    assert normalize_linkedin_profile_url("https://www.linkedin.com/company/acme") is None
    assert normalize_linkedin_profile_url("https://www.linkedin.com/jobs/view/123") is None
    assert normalize_linkedin_profile_url("https://example.com/in/jane") is None
    assert normalize_linkedin_profile_url(None) is None


def test_company_page_links_are_rejected_even_with_a_person_like_title() -> None:
    assert (
        _parse_result(
            {
                "title": "Jane Doe - CEO - Acme Inc | LinkedIn",
                "link": "https://www.linkedin.com/company/acme",
                "snippet": "CEO at Acme Inc",
            },
            "Acme Inc",
            "acme.com",
        )
        is None
    )


def test_company_in_the_headline_gives_high_confidence_and_keeps_the_profile_url() -> None:
    contact = _parse_result(
        {
            "title": "Jane Doe - CEO - Acme Inc | LinkedIn",
            "link": "https://www.linkedin.com/in/janedoe",
            "snippet": "Jane Doe is the CEO of Acme Inc.",
        },
        "Acme Inc",
        "acme.com",
    )
    assert contact is not None
    assert contact.linkedin_url == "https://www.linkedin.com/in/janedoe"
    assert contact.confidence is not None and contact.confidence >= 0.9
    assert contact.source == "serper:linkedin"


def test_a_person_without_any_company_evidence_is_rejected() -> None:
    # "Elaine Kerr - Cto" style: a role but nothing tying her to this company.
    assert (
        _parse_result(
            {
                "title": "Elaine Kerr - Cto | LinkedIn",
                "link": "https://www.linkedin.com/in/elainekerr",
                "snippet": "Experienced CTO. Based in Dublin.",
            },
            "DPD Group",
            "dpd.com",
        )
        is None
    )


def test_surname_equal_to_the_company_name_is_not_a_company_match() -> None:
    # Searching for the company Hermes must not accept a person named Hermes at another company.
    assert (
        _parse_result(
            {
                "title": "Jackie Hermes - CEO - Accelity | LinkedIn",
                "link": "https://www.linkedin.com/in/jackiehermes",
                "snippet": "Jackie Hermes is CEO at Accelity.",
            },
            "Hermes",
            "hermes.com",
        )
        is None
    )


def test_company_only_in_the_snippet_scores_lower_than_in_the_headline() -> None:
    headline = _parse_result(
        {
            "title": "Jane Doe - Director - Acme | LinkedIn",
            "link": "https://www.linkedin.com/in/jane",
            "snippet": "Jane Doe leads logistics.",
        },
        "Acme Inc",
        "acme.com",
    )
    snippet_only = _parse_result(
        {
            "title": "Jane Doe - Director | LinkedIn",
            "link": "https://www.linkedin.com/in/jane",
            "snippet": "Jane Doe is a director at Acme leading logistics.",
        },
        "Acme Inc",
        "acme.com",
    )
    assert headline is not None and snippet_only is not None
    assert snippet_only.confidence < headline.confidence


def test_domain_label_counts_as_the_company_when_the_name_differs() -> None:
    contact = _parse_result(
        {
            "title": "Marc Leroy - Head of IT - DPD | LinkedIn",
            "link": "https://fr.linkedin.com/in/marcleroy",
            "snippet": "",
        },
        "DPD Group",
        "dpd.com",
    )
    assert contact is not None and contact.linkedin_url.endswith("/in/marcleroy")
