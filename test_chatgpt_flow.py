"""Mock-only OAuth and Responses checks. No real login or model requests."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from chatgpt_auth import (CredentialStore,AuthError,authorization_parameters,validate_callback,
    validate_identity,access_record,PLAN_SCOPE,ISSUER,list_models)
from chatgpt_provider import request_body,parse_stream,provider
from research_agent import Ledger,build_graph,initial_state,dump


class AuthTests(unittest.TestCase):
    def test_pkce_and_new_registration(self):
        p,s=authorization_parameters('urn:uuid:fixture','http://127.0.0.1:23456/auth/callback')
        self.assertEqual(p['client_id'],'dynamic_agent_client')
        self.assertEqual(p['agent_name_hint'],'LOResearch-Agent')
        expected=base64.urlsafe_b64encode(hashlib.sha256(s['verifier'].encode()).digest()).decode().rstrip('=')
        self.assertEqual(p['code_challenge'],expected)
        self.assertIn(PLAN_SCOPE,p['scope'].split())
        p2,_=authorization_parameters('urn:uuid:fixture','http://127.0.0.1:23456/auth/callback')
        self.assertNotEqual(p['state'],p2['state'])
    def test_returning_registration(self):
        p,s=authorization_parameters('fixture','http://127.0.0.1:1/auth/callback',
                 dict(client_id='oaiapp_fixture',id_token='fake-id-token',email='fixture@example.invalid'))
        self.assertNotIn('agent_name_hint',p)
        self.assertEqual(p['client_id'],'oaiapp_fixture')
        self.assertEqual(p['id_token_hint'],'fake-id-token')
    def test_callback(self):
        _,s=authorization_parameters('fixture','http://127.0.0.1:1/auth/callback')
        self.assertEqual(validate_callback(dict(state=[s['state']],code=['fake-code'],client_id=['oaiapp_fixture']),s),('fake-code','oaiapp_fixture'))
        with self.assertRaises(AuthError): validate_callback(dict(state=['wrong'],code=['fake-code']),s)
        with self.assertRaises(AuthError): validate_callback(dict(state=[s['state']],code=['fake-code']),s)
        with self.assertRaises(AuthError): validate_callback(dict(state=[s['state']],error=['access_denied']),s)
    def test_returning_client_mismatch(self):
        _,s=authorization_parameters('fixture','http://127.0.0.1:1/auth/callback',dict(client_id='oaiapp_old'))
        with self.assertRaises(AuthError):
            validate_callback(dict(state=[s['state']],code=['fake'],client_id=['oaiapp_other']),s)
    def test_signed_identity_validation(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()));jwk['kid']='fixture'
        claims=dict(iss=ISSUER,aud='oaiapp_fixture',sub='fixture-sub',iat=int(time.time()),exp=int(time.time())+300,nonce='fixture-nonce')
        encoded=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'fixture'})
        self.assertEqual(validate_identity(encoded,'oaiapp_fixture','fixture-nonce',dict(keys=[jwk]))['sub'],'fixture-sub')
        with self.assertRaises(AuthError): validate_identity(encoded,'oaiapp_fixture','wrong-nonce',dict(keys=[jwk]))
        with self.assertRaises(AuthError): validate_identity(encoded,'wrong-audience','fixture-nonce',dict(keys=[jwk]))
        claims['exp']=int(time.time())-30
        expired=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'fixture'})
        with self.assertRaises(AuthError): validate_identity(expired,'oaiapp_fixture','fixture-nonce',dict(keys=[jwk]))
    def record(self):
        return dict(client_id='oaiapp_fixture',subject='fixture-sub',email='fixture@example.invalid',
           scopes=[PLAN_SCOPE],access_token='dummy-access',refresh_token='dummy-refresh',
           id_token='dummy-id',expires_at=time.time()+3600)
    def test_local_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CredentialStore(tmp);record=self.record();store.save(record)
            self.assertEqual(store.read(record['client_id'])['access_token'],'dummy-access')
            self.assertNotIn('dummy-access',json.dumps(store.public()))
            self.assertEqual(store.host_id(),store.host_id())
            if os.name!='nt': self.assertEqual(store.path(record['client_id']).stat().st_mode&0o077,0)
            store.clear_tokens(record['client_id'])
            self.assertIsNone(store.public()['active'])
            self.assertEqual(store.public()['accounts'][0]['client_id'],'oaiapp_fixture')
    def test_scope_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CredentialStore(tmp);r=self.record();r['scopes']=[];store.save(r)
            with self.assertRaises(AuthError): access_record(store)
    def test_refresh_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CredentialStore(tmp);r=self.record();r['expires_at']=0;store.save(r)
            response=dict(access_token='dummy-new-access',refresh_token='dummy-new-refresh',expires_in=3600,token_type='Bearer')
            with patch('chatgpt_auth.request_json',return_value=response) as call:
                result=access_record(store)
            self.assertEqual(result['refresh_token'],'dummy-new-refresh')
            self.assertEqual(store.read(r['client_id'])['access_token'],'dummy-new-access')
            self.assertNotIn('scope',call.call_args.kwargs['data'])
    def test_model_catalog(self):
        values=dict(models=[dict(slug='a',display_name='A',visibility='list'),dict(slug='hidden',visibility='hidden')])
        with patch('chatgpt_auth.access_record',return_value=dict(access_token='dummy')),patch('chatgpt_auth.request_json',return_value=values):
            self.assertEqual(list_models(None),[dict(slug='a',display_name='A')])


class StreamTests(unittest.TestCase):
    def lines(self,event): return ['data: '+json.dumps(event),'']
    def test_body_contract(self):
        body=request_body([dict(role='system',content='rules'),dict(role='user',content='question')],'fixture')
        self.assertEqual(set(body),{'model','instructions','input','store','stream'})
        self.assertFalse(body['store']);self.assertTrue(body['stream'])
        self.assertEqual(body['instructions'],'rules')
        self.assertNotIn('system',[x['role'] for x in body['input']])
    def test_completed(self):
        lines=self.lines(dict(type='response.output_text.delta',delta='hello'))
        lines+=self.lines(dict(type='response.completed',response=dict(status='completed',id='mock',usage=dict(total_tokens=9))))
        text,meta=parse_stream(lines)
        self.assertEqual(text,'hello');self.assertEqual(meta['terminal_event'],'response.completed')
    def test_partial_is_not_success(self):
        with self.assertRaises(AuthError): parse_stream(self.lines(dict(type='response.output_text.delta',delta='partial')))
    def test_late_quota_failure(self):
        lines=self.lines(dict(type='response.output_text.delta',delta='partial'))
        lines+=self.lines(dict(type='response.failed',response=dict(error=dict(code='subscription_sharing_usage_limit_exceeded'))))
        with self.assertRaisesRegex(AuthError,'subscription_sharing_usage_limit_exceeded'): parse_stream(lines)
    def test_incomplete(self):
        with self.assertRaises(AuthError): parse_stream(self.lines(dict(type='response.incomplete',response={})))
    def test_mocked_graph_and_stream(self):
        proposals=[dict(action='evaluate',hypothesis='MOCK: test invalid candidate',candidates=[dict(width=-1)]),
          dict(action='evaluate',hypothesis='MOCK: revise using feedback',candidates=[dict(alpha=.4,radius=14,width=1)]),
          dict(action='finish',hypothesis='MOCK: stop',candidates=[])]
        seen=[];real_client=httpx.Client
        def handler(request):
            self.assertEqual(str(request.url),'https://api.openai.com/v1/responses')
            body=json.loads(request.content);seen.append(body)
            raw=json.dumps(proposals[len(seen)-1])
            event=dict(type='response.completed',response=dict(status='completed',id='mock-response',model='fixture',
                output=[dict(type='message',content=[dict(type='output_text',text=raw)])]))
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},text='data: '+json.dumps(event)+'\n\n')
        def client_factory(**kwargs): return real_client(transport=httpx.MockTransport(handler),trust_env=False)
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(Path(tmp)/'trace.jsonl','mocked_chatgpt_plan_test')
            with patch('chatgpt_provider.access_record',return_value=dict(access_token='dummy-access')),patch('chatgpt_provider.httpx.Client',side_effect=client_factory):
                state=build_graph(provider(None,'fixture-client','fixture'),ledger,4).invoke(initial_state(),config={'recursion_limit':24})
            self.assertTrue(state['stop']);self.assertEqual(len(seen),3)
            self.assertIn('TOOL_RESULT',seen[1]['input'][-1]['content'])
            self.assertEqual(state['observations'][0]['results'][0]['status'],'rejected')
            self.assertTrue(state['observations'][1]['results'][0]['verification']['accepted'])
            self.assertNotIn('dummy-access',(Path(tmp)/'trace.jsonl').read_text())


if __name__=='__main__': unittest.main(verbosity=2)
