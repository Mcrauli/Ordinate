"""Lataa Zenodo-recordin tiedostoja (resume+retry). Aja:
  python zenodo_download.py RECORD_ID key1,key2 OUT_DIR"""
import sys, time
from pathlib import Path
import requests

rec, keys, out = sys.argv[1], set(sys.argv[2].split(",")), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
d = requests.get(f"https://zenodo.org/api/records/{rec}", timeout=60).json()
for f in d["files"]:
    if f["key"] not in keys: continue
    url = f["links"]["self"]; target = f.get("size", 0); dst = out / f["key"]
    for attempt in range(1, 9):
        have = dst.stat().st_size if dst.exists() else 0
        if target and have == target: break
        if target and have > target: dst.unlink(); have = 0
        hdr = {"Range": f"bytes={have}-"} if have > 0 else {}
        print(f"  {f['key']} ({target/1e9:.2f}GB) yritys {attempt}, alkaen {have/1e9:.2f}GB…", flush=True)
        try:
            with requests.get(url, stream=True, timeout=120, headers=hdr) as r:
                if have > 0 and r.status_code == 200: dst.unlink()
                r.raise_for_status()
                with open(dst, "ab" if have > 0 and r.status_code == 206 else "wb") as fh:
                    for c in r.iter_content(1 << 20): fh.write(c)
        except Exception as e:
            print(f"    katkos {type(e).__name__}, retry", flush=True); time.sleep(2*attempt); continue
        if not target: break
print("VALMIS", flush=True)
