"""Responses/SSE provider for officially granted ChatGPT plan usage."""
from datetime import datetime,timezone
from pathlib import Path
import json
from time import perf_counter
import httpx
from chatgpt_auth import CredentialStore,AuthError,RESOURCE,access_record,list_models
from research_agent import Ledger,build_graph,initial_state,dump


def request_body(messages,model):
    instructions='\n\n'.join(x['content'] for x in messages if x['role']=='system')
    inputs=[dict(role=x['role'],content=x['content']) for x in messages if x['role'] in ('user','assistant')]
    # SIWC preview forbids max_output_tokens/temperature/metadata/etc.
    return dict(model=model,instructions=instructions,input=inputs,store=False,stream=True)


def parse_stream(lines):
    data=[];parts=[];completed=None;events=0
    def consume(block):
        nonlocal completed,events
        if not block: return
        payload='\n'.join(block)
        if payload=='[DONE]': return
        try: event=json.loads(payload)
        except ValueError: raise AuthError('Invalid SSE JSON; partial model output was discarded.') from None
        events+=1
        kind=event.get('type','')
        if kind=='response.output_text.delta': parts.append(event.get('delta',''))
        elif kind=='response.completed':
            response=event.get('response',{})
            if response.get('status','completed')!='completed': raise AuthError('Response did not complete.')
            completed=response
        elif kind in ('response.failed','response.incomplete','error'):
            error=event.get('response',{}).get('error') or event.get('error') or {}
            code=error.get('code') if isinstance(error,dict) else None
            known={'subscription_sharing_usage_limit_exceeded','subscription_sharing_usage_unavailable',
                   'subscription_sharing_unsupported_capability','insufficient_scope'}
            suffix=' '+code if code in known else ''
            raise AuthError('Responses stream failed'+suffix+'; partial text discarded; no API-key fallback.')
    for line in lines:
        if line=='': consume(data);data=[]
        elif line.startswith('data:'): data.append(line[5:].lstrip(' '))
    if data: consume(data)
    if completed is None: raise AuthError('Stream ended without response.completed; partial text discarded.')
    final=[]
    for item in completed.get('output',[]):
        if item.get('type')=='message':
            final.extend(c['text'] for c in item.get('content',[]) if c.get('type')=='output_text')
    text=''.join(final) if final else ''.join(parts)
    if not text: raise AuthError('Completed response contained no public text.')
    return text,dict(response_id=completed.get('id'),returned_model=completed.get('model'),
                     usage=completed.get('usage'),terminal_event='response.completed',sse_events=events)


def provider(store,client_id,model):
    def call(messages):
        record=access_record(store,client_id)
        body=request_body(messages,model)
        try:
            with httpx.Client(timeout=httpx.Timeout(180,connect=15),follow_redirects=False) as client:
                with client.stream('POST',RESOURCE+'/responses',json=body,
                     headers={'Authorization':'Bearer '+record['access_token'],'Accept':'text/event-stream'}) as response:
                    if response.status_code!=200:
                        raise AuthError(f'Responses HTTP {response.status_code}; sign-in/plan access may need checking. No retry or paid-key fallback.')
                    text,metadata=parse_stream(response.iter_lines())
        except (httpx.RequestError,ImportError):
            raise AuthError('Responses network/proxy failure; no retry was made.') from None
        metadata.update(provider='official_chatgpt_plan_oauth',requested_model=model)
        return text,metadata
    return call


def run_chatgpt(max_rounds=6,root=None):
    if not 1<=max_rounds<=12: raise AuthError('Model-call budget must be in [1,12].')
    root=Path(root) if root else Path(__file__).resolve().parent
    store=CredentialStore()
    public=store.public();client_id=public['active']
    if not client_id: raise AuthError('Run 05_chatgpt_login.py, authorize and save an available model first.')
    model=public.get('models',{}).get(client_id)
    if not model: raise AuthError('Choose and save a model in 05_chatgpt_login.py first.')
    if model not in {m['slug'] for m in list_models(store,client_id)}:
        raise AuthError('Saved model no longer available; refresh model list in 05_chatgpt_login.py.')
    out=root/'results'/('chatgpt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    ledger=Ledger(out/'trace.jsonl','autonomous_chatgpt_plan')
    ledger.append('run_start',dict(model=model,max_model_calls=max_rounds,
        provider='official_chatgpt_plan_oauth',note='Uses authorized ChatGPT plan limits; no separate API key or fallback.'))
    started=perf_counter()
    try:
        state=build_graph(provider(store,client_id,model),ledger,max_rounds).invoke(
            initial_state(),config={'recursion_limit':4*max_rounds+8})
        (out/'final_state.json').write_text(dump(state),encoding='utf-8')
        ledger.append('run_end',dict(model_rounds=state['iteration'],tool_rounds=len(state['observations']),
                        ended_by_model=state['stop'],elapsed_seconds=perf_counter()-started))
    except AuthError as exc:
        ledger.append('run_failed',dict(safe_error=str(exc),elapsed_seconds=perf_counter()-started))
        print('Partial trace saved:',out)
        raise
    print('ChatGPT automatic research completed. Output:',out)
