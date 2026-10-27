"""Fixed, reproducible experiments. This script does not call an LLM."""
from dataclasses import dataclass
from math import exp, log, pi, inf, isfinite
from pathlib import Path
from time import perf_counter
import csv
import json
import warnings
import numpy as np
import scipy
from scipy.integrate import quad, IntegrationWarning
from scipy.optimize import minimize_scalar
from scipy.special import gammainc, gammaincinv, gammaln
from evaluator import evaluate, CX


@dataclass
class GammaDensity:
    """rho=A*r^alpha*exp(-a*r), 0<=a*r<R; mass=2.

    R is dimensionless cutoff, a is a pure scale. Hard-cutoff densities are
    classical/SCE benchmarks; they do not have sqrt(rho) in H1 at the cutoff.
    """
    alpha: float = 0.0
    cutoff: float = inf
    scale: float = 1.0

    def __post_init__(self):
        if self.alpha < 0 or self.scale <= 0 or self.cutoff <= 0:
            raise ValueError('alpha>=0, scale>0, cutoff>0 required')
        self.name = f'gamma_alpha={self.alpha:g}_R={self.cutoff:g}'
        self.k = self.alpha + 3.0
        self.mass_fraction = float(gammainc(self.k, self.cutoff))

    def quantile(self, t):
        return gammaincinv(self.k, t * self.mass_fraction) / self.scale

    def log_quantile_derivative(self, t):
        x = gammaincinv(self.k, t * self.mass_fraction)
        return (gammaln(self.k) + log(self.mass_fraction) + x
                - (self.k - 1.0) * log(x) - log(self.scale))


def radial_check(density, tol=1e-10):
    """Recompute D, I in radius x=a*r, with no q' formula."""
    k, p, a, R = density.k, density.mass_fraction, density.scale, density.cutoff
    def radial_pdf(x):
        if x == 0:
            return 0.0
        return 2.0 * exp((k - 1.0) * log(x) - x - gammaln(k)) / p
    normalization = quad(radial_pdf, 0, R, epsabs=tol, epsrel=tol, limit=400)[0]
    def hartree_integrand(x):
        if x == 0:
            return 0.0
        enclosed = 2.0 * gammainc(k, x) / p
        return a * enclosed * radial_pdf(x) / x
    D = quad(hartree_integrand, 0, R, epsabs=tol, epsrel=tol, limit=400)[0]
    log_A = -log(2.0 * pi) - gammaln(k) - log(p)
    s = 3.0 + 4.0 * density.alpha / 3.0
    I = a * exp(log(4*pi) + 4*log_A/3 + gammaln(s) - s*log(4/3)) * gammainc(s, 4*R/3)
    # Inverse CDF still used for partner radius, but integration variable is radius.
    def sce_integrand(x):
        if x == 0:
            return 0.0
        from scipy.special import gammaincc
        # More stable than 1-gammainc(k,x)/p in the infinite tail.
        complement = (gammaincc(k, x) - gammaincc(k, R)) / p
        partner = gammaincinv(k, max(0.0, min(1.0, complement)) * p)
        return 0.5 * a * radial_pdf(x) / (x + partner)
    V = quad(sce_integrand, 0, R, epsabs=tol, epsrel=tol, limit=400)[0]
    return dict(normalization=normalization, hartree=D, sce=V, rho_4_over_3=I,
                C_ratio=(D-V)/I, lambda_ratio=(D-V)/I/CX)


def evaluate_logged(density, tolerance, stage):
    start = perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always', IntegrationWarning)
        row = evaluate(density, tolerance)
    row.update(alpha=density.alpha, cutoff=density.cutoff if isfinite(density.cutoff) else None,
               stage=stage, elapsed_seconds=perf_counter()-start,
               warnings=[str(w.message) for w in caught])
    return row


def main():
    out = Path(__file__).resolve().parent / 'results'
    out.mkdir(exist_ok=True)
    rows = []
    for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
        for R in (3.0, 5.0, 8.0, 12.0, 20.0, 40.0, inf):
            row = evaluate_logged(GammaDensity(alpha, R), 2e-8, 'grid_scan')
            rows.append(row)
        print(f'Completed alpha={alpha:g}', flush=True)

    # Fixed one-dimensional searches, not LLM-designed research iterations.
    optimizations = []
    for alpha in (0.0, 0.5):
        def objective(R):
            row = evaluate_logged(GammaDensity(alpha, float(R)), 2e-8, 'cutoff_optimization')
            rows.append(row)
            return -row['lambda_ratio']
        opt = minimize_scalar(objective, bounds=(3.0, 30.0), method='bounded',
                              options={'xatol': 1e-5, 'maxiter': 60})
        optimizations.append(dict(alpha=alpha, cutoff=float(opt.x), success=bool(opt.success),
                                  evaluations=int(opt.nfev), lambda_ratio=float(-opt.fun)))

    eligible = [r for r in rows if not r['warnings']]
    if not eligible:
        raise RuntimeError('No warning-free candidates')
    best = max(eligible, key=lambda r: r['lambda_ratio'])
    candidate = GammaDensity(best['alpha'], best['cutoff'] if best['cutoff'] is not None else inf)
    refined = [evaluate_logged(candidate, tol, 'independent_validation') for tol in (1e-8, 1e-10)]
    radial = radial_check(candidate)
    fine = refined[-1]
    checks = [dict(name='normalization', difference=abs(radial['normalization']-2), threshold=1e-8)]
    for key in ('hartree', 'sce', 'rho_4_over_3', 'lambda_ratio'):
        checks.append(dict(name='independent_'+key, difference=abs(radial[key]-fine[key]), threshold=1e-7))
    checks.append(dict(name='tolerance_stability', difference=abs(refined[0]['lambda_ratio']-fine['lambda_ratio']), threshold=1e-7))
    scaled = evaluate_logged(GammaDensity(candidate.alpha, candidate.cutoff, 2.0), 1e-10, 'scale_validation')
    checks.append(dict(name='scale_invariance', difference=abs(scaled['lambda_ratio']-fine['lambda_ratio']), threshold=1e-8))
    for check in checks:
        check['passed'] = bool(check['difference'] <= check['threshold'])
    report = dict(stage='fixed_density_search', llm_calls=0, certified=False,
                  literature_comparison=dict(source='Seidl et al. 2016, Eq. (60)',
                                              lambda_value=1.701052,
                                              note='Historical benchmark, not a claim of current best.'),
                  environment=dict(numpy=np.__version__, scipy=scipy.__version__),
                  scan=rows, optimizations=optimizations, best_scan=best,
                  refined=refined, independent_radial=radial, checks=checks,
                  all_checks_passed=all(c['passed'] for c in checks),
                  limitations=['Hard cutoff is discontinuous; classical/SCE trial only.',
                               'Finite-kinetic-energy use requires smooth approximation.',
                               'No rigorous interval enclosures; no global optimum claim.',
                               'Fixed search and optimization, not an LLM agent run.'])
    (out/'search_results.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    columns=['stage','alpha','cutoff','C_ratio','lambda_ratio','tolerance','elapsed_seconds']
    with (out/'search_results.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows+refined+[scaled])
    print('Best candidate:', candidate)
    print('Refined lambda:', fine['lambda_ratio'])
    print('Historical benchmark:',1.701052)
    print('Checks:',sum(c['passed'] for c in checks),'/',len(checks))
    if not report['all_checks_passed'] or any(r['warnings'] for r in refined):
        raise RuntimeError('Candidate validation failed; inspect results JSON')
    return report


if __name__=='__main__':
    main()
