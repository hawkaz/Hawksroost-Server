from .conftest import login


def book(client, start, end, title="Trip"):
    return client.post("/api/calendar", json={"title": title, "start_date": start, "end_date": end})


def test_overlaps_flagged_not_blocked(client):
    login(client, "member")
    a = book(client, "2026-07-10", "2026-07-14").json()
    b = book(client, "2026-07-13", "2026-07-16")
    assert b.status_code == 201
    assert b.json()["overlaps"] == [a["id"]]
    # Leaving the day the next person arrives is not an overlap.
    c = book(client, "2026-07-16", "2026-07-18").json()
    assert c["overlaps"] == []
    listed = client.get("/api/calendar", params={"start": "2026-07-01", "end": "2026-07-31"}).json()
    assert {x["id"]: x["overlaps"] for x in listed}[a["id"]] == [b.json()["id"]]


def test_stay_dates_validated(client):
    login(client, "member")
    r = book(client, "2026-07-10", "2026-07-10")
    assert r.status_code == 422
    assert "after" in r.json()["detail"]


def test_ical_feed(client):
    login(client, "member")
    book(client, "2027-07-10", "2027-07-14", "Lake weekend")
    url = client.get("/api/calendar/feed").json()["url"]
    client.post("/api/auth/logout")
    r = client.get(url.replace("https://testserver", ""))
    assert r.status_code == 200 and b"Lake weekend" in r.content


def test_shopping_history(client):
    login(client, "member")
    item = client.post("/api/lists/shopping", json={"text": "Propane", "qty": "2", "store": "Flagstaff run"}).json()
    assert item["added_by"]["name"] == "Member"
    got = client.patch(f"/api/lists/shopping/{item['id']}", json={"acquired": True}).json()
    assert got["acquired_by"]["name"] == "Member" and got["acquired_at"]
    lists = client.get("/api/lists/shopping").json()
    assert lists["open"] == [] and lists["acquired"][0]["id"] == item["id"]
    assert lists["stores"] == ["Flagstaff run"]


def test_tasks_and_reset(client):
    login(client, "member")
    lst = client.post("/api/lists/tasks", json={"name": "Before we leave"}).json()
    t = client.post(f"/api/lists/tasks/{lst['id']}/items", json={"title": "Shut off water", "priority": 2}).json()
    done = client.patch(f"/api/lists/tasks/items/{t['id']}", json={"done": True}).json()
    assert done["done_by"]["name"] == "Member"
    client.post(f"/api/lists/tasks/{lst['id']}/reset")
    lists = {l["id"]: l for l in client.get("/api/lists/tasks").json()}
    assert lists[lst["id"]]["tasks"][0]["done_at"] is None


def test_today(client):
    login(client, "viewer")
    r = client.get("/api/today")
    assert r.status_code == 200
    assert r.json()["task_count"] == 0


def test_visit_with_several_people(client):
    from .conftest import login, make_user
    dana = make_user("member", "dana@example.com")
    login(client, "member")
    me = client.get("/api/auth/me").json()["id"]
    people = client.get("/api/calendar/people").json()
    assert {p["id"] for p in people} == {me, dana}
    r = client.post("/api/calendar", json={"title": "Fourth of July", "start_date": "2099-07-02", "end_date": "2099-07-06",
                                           "people_ids": [me, dana, 9999], "others": "the Smiths "})
    assert r.status_code == 201, r.text
    b = r.json()
    assert sorted(p["id"] for p in b["people"]) == sorted([me, dana]) and b["others"] == "the Smiths"
    # Editing replaces the list.
    r = client.put(f"/api/calendar/{b['id']}", json={"title": "Fourth of July", "start_date": "2099-07-02",
                                                     "end_date": "2099-07-06", "people_ids": [dana]})
    assert [p["id"] for p in r.json()["people"]] == [dana] and r.json()["others"] is None
    feed = client.get(client.get("/api/calendar/feed").json()["url"].split("testserver")[1]).text
    assert "Member: Fourth of July" in feed   # who's coming, in calendar apps too
