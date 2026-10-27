"""API boundary tests use dummy fixtures only; no real network or key."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from research_agent import Ledger,live_provider,read_env


class IntegrationTests(unittest.TestCase):
    def test_missing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): read_env(Path(tmp)/'.env')

    def test_insecure_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'.env'
            p.write_text('LLM_BASE_URL=http://example.invalid\nLLM_MODEL=fixture\nLLM_API_KEY=dummy-test-only')
            with self.assertRaises(ValueError): read_env(p)

    def test_mocked_api_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(Path(tmp)/'trace.jsonl','mocked_api_test')
            def handler(request):
                self.assertEqual(str(request.url),'https://example.invalid/v1/chat/completions')
                body=json.loads(request.content)
                self.assertEqual(body['model'],'fixture')
                self.assertEqual(body['stream'],False)
                self.assertEqual(request.headers['Authorization'],'Bearer dummy-test-only')
                return httpx.Response(200,json={'model':'fixture-returned','id':'mock-id',
                  'usage':{'total_tokens':17},'choices':[{'message':{'content':'{"action":"finish","hypothesis":"mock","candidates":[]}'},'finish_reason':'stop'}]})
            client=httpx.Client(transport=httpx.MockTransport(handler))
            with patch('research_agent.httpx.Client',return_value=client):
                raw,meta=live_provider(dict(LLM_BASE_URL='https://example.invalid/v1',
                  LLM_MODEL='fixture',LLM_API_KEY='dummy-test-only'),ledger)([dict(role='user',content='mock')])
            self.assertEqual(json.loads(raw)['action'],'finish')
            self.assertEqual(meta['usage']['total_tokens'],17)

    def test_mocked_api_error_no_key_in_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.jsonl'
            ledger=Ledger(p,'mocked_api_test')
            client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(401,text='dummy-test-only')))
            with patch('research_agent.httpx.Client',return_value=client):
                with self.assertRaises(RuntimeError):
                    live_provider(dict(LLM_BASE_URL='https://example.invalid',LLM_MODEL='fixture',
                        LLM_API_KEY='dummy-test-only'),ledger)([])
            self.assertNotIn('dummy-test-only',p.read_text())
            self.assertIn('401',p.read_text())


if __name__=='__main__': unittest.main()
