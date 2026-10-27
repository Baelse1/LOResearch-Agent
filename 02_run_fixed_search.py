"""Run fixed density search only. No LLM API request."""
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    script=Path(__file__).resolve().parent/'baselines/lo_research_step2/scan_densities.py'
    subprocess.run([sys.executable,str(script)],check=True)
