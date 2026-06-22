import json, math

m = json.load(open("data/output/apt_v29/model.json"))
walls = {w["id"]: w for w in m["walls"]}

def gap(id1, ep1, id2, ep2):
    p1 = walls[id1]["axis"][ep1]
    p2 = walls[id2]["axis"][ep2]
    return math.dist(p1, p2)

checks = [
    ("wall_138", 0, "wall_071", 0),
    ("wall_138", 1, "wall_000", 1),
    ("wall_071", 1, "wall_077", 1),
    ("wall_009", 1, "wall_077", 0),
    ("wall_105", 1, "wall_000", 0),
]
for id1, ep1, id2, ep2 in checks:
    g = gap(id1, ep1, id2, ep2)
    status = "OK" if g < 1.0 else f"GAP {g:.1f}mm"
    print(f"{id1}[{ep1}] ~ {id2}[{ep2}]: {status}")
