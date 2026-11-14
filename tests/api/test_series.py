"""J7: /series gives the monthly values for a region."""

import pytest

pytestmark = pytest.mark.unit


def test_default_region(client):
    body = client.get("/series").json()
    assert body["region_id"] == "example_region"
    assert body["series"][0] == {"time": "2003-01", "value": body["series"][0]["value"]}


def test_by_label_any_case(client):
    assert client.get("/series", params={"region": "example REGION"}).status_code == 200


@pytest.mark.parametrize("bad", ["<script>", "x" * 101, ""])
def test_bad_input_is_422(client, bad):
    assert client.get("/series", params={"region": bad}).status_code == 422
