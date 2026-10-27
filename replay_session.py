"""Replay saved proposals. This NEVER counts as a fresh model research run."""
from pathlib import Path
from research_agent import interactive_step

if __name__=='__main__':
    for proposal in sorted(Path(__file__).with_name('proposals').glob('round*.json')):
        print('Replaying',proposal.name)
        interactive_step(proposal,session=False)
