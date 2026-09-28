"""Matriisi Idle-prioriteetilla (kone kaytossa muuhun samalla)."""
import subprocess
import sys

if __name__ == "__main__":
    import psutil
    psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    sys.exit(subprocess.call([sys.executable, "data/_matrix.py", "--baseline", "data/_matrix_baseline.json"]))
