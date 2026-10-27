"""Calls configured model service, which may charge. This does NOT train a model."""
from research_agent import run_live

if __name__ == '__main__':
    print('Using the API in project .env. At most 6 model requests. Provider may charge.')
    run_live(6)
