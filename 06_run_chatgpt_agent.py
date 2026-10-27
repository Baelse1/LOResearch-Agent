"""Use authorized ChatGPT plan access, without an API key. Max 6 model calls."""
from chatgpt_auth import AuthError
from chatgpt_provider import run_chatgpt

if __name__=='__main__':
    print('Starting automatic research with the saved ChatGPT account/model.')
    print('Uses authorized plan limits; at most 6 model requests; no API-key fallback.')
    try: run_chatgpt(6)
    except AuthError as exc:
        print('未完成：',str(exc))
        raise SystemExit(1)
