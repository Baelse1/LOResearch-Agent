"""Audit uploaded run artifacts, replay best candidate, export measured tables/plots."""
import argparse
from datetime import datetime,timedelta,timezone
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from density_tools import calculate,Candidate

ROOT=Path(__file__).resolve().parent


def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)


def audit(directory):
    directory=Path(directory)
    state=json.loads((directory/'final_state.json').read_text(encoding='utf-8'))
    events=[json.loads(x) for x in (directory/'trace.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
    previous='0'*64
    for raw in events:
        event=dict(raw);digest=event.pop('sha256')
        if event['previous_sha256']!=previous or hashlib.sha256(canonical(event).encode()).hexdigest()!=digest:
            raise ValueError('Trace hash-chain validation failed')
        previous=digest
    responses=[e for e in events if e['kind']=='model_response']
    requests=[e for e in events if e['kind']=='model_request']
    tool_events=[e for e in events if e['kind']=='tool_result']
    if len(responses)!=len(tool_events) or len(requests)!=len(responses):
        raise ValueError('This completed run must have a one-to-one request/response/tool sequence')
    if state['observations']!=[e['payload']['observation'] for e in tool_events]:
        raise ValueError('Final state and trace tool results differ')
    if state['iteration']!=len(responses):raise ValueError('Iteration count mismatch')
    all_candidates=[];rounds=[]
    for i,(request,response,tool) in enumerate(zip(requests,responses,tool_events),1):
        messages=request['payload']['messages']
        if len(messages)!=2+2*(i-1): raise ValueError('Unexpected history length')
        for j in range(i-1):
            if messages[2+2*j]['content']!=responses[j]['payload']['raw_content']:
                raise ValueError('Earlier model response missing from history')
            expected='TOOL_RESULT '+canonical(tool_events[j]['payload']['observation'])
            if messages[3+2*j]['content']!=expected:
                raise ValueError('Earlier tool feedback missing from history')
        proposal=json.loads(response['payload']['raw_content'])
        results=tool['payload']['observation']['results']
        if len(proposal['candidates'])!=len(results): raise ValueError('Candidate/result count mismatch')
        values=[]
        for k,(spec,result) in enumerate(zip(proposal['candidates'],results),1):
            if result['status']!='ok' or not result['verification']['accepted']:
                raise ValueError('This specific report expects all uploaded candidates to pass; inspect rejected result')
            v=result['verification'];fine=v['fine']
            if Candidate.parse(spec)!=Candidate.parse(fine['candidate']):raise ValueError('Candidate changed in execution')
            item=dict(round=i,candidate_id=k,candidate=fine['candidate'],
                lambda_ratio=fine['lambda_ratio'],C_ratio=fine['C_ratio'],
                accepted=v['accepted'],checks=v['checks'],grid_difference=v['grid_difference'],
                coordinate_disagreement=fine['coordinate_disagreement'])
            all_candidates.append(item);values.append(item['lambda_ratio'])
        rounds.append(dict(round=i,hypothesis=proposal['hypothesis'],best_lambda=max(values),
            running_best=max(x['lambda_ratio'] for x in all_candidates),
            usage=response['payload']['metadata'].get('usage'),
            model_seconds=response['payload']['elapsed_seconds'],
            tool_seconds=tool['payload']['elapsed_seconds']))
    best=max(all_candidates,key=lambda x:x['lambda_ratio'])
    recomputations=[calculate(best['candidate'],n,o) for n,o in [(8193,512),(16385,1024),(32769,2048)]]
    original=best['lambda_ratio'];local=recomputations[-1]['lambda_ratio']
    if abs(original-local)>1e-8: raise ValueError('Uploaded best not reproduced')
    independent=json.loads((ROOT/'results/independent_verification.json').read_text(encoding='utf-8'))
    if independent[-1]['candidate']!=best['candidate']:raise ValueError('Independent verification candidate mismatch')
    if abs(independent[-1]['lambda_ratio']-local)>1e-8:raise ValueError('Independent verification failed')
    usage={key:sum(r['usage'][key] for r in rounds) for key in ['input_tokens','output_tokens','total_tokens']}
    start=next(e for e in events if e['kind']=='run_start')
    end=next(e for e in events if e['kind']=='run_end')
    local_time=lambda s:datetime.fromisoformat(s).astimezone(timezone(timedelta(hours=8))).isoformat()
    summary=dict(model=start['payload']['model'],provenance='user_uploaded_autonomous_chatgpt_plan_run',
        round_count=len(rounds),candidate_count=len(all_candidates),all_candidates_accepted=True,
        event_count=len(events),hash_chain_valid=True,state_matches_trace=True,feedback_history_valid=True,
        ended_by_model=end['payload']['ended_by_model'],stop_reason='configured_model_call_budget',
        elapsed_seconds=end['payload']['elapsed_seconds'],start_time_shanghai=local_time(start['time_utc']),
        end_time_shanghai=local_time(end['time_utc']),usage=usage,
        model_seconds=sum(x['model_seconds'] for x in rounds),tool_seconds=sum(x['tool_seconds'] for x in rounds),
        rounds=rounds,candidates=all_candidates,best=best,local_recomputations=recomputations,
        independent_verifications=independent,
        improvement_over_fixed_scan=original-1.7009741386617967,
        difference_above_historical_2016=original-1.701052,
        source_hashes={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ['trace.jsonl','final_state.json']},
        verification_environment=dict(python=sys.version,platform=platform.platform(),
            versions={n:importlib.metadata.version(n) for n in ['numpy','scipy','matplotlib']}),
        claims_limit=['Hash chain detects changes, not external authentication of authorship/provider receipts.',
          'SCE density functional numerical result, not a finite-kinetic wavefunction proof.',
          'No interval arithmetic; numerical agreement is not a theorem.',
          'Historical benchmark exceeded numerically; current record and novelty unverified.',
          'Different candidate families and budgets prevent a causal superiority claim over fixed search.',
          'Run consumed provider-reported plan tokens; monetary cost is not inferred.',
          'One completed run; no multiple-seed statistical evidence.'])
    out=ROOT/'results/audited_actual_run';out.mkdir(exist_ok=True)
    (out/'audit_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'candidate_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['round','candidate_id','alpha','radius','width','bumps','lambda_ratio','C_ratio','accepted']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for x in all_candidates:
            row={k:x[k] for k in ['round','candidate_id','lambda_ratio','C_ratio','accepted']}
            row.update(x['candidate']);row['bumps']=canonical(row['bumps']);writer.writerow(row)
    xs=[x['round'] for x in rounds]
    fig,ax=plt.subplots(figsize=(8,3.6),constrained_layout=True)
    ax.plot(xs,[x['best_lambda'] for x in rounds],'-o',label='Best candidate in each round',color='#1f6f8b')
    ax.axhline(1.701052,ls='--',color='#b45f06',label='Historical comparator (2016)')
    ax.axhline(1.7009741386617967,ls=':',color='#667788',label='Earlier fixed-family search')
    ax.set(xlabel='Model round',ylabel='Lambda ratio',xticks=xs,title='One actual autonomous research run')
    ax.ticklabel_format(axis='y',style='plain',useOffset=False);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(out/'iteration_curve.png',dpi=180);plt.close(fig)
    c=Candidate.parse(best['candidate']);r=np.linspace(0,c.radius,1200)
    rho=independent[-1]['normalizing_constant']*c.shape(r)
    fig,axes=plt.subplots(1,2,figsize=(9,3.1),constrained_layout=True)
    axes[0].plot(r,rho,color='#1f6f8b');axes[0].set(xlabel='r',ylabel='rho(r)',title='Best candidate density')
    axes[1].plot(r,4*np.pi*r*r*rho,color='#965b36');axes[1].set(xlabel='r',ylabel='4 pi r^2 rho(r)',title='Radial electron-number density')
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(out/'best_density.png',dpi=180);plt.close(fig)
    print('Audit completed:',out)
    print('Model rounds:',len(rounds),'candidates:',len(all_candidates),'best lambda:',original)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',type=Path,default=ROOT/'results/actual_chatgpt_run_20261027')
    audit(parser.parse_args().run_dir)
