"""Adaptive quadrature + Brent inversion; no production CDF grid/interpolator.

Independent implementation of the same spherical SCE formula, not a different
physical theory. QUADPACK estimates are diagnostics, not rigorous enclosures.
"""
from functools import lru_cache
from math import exp,pi
from pathlib import Path
from time import perf_counter
import json
import warnings
from scipy.integrate import quad,IntegrationWarning
from scipy.optimize import brentq


def recompute(spec,tol=1e-10):
    a=float(spec['alpha']);R=float(spec['radius']);w=float(spec['width'])
    bumps=spec.get('bumps',[])
    start=perf_counter()
    def shape(r):
        if r<=0 or r>=R: return 0.0
        u=min(1.0,(R-r)/w)
        taper=u*u*(3.0-2.0*u)
        b=sum(x['amplitude']*exp(-.5*((r-x['center'])/x['sigma'])**2) for x in bumps)
        return r**a*exp(-r+b)*taper*taper
    def integrate(fun,left,right):
        if right<=left: return (0.0,0.0)
        points=[R-w] if left<R-w<right else None
        return quad(fun,left,right,epsabs=tol,epsrel=tol,points=points,limit=300)
    normalizer,en=integrate(lambda r:4*pi*r*r*shape(r),0,R)
    A=2.0/normalizer
    def rho(r): return A*shape(r)
    def p(r): return 4*pi*r*r*rho(r)
    @lru_cache(maxsize=32768)
    def mass(r):
        if r<=0:return 0.0
        if r>=R:return 2.0
        return integrate(p,0,r)[0]
    def partner(r):
        if r<=0:return R
        if r>=R:return 0.0
        # Direct tail integration avoids subtracting two nearly equal masses.
        target=integrate(p,r,R)[0]
        return brentq(lambda x:mass(x)-target,0,R,xtol=2e-12,rtol=2e-14)
    D,eD=integrate(lambda r:mass(r)*p(r)/r if r>0 else 0.0,0,R)
    V,eV=integrate(lambda r:.5*p(r)/(r+partner(r)) if 0<r<R else 0.0,0,R)
    I,eI=integrate(lambda r:4*pi*r*r*rho(r)**(4/3),0,R)
    def kinetic_integrand(r):
        if not 0<r<R: return 0.0
        derivative=a/r-1
        for b in bumps:
            derivative-=b['amplitude']*(r-b['center'])/b['sigma']**2*exp(-.5*((r-b['center'])/b['sigma'])**2)
        if r>R-w:
            u=(R-r)/w
            derivative-=12*(1-u)/(w*u*(3-2*u))
        return .125*p(r)*derivative**2
    kinetic,eK=integrate(kinetic_integrand,0,R)
    Cx=.75*(3/pi)**(1/3)
    return dict(method='adaptive_radial_quadrature_and_brent_inverse',candidate=spec,
        tolerance=tol,normalization=integrate(p,0,R)[0],normalizing_constant=A,
        hartree=D,sce=V,rho_4_over_3=I,C_ratio=(D-V)/I,lambda_ratio=(D-V)/(Cx*I),
        von_weizsaecker_kinetic=kinetic,quad_estimated_errors=dict(normalizer=en,hartree=eD,sce=eV,integral=eI,kinetic=eK),
        elapsed_seconds=perf_counter()-start,certified=False,
        limitations='Same SCE formula, independent numerical implementation; no interval arithmetic or global optimality.')


def main():
    root=Path(__file__).resolve().parent
    spec=json.loads((root/'best_candidate.json').read_text())
    reports=[]
    for tol in (1e-9,1e-11):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',IntegrationWarning)
            r=recompute(spec,tol)
        r['warnings']=[str(w.message) for w in caught]
        reports.append(r)
        print('Independent result:',r['lambda_ratio'],'tolerance',tol,'warnings',len(caught),flush=True)
    target=root/'results/independent_verification.json'
    target.write_text(json.dumps(reports,indent=2),encoding='utf-8')
    if any(x['warnings'] for x in reports):
        raise RuntimeError('Quadrature warnings: inspect report before using result')
    return reports


if __name__=='__main__':main()
