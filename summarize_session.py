"""Summarize actual interactive traces and perform extra refinement of the best."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
from density_tools import calculate
from research_agent import Ledger,dump

ROOT=Path(__file__).resolve().parent


def main():
    path=ROOT/'results/interactive_session/trace.jsonl'
    Ledger(path,'interactive_chatgpt_session')
    events=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    rounds=[]
    proposal=None
    for event in events:
        if event['kind']=='session_assistant_proposal':
            proposal=event['payload']['proposal']
        elif event['kind']=='tool_result' and proposal is not None:
            results=event['payload']['results']
            passed=[r['verification']['fine'] for r in results
                    if r['status']=='ok' and r['verification']['accepted']]
            rounds.append(dict(round=len(rounds)+1,hypothesis=proposal['hypothesis'],
                results=results,best_lambda=max((r['lambda_ratio'] for r in passed),default=None)))
            proposal=None
    candidates=[r['verification']['fine'] for item in rounds for r in item['results']
                if r['status']=='ok' and r['verification']['accepted']]
    best=max(candidates,key=lambda r:r['lambda_ratio'])
    extra=calculate(best['candidate'],32769,2048)
    extra_delta=abs(best['lambda_ratio']-extra['lambda_ratio'])
    assert extra_delta<5e-7 and extra['coordinate_disagreement']<5e-7
    versions={name:importlib.metadata.version(name) for name in ('numpy','scipy','langgraph','httpx')}
    (ROOT/'requirements-tested.txt').write_text('\n'.join(f'{k}=={v}' for k,v in versions.items())+'\n',encoding='utf-8')
    summary=dict(provenance='interactive_chatgpt_session',autonomous_api_executed=False,
        separate_model_api_calls=0,proposal_rounds=len(rounds),candidate_count=len(candidates),
        rounds=rounds,best=best,extra_refinement=extra,extra_grid_difference=extra_delta,
        gap_to_historical_2016=1.701052-extra['lambda_ratio'],
        source_trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        trace_hash_chain_valid=True,versions=versions,
        source_file_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                           (ROOT/'density_tools.py',ROOT/'research_agent.py')},
        limitations=['Current-session assistant proposals; not a completed autonomous API run.',
          'No original model IDs, token counts or provider receipts available for chat-session proposals.',
          'Hash chain detects accidental alteration; it does not authenticate authorship.',
          'Shared CDF inverse; diagnostics not a rigorous certificate.',
          'No global optimum, current record or universal bound claim.'])
    target=ROOT/'results/interactive_session/summary.json'
    target.write_text(dump(summary),encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['proposal_rounds','candidate_count','extra_grid_difference','gap_to_historical_2016']},indent=2))
    print('Best refined lambda:',extra['lambda_ratio'])
    print('Extra coordinate disagreement:',extra['coordinate_disagreement'])


if __name__=='__main__': main()
