"""Two-electron spherical SCE baseline. Numerical estimates, not certified bounds."""
from dataclasses import dataclass
from math import exp, log, pi, sqrt
import csv
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
from scipy.integrate import quad
from scipy.special import gammaincinv, gammaln, gammaincc

CX = 0.75 * (3.0 / pi) ** (1.0 / 3.0)


@dataclass
class Density:
    name: str
    beta: float | None = None
    scale: float = 1.0

    def quantile(self, t):
        """r(t) for fraction t of the total electron number, 0<t<1."""
        if self.beta is None:
            return t ** (1.0 / 3.0) / self.scale
        return gammaincinv(3.0 / self.beta, t) ** (1.0 / self.beta) / self.scale

    def log_quantile_derivative(self, t):
        if self.beta is None:
            return -log(3.0 * self.scale) - 2.0 * log(t) / 3.0
        b = self.beta
        x = gammaincinv(3.0 / b, t)
        return x + gammaln(3.0 / b) - log(self.scale * b) - 2.0 * log(x) / b


def evaluate(density, tol=1e-9):
    def integrate(fun):
        # Partition to avoid losing all refinement at a single endpoint.
        a, ea = quad(fun, 0.0, 0.5, epsabs=tol / 2, epsrel=tol, limit=400)
        b, eb = quad(fun, 0.5, 1.0, epsabs=tol / 2, epsrel=tol, limit=400)
        return a + b, ea + eb

    q = density.quantile
    hartree, eh = integrate(lambda t: 4.0 * t / q(t))
    sce, es = integrate(lambda t: 1.0 / (q(t) + q(1.0 - t)))
    factor = 2.0 ** (4.0 / 3.0) / (4.0 * pi) ** (1.0 / 3.0)
    integral, ei = integrate(lambda t: factor * exp(
        -2.0 * log(q(t)) / 3.0 - density.log_quantile_derivative(t) / 3.0))
    raw = (hartree - sce) / integral
    return dict(density=density.name, scale=density.scale, tolerance=tol,
                hartree=hartree, sce=sce, rho_4_over_3=integral,
                C_ratio=raw, lambda_ratio=raw / CX,
                quad_error_estimates=dict(hartree=eh, sce=es, integral=ei))


def independent_exponential_sce(tol=1e-9):
    # Independent radial-coordinate integration, scale=1; total density=exp(-r)/(4*pi).
    def integrand(r):
        partner = gammaincinv(3.0, gammaincc(3.0, r))
        return 0.5 * r * r * exp(-r) / (r + partner)
    return quad(integrand, 0.0, np.inf, epsabs=tol, epsrel=tol, limit=400)[0]


def run(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    densities = [Density('uniform_ball'), Density('exponential', 1.0), Density('gaussian', 2.0)]
    rows = [evaluate(d, tol) for d in densities for tol in (1e-7, 1e-9)]
    checks = []

    def check(name, observed, expected, threshold):
        error = abs(observed - expected)
        checks.append(dict(name=name, observed=observed, expected=expected,
                           absolute_error=error, threshold=threshold, passed=bool(error <= threshold)))

    ball, exponential = rows[1], rows[3]
    check('uniform_ball_hartree', ball['hartree'], 12.0 / 5.0, 1e-8)
    check('uniform_ball_density_integral', ball['rho_4_over_3'],
          2.0 ** (4.0 / 3.0) / (4.0 * pi / 3.0) ** (1.0 / 3.0), 1e-8)
    check('exponential_hartree', exponential['hartree'], 5.0 / 8.0, 1e-8)
    check('exponential_sce_independent_coordinates', exponential['sce'],
          independent_exponential_sce(), 1e-8)
    for d, fine in zip(densities, rows[1::2]):
        scaled = evaluate(Density(d.name, d.beta, 2.0))
        check(d.name + '_scale_invariance', scaled['C_ratio'], fine['C_ratio'], 1e-8)
    for coarse, fine in zip(rows[::2], rows[1::2]):
        check(fine['density'] + '_tolerance_stability', coarse['C_ratio'], fine['C_ratio'], 1e-6)

    result = dict(stage='baseline_evaluator_only', llm_calls=0, certified=False,
                  scope='N=2, spherical SCE; no global optimality claim',
                  environment=dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                                   platform=platform.platform()),
                  dirac_exchange_constant=CX, results=rows, checks=checks,
                  all_checks_passed=all(c['passed'] for c in checks))
    (output_dir / 'baseline_results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    fields = ['density', 'scale', 'tolerance', 'hartree', 'sce', 'rho_4_over_3', 'C_ratio', 'lambda_ratio']
    with (output_dir / 'baseline_results.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print('density             C_ratio       lambda_ratio')
    for r in rows[1::2]:
        print(f"{r['density']:18s} {r['C_ratio']:.9f}   {r['lambda_ratio']:.9f}")
    print(f"Checks passed: {sum(c['passed'] for c in checks)}/{len(checks)}")
    print('Results:', output_dir.resolve())
    print('Numerical estimates only. No model was called; this is not an agent run.')
    if not result['all_checks_passed']:
        raise RuntimeError('Baseline validation failed; inspect JSON checks.')
    return result


if __name__ == '__main__':
    run(Path(__file__).resolve().parent / 'results')
