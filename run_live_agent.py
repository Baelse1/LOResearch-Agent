"""Explicit live entry point. Running it calls your configured, possibly paid API."""
from research_agent import run_live

if __name__=='__main__':
    print('Calling the API configured in project .env, at most 6 model requests.')
    run_live(6)
