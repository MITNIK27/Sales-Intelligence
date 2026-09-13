from app.modules.ingestion.csv_parser import parse_csv


def test_parses_known_headers_with_aliases() -> None:
    raw = "Company,Website,Email\nAcme Inc,https://acme.com,jane@acme.com\n"
    parsed = parse_csv(raw)
    assert parsed.header_map["company_name"] == "Company"
    assert parsed.header_map["domain"] == "Website"
    assert parsed.header_map["contact_email"] == "Email"
    assert len(parsed.rows) == 1
    assert parsed.rows[0].fields["company_name"] == "Acme Inc"
    assert parsed.rows[0].error is None


def test_row_without_company_name_or_domain_is_flagged() -> None:
    raw = "contact_email\njane@acme.com\n"
    parsed = parse_csv(raw)
    assert parsed.rows[0].error == "row has neither a company name nor a domain"


def test_row_numbers_are_one_indexed_excluding_header() -> None:
    raw = "company_name\nAcme\nGlobex\n"
    parsed = parse_csv(raw)
    assert [r.row_number for r in parsed.rows] == [1, 2]
