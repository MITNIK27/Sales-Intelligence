from app.modules.enrichment.providers.base import looks_like_person_name


def test_accepts_a_plausible_two_word_name() -> None:
    assert looks_like_person_name("Jane Doe") is True


def test_accepts_a_plausible_four_word_name() -> None:
    assert looks_like_person_name("Jane Anne Van Doe") is True


def test_rejects_single_word() -> None:
    assert looks_like_person_name("Leadership") is False


def test_rejects_more_than_four_words() -> None:
    assert looks_like_person_name("Not A Person Heading With Way Too Many Words") is False


def test_rejects_name_containing_a_digit() -> None:
    assert looks_like_person_name("District 9 Manager") is False


def test_rejects_company_suffix_word() -> None:
    assert looks_like_person_name("Acme Solutions") is False
    assert looks_like_person_name("Acme Inc") is False


def test_rejects_lowercase_word() -> None:
    assert looks_like_person_name("jane doe") is False
