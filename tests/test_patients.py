VALID_PATIENT = {
    "first_name": "Test",
    "last_name": "Patient",
    "date_of_birth": "01/15/1990",
    "sex": "Female",
    "phone_number": "555-000-1111",
    "address_line_1": "123 Main St",
    "city": "Columbus",
    "state": "OH",
    "zip_code": "43215",
}


def _create(client, cleanup_patients, overrides=None):
    payload = {**VALID_PATIENT, **(overrides or {})}
    resp = client.post("/patients", json=payload)
    if resp.status_code == 201:
        cleanup_patients.append(resp.json()["data"]["phone_number"])
    return resp


def test_create_patient_normalizes_and_persists(client, cleanup_patients):
    resp = _create(client, cleanup_patients, {
        "phone_number": "(555) 000-2222",
        "state": "ohio",
        "email": "test dot patient at example dot com",
    })
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert resp.json()["error"] is None
    assert data["phone_number"] == "5550002222"
    assert data["state"] == "OH"
    assert data["email"] == "test.patient@example.com"
    assert data["patient_id"]


def test_create_patient_invalid_fields_returns_422(client, cleanup_patients):
    resp = _create(client, cleanup_patients, {
        "phone_number": "123",
        "date_of_birth": "01/15/2099",
    })
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert "phone_number" in body["error"]
    assert "date_of_birth" in body["error"]


def test_create_malformed_json_returns_400(client):
    resp = client.post(
        "/patients", content="{not valid json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.json()["data"] is None


def test_get_nonexistent_patient_returns_404(client):
    resp = client.get("/patients/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["data"] is None


def test_list_filters_by_last_name(client, cleanup_patients):
    _create(client, cleanup_patients, {"phone_number": "555-000-3333", "last_name": "Uniquename"})
    resp = client.get("/patients", params={"last_name": "Uniquename"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["last_name"] == "Uniquename"


def test_partial_update_only_changes_given_fields(client, cleanup_patients):
    created = _create(client, cleanup_patients, {"phone_number": "555-000-4444"}).json()["data"]
    resp = client.put(f"/patients/{created['patient_id']}", json={"city": "Cleveland"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["city"] == "Cleveland"
    assert data["last_name"] == created["last_name"]


def test_soft_delete_excludes_from_get_and_list(client, cleanup_patients):
    created = _create(client, cleanup_patients, {"phone_number": "555-000-5555"}).json()["data"]
    patient_id = created["patient_id"]

    del_resp = client.delete(f"/patients/{patient_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["deleted_at"] is not None

    get_resp = client.get(f"/patients/{patient_id}")
    assert get_resp.status_code == 404

    list_resp = client.get("/patients", params={"phone_number": "5550005555"})
    assert list_resp.json()["data"] == []
