"""Run this file from the selected Python editor to install its dependencies."""
from pathlib import Path
import subprocess
import sys

if __name__=='__main__':
    print('Installing requirements into this interpreter:',sys.executable)
    subprocess.run([sys.executable,'-m','pip','install','-r',str(Path(__file__).with_name('requirements.txt'))],check=True)
