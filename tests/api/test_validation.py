"""J10: region text is checked before the handler runs."""

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("ok", ["example_region", "Example Region", "St. Paul (north)", "a"])
def test_allowed_text_passes_validation(client, ok):
    assert client.get("/trend", params={"region": ok}).status_code in (200, 404)


@pytest.mark.parametrize("bad", ["x" * 101, "<b>", "a;DROP", "émoji🙂", ""])
def test_bad_text_is_422(client, bad):
    assert client.get("/trend", params={"region": bad}).status_code == 422
