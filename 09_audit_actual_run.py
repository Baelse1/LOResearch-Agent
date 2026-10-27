"""Audit supplied actual-run logs, export tables and plots; no model requests."""
from pathlib import Path
from audit_run import audit

if __name__=='__main__':
    audit(Path(__file__).resolve().parent/'results/actual_chatgpt_run_20261027')
