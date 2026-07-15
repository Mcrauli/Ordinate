"""Rohbau3D-lataaja suoraan Dataversesta (DOI 10.60776/ZWJFI4).
Ei aja ulkopuolista koodia — pelkkä Dataverse-access-API + requests.

Kaytto:
  python rohbau_download.py --list                      # listaa tiedostot+koot
  python rohbau_download.py --sites 0,3,6 --features coord,intensity,color,class --out DIR
"""
import argparse, sys, json, re
from pathlib import Path
import requests

HOST = "https://open-data.unibw.de"
DOI = "doi:10.60776/ZWJFI4"


def list_files():
    url = f"{HOST}/api/datasets/:persistentId/?persistentId={DOI}"
    r = requests.get(url, timeout=60); r.raise_for_status()
    files = r.json()["data"]["latestVersion"]["files"]
    out = []
    for f in files:
        df = f["dataFile"]
        out.append({"name": df["filename"], "id": df["id"],
                    "size": int(df.get("filesize", 0))})
    return out


def parse(name):
    m = re.match(r"site_(\d+)\.(\w+)\.part\d+\.tar\.zst", name)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--sites", default="")
    ap.add_argument("--features", default="coord,intensity,color,class")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    files = list_files()
    if a.list:
        by_site = {}
        for f in files:
            s, feat = parse(f["name"])
            if s is None: continue
            by_site.setdefault(s, {}).setdefault(feat, 0)
            by_site[s][feat] += f["size"]
        print(f"{'site':>4} | " + " ".join(f"{k:>10}" for k in ("coord","intensity","color","normal","class")) + " |  total GB")
        for s in sorted(by_site):
            d = by_site[s]
            tot = sum(d.values())
            print(f"{s:>4} | " + " ".join(f"{d.get(k,0)/1e9:>9.2f}G" for k in ("coord","intensity","color","normal","class")) + f" | {tot/1e9:>7.2f}")
        sel_feat = ("coord","intensity","color","class")
        gtot = sum(f["size"] for f in files if parse(f["name"])[1] in sel_feat)
        print(f"\nKAIKKI 14 (coord+intensity+color+class): {gtot/1e9:.1f} GB pakattuna")
        return

    sites = {int(x) for x in a.sites.split(",") if x.strip() != ""}
    feats = set(a.features.split(","))
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    todo = [f for f in files if parse(f["name"])[0] in sites and parse(f["name"])[1] in feats]
    tot = sum(f["size"] for f in todo)
    print(f"Ladataan {len(todo)} tiedostoa, {tot/1e9:.1f} GB -> {out}")
    import time
    for i, f in enumerate(todo):
        dst = out / f["name"]
        url = f"{HOST}/api/access/datafile/{f['id']}"
        target = f["size"]
        for attempt in range(1, 9):
            have = dst.stat().st_size if dst.exists() else 0
            if target and have == target:
                break  # valmis
            if have > target and target:      # korruptoitunut/ylipitkä → alusta
                dst.unlink(); have = 0
            mode = "ab" if have > 0 else "wb"
            headers = {"Range": f"bytes={have}-"} if have > 0 else {}
            tag = f"  [{i+1}/{len(todo)}] {f['name']} ({target/1e9:.2f} GB)"
            print(f"{tag}  yritys {attempt}, alkaen {have/1e9:.2f} GB…", flush=True)
            try:
                with requests.get(url, stream=True, timeout=120, headers=headers) as r:
                    # 200 ilman Range-tukea → aloita alusta; 206 → jatka
                    if have > 0 and r.status_code == 200:
                        dst.unlink(); mode = "wb"
                    r.raise_for_status()
                    with open(dst, mode) as fh:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            fh.write(chunk)
            except Exception as e:
                print(f"    katkos: {type(e).__name__} — retry {2*attempt}s", flush=True)
                time.sleep(2 * attempt); continue
            if not target:      # koko tuntematon → hyväksy yksi lataus
                break
        else:
            print(f"    VAROITUS: {f['name']} ei latautunut täyteen 8 yrityksellä", flush=True)
    print("VALMIS lataus.")


if __name__ == "__main__":
    main()
