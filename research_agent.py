"""LangGraph research loop with explicit offline, interactive, and live provenance."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
from time import perf_counter
from typing import TypedDict
from urllib.parse import urlparse
import httpx
from langgraph.graph import StateGraph, START, END
from density_tools import evaluate_batch

ROOT=Path(__file__).resolve().parent
SYSTEM='''You are researching the spherical two-electron Lieb-Oxford ratio.
You may propose only bounded density data, not executable code. The fixed evaluator
uses rho=A*r^alpha*exp(-r+sum Gaussian bumps)*T((R-r)/width)^2, T(u)=3u^2-2u^3
clipped to [0,1]. A normalizes the 3D density to two electrons. Every candidate is
verified by grid refinement and two coordinate integrations. Do not edit checks.
Return ONE JSON object with keys action,hypothesis,candidates. action is evaluate
or finish. hypothesis is a short public research rationale, NOT private reasoning.
For evaluate, candidates is a list of 1-4 objects with alpha,radius,width,bumps.
alpha in [0,2], radius in [3,30], width in [0.1,radius/2]. bumps is a list of 0-4
objects with amplitude in [-3,3], center in [0,radius], sigma in [0.1,radius].
For finish, candidates must be []. Ground claims in tool results, distinguish
failed checks, numerical evidence and mathematical proof. Compare with the
historical lambda=1.701052, not a current-record assertion. No global optimality.
Use feedback to revise density shapes. Give no unverified claims of discovery.'''


def dump(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, path, mode):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.mode=mode
        self.previous='0'*64
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                event=json.loads(line)
                digest=event.pop('sha256')
                if event['previous_sha256']!=self.previous or hashlib.sha256(dump(event).encode()).hexdigest()!=digest:
                    raise ValueError('Existing trace hash chain invalid')
                self.previous=digest

    def append(self, kind, payload):
        event=dict(time_utc=timestamp(),mode=self.mode,kind=kind,payload=payload,previous_sha256=self.previous)
        digest=hashlib.sha256(dump(event).encode()).hexdigest()
        event['sha256']=digest
        with self.path.open('a',encoding='utf-8') as f:
            f.write(dump(event)+'\n')
        self.previous=digest


def validate_proposal(proposal):
    if not isinstance(proposal,dict) or set(proposal)!={'action','hypothesis','candidates'}:
        raise ValueError('Required proposal keys: action,hypothesis,candidates')
    if proposal['action'] not in ('evaluate','finish'):
        raise ValueError('Unsupported action')
    if not isinstance(proposal['hypothesis'],str) or not 1<=len(proposal['hypothesis'])<=8000:
        raise ValueError('Invalid public rationale')
    if proposal['action']=='finish' and proposal['candidates']!=[]:
        raise ValueError('finish candidates must be empty')
    if proposal['action']=='evaluate' and (not isinstance(proposal['candidates'],list) or not 1<=len(proposal['candidates'])<=4):
        raise ValueError('Provide 1-4 candidates')
    return proposal


def execute(proposal):
    validate_proposal(proposal)
    if proposal['action']=='finish':
        return dict(action='finish',summary=proposal['hypothesis'])
    return dict(action='evaluate',results=evaluate_batch(proposal['candidates']))


class State(TypedDict):
    messages:list
    iteration:int
    proposal:dict
    stop:bool
    observations:list


def build_graph(provider,ledger,max_rounds):
    if not 1<=max_rounds<=12:
        raise ValueError('max_rounds must be in [1,12]')

    def propose(state):
        started=perf_counter()
        ledger.append('model_request',dict(iteration=state['iteration']+1,messages=state['messages']))
        try:
            raw,metadata=provider(state['messages'])
            ledger.append('model_response',dict(raw_content=raw,metadata=metadata,elapsed_seconds=perf_counter()-started))
            proposal=validate_proposal(json.loads(raw))
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
            # Parsing failures consume a round and are feedback, not fabricated success.
            feedback=dict(error='Invalid JSON proposal: '+str(exc))
            ledger.append('proposal_rejected',feedback)
            return dict(iteration=state['iteration']+1,proposal={},stop=False,
                        messages=state['messages']+[dict(role='user',content=dump(feedback))])
        return dict(iteration=state['iteration']+1,proposal=proposal,
                    stop=proposal['action']=='finish',
                    messages=state['messages']+[dict(role='assistant',content=raw)])

    def perform(state):
        started=perf_counter()
        observation=execute(state['proposal'])
        ledger.append('tool_result',dict(iteration=state['iteration'],observation=observation,
                                         elapsed_seconds=perf_counter()-started))
        return dict(observations=state['observations']+[observation],
                    messages=state['messages']+[dict(role='user',content='TOOL_RESULT '+dump(observation))])

    def route(state):
        if state['stop']:
            ledger.append('finish',dict(iteration=state['iteration'],proposal=state['proposal']))
            return END
        if not state['proposal']:
            return END if state['iteration']>=max_rounds else 'propose'
        return 'perform'

    def next_step(state):
        return END if state['iteration']>=max_rounds else 'propose'

    graph=StateGraph(State)
    graph.add_node('propose',propose)
    graph.add_node('perform',perform)
    graph.add_edge(START,'propose')
    graph.add_conditional_edges('propose',route)
    graph.add_conditional_edges('perform',next_step)
    return graph.compile()


def read_env(path):
    # Project-local configuration only; no process-wide credential inspection.
    if not path.exists():
        raise ValueError('Missing .env: copy .env.example and fill it locally')
    values={}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):
            continue
        key,sep,value=line.partition('=')
        if not sep:
            raise ValueError('Malformed .env line')
        values[key.strip()]=value.strip().strip('\"\'')
    for key in ('LLM_BASE_URL','LLM_MODEL','LLM_API_KEY'):
        if not values.get(key) or values[key].startswith('YOUR_'):
            raise ValueError('Fill '+key+' in project .env')
    url=urlparse(values['LLM_BASE_URL'])
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('LLM_BASE_URL must be an HTTPS API base without credentials/query')
    return values


def live_provider(config,ledger):
    endpoint=config['LLM_BASE_URL'].rstrip('/')+'/chat/completions'
    model=config['LLM_MODEL']
    def call(messages):
        body=dict(model=model,messages=messages,stream=False,max_tokens=4096)
        # Never record Authorization, .env contents or request headers.
        try:
            with httpx.Client(timeout=120,follow_redirects=False) as client:
                response=client.post(endpoint,json=body,headers={'Authorization':'Bearer '+config['LLM_API_KEY']})
                if response.status_code!=200:
                    ledger.append('api_error',dict(http_status=response.status_code))
                    raise RuntimeError(f'API returned HTTP {response.status_code}; no retry was made')
                result=response.json()
        except httpx.RequestError:
            ledger.append('api_error',dict(error='Network or timeout error; no retry'))
            raise RuntimeError('API network/timeout error; inspect connectivity') from None
        metadata=dict(requested_model=model,returned_model=result.get('model'),
                      response_id=result.get('id'),usage=result.get('usage'),
                      finish_reason=result['choices'][0].get('finish_reason'))
        # Raw final content and provider-reported metadata; no private reasoning requested.
        return result['choices'][0]['message']['content'],metadata
    return call


def initial_state():
    notes=json.loads((ROOT/'research_notes.json').read_text(encoding='utf-8'))
    return dict(messages=[dict(role='system',content=SYSTEM),
                          dict(role='user',content=dump(notes))],
                iteration=0,proposal={},stop=False,observations=[])


def run_live(max_rounds):
    config=read_env(ROOT/'.env')
    out=ROOT/'results'/('live_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    ledger=Ledger(out/'trace.jsonl','autonomous_api')
    ledger.append('run_start',dict(max_model_calls=max_rounds,max_candidates_per_call=4,
                  model=config['LLM_MODEL'],langgraph=importlib.metadata.version('langgraph'),
                  note='Actual charge depends on provider; token usage is recorded, currency cost is not inferred.'))
    graph=build_graph(live_provider(config,ledger),ledger,max_rounds)
    state=graph.invoke(initial_state(),config={'recursion_limit':4*max_rounds+8})
    (out/'final_state.json').write_text(dump(state),encoding='utf-8')
    ledger.append('run_end',dict(model_rounds=state['iteration'],tool_rounds=len(state['observations']),
                               ended_by_model=state['stop']))
    print('Live run output:',out)


def interactive_step(proposal_path,session=False):
    proposal=json.loads(Path(proposal_path).read_text(encoding='utf-8'))
    validate_proposal(proposal)
    mode='interactive_chatgpt_session' if session else 'proposal_replay'
    folder='interactive_session' if session else 'proposal_replay'
    ledger=Ledger(ROOT/'results'/folder/'trace.jsonl',mode)
    previous_hash=ledger.previous
    ledger.append('session_assistant_proposal' if session else 'replayed_proposal',dict(proposal=proposal,
                  provenance=('Proposed by ChatGPT in current conversation; no separate model API request.' if session
                              else 'Replay of a saved proposal; NOT a fresh model-generated research step.'),
                  based_on_trace_head=previous_hash))
    observation=execute(proposal)
    ledger.append('tool_result',observation)
    print(json.dumps(observation,ensure_ascii=False,indent=2))


def offline_test():
    out=ROOT/'results'/('offline_test_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    ledger=Ledger(out/'trace.jsonl','scripted_offline_test')
    calls=[]
    proposals=[
        dict(action='evaluate',hypothesis='OFFLINE FIXTURE: reject a negative smoothing width.',
             candidates=[dict(alpha=.5,radius=14,width=-1)]),
        dict(action='evaluate',hypothesis='OFFLINE FIXTURE: test one valid smooth density after feedback.',
             candidates=[dict(alpha=.5,radius=14,width=1)]),
        dict(action='finish',hypothesis='OFFLINE FIXTURE: stop after receiving validation.',candidates=[])]
    def provider(messages):
        calls.append(messages)
        return dump(proposals[len(calls)-1]),dict(provider='scripted_fixture',actual_api_calls=0)
    state=build_graph(provider,ledger,4).invoke(initial_state(),config={'recursion_limit':24})
    assert state['stop'] and state['iteration']==3
    assert state['observations'][0]['results'][0]['status']=='rejected'
    assert state['observations'][1]['results'][0]['verification']['accepted']
    assert 'TOOL_RESULT' in calls[1][-1]['content']
    Ledger(out/'trace.jsonl','scripted_offline_test') # verify hash chain
    # Test hard model-call cap with a provider that never finishes.
    capped=Ledger(out/'cap_test.jsonl','scripted_offline_test')
    def never_finish(messages):
        return dump(proposals[0]),dict(provider='scripted_fixture')
    limited=build_graph(never_finish,capped,2).invoke(initial_state(),config={'recursion_limit':16})
    assert limited['iteration']==2 and len(limited['observations'])==2
    # Parsing failures must be feedback and must not become fabricated tool results.
    bad=Ledger(out/'parse_test.jsonl','scripted_offline_test')
    invalid=build_graph(lambda m:('invalid-json',{}),bad,2).invoke(initial_state(),config={'recursion_limit':16})
    assert invalid['iteration']==2 and invalid['observations']==[]
    (out/'summary.json').write_text(dump(dict(status='passed',actual_api_calls=0,
         checks=['invalid candidate rejection','valid candidate verification','feedback passed to next call',
                 'finish routing','round cap','invalid JSON cap','trace hash-chain validation'])),encoding='utf-8')
    print('Offline graph tests passed. These are scripted fixtures, NOT autonomous model research.')
    print('Test output:',out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline-test',action='store_true')
    mode.add_argument('--live',action='store_true',help='Calls configured API; provider may charge')
    mode.add_argument('--proposal',help='Run a proposal supplied by the assistant in this conversation')
    mode.add_argument('--session-proposal',help='For current-conversation assistant tool execution only; provenance is self-declared')
    parser.add_argument('--max-rounds',type=int,default=6)
    args=parser.parse_args()
    try:
        if args.offline_test: offline_test()
        elif args.live: run_live(args.max_rounds)
        elif args.session_proposal: interactive_step(args.session_proposal,session=True)
        else: interactive_step(args.proposal)
    except (ValueError,RuntimeError) as exc:
        raise SystemExit(str(exc))
