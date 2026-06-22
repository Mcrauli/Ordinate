import json, math, numpy as np

m = json.load(open("data/output/apt_v29/model.json"))
walls = m["walls"]
w105 = next(w for w in walls if "105" in w["id"])
w000 = next(w for w in walls if "000" in w["id"])

p0_105 = np.array(w105["axis"][0])
p1_105 = np.array(w105["axis"][1])
p0_000 = np.array(w000["axis"][0])
p1_000 = np.array(w000["axis"][1])

len_105 = float(np.linalg.norm(p1_105 - p0_105))
len_000 = float(np.linalg.norm(p1_000 - p0_000))
ua_000 = (p1_000 - p0_000) / len_000
ua_105 = (p1_105 - p0_105) / len_105

print(f"w105 p1={p1_105}")
print(f"w000 p0={p0_000}, len={len_000:.1f}")
print(f"ua_000={np.round(ua_000,4)}")

t = float(np.dot(p1_105 - p0_000, ua_000))
proj = p0_000 + max(0.0, t) * ua_000
dist = float(np.linalg.norm(p1_105 - proj))
print(f"\np1_105 onto wall_000: t={t:.3f}mm, dist={dist:.1f}mm")
print(f"proj={np.round(proj,1)}")
print(f"would snap: t>=-50 and t<=len_000 and dist<=300: {t >= -50.0 and t <= len_000 and dist <= 300}")

t2 = float(np.dot(p0_000 - p0_105, ua_105))
proj2 = p0_105 + t2 * ua_105
dist2 = float(np.linalg.norm(p0_000 - proj2))
print(f"\np0_000 onto wall_105: t={t2:.3f}mm (len={len_105:.1f}mm), dist={dist2:.1f}mm")
print(f"gap final: {math.dist(p1_105, p0_000):.1f}mm")
