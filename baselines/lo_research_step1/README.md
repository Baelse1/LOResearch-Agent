# Lieb–Oxford research agent — stage 1

This package is a numerical baseline evaluator, not yet a research agent.
No model calls, claims of new bounds, or global optimality are included.

## Run

Install dependencies into your selected Python environment using requirements.txt,
then run evaluator.py from your editor. Alternatively run `python evaluator.py`.
The optional Windows batch file requires `python` on PATH.
Outputs are written next to the script in results/. Included results are from the
development environment; rerunning replaces them with your local measurements.

## Model and conventions

Three-dimensional, spin-summed spherical density with integral 2. The spherical
SCE coupling minimizes Coulomb repulsion for a given density. It is an optimal
transport object, not an ordinary finite-kinetic-energy wavefunction. Transferring
claims to physical wavefunction classes requires the corresponding approximation
theorems and admissibility checks. The program only evaluates numerical ratios.

Let t=N_e(r)/2, q(t)=r. Partner radius is q(1-t). Then

* D = 4 integral_0^1 t/q(t) dt;
* V_SCE = integral_0^1 1/(q(t)+q(1-t)) dt;
* I = 2^(4/3)/(4*pi)^(1/3) integral_0^1 q^(-2/3) q'^(-1/3) dt;
* C_ratio=(D-V_SCE)/I;
* lambda_ratio=C_ratio/C_x, C_x=(3/4)(3/pi)^(1/3).

The two ratios MUST NOT be compared without converting conventions. Neither
is the universal optimal constant: these are values for specific trial densities.

Baselines: uniform unit ball; rho=exp(-r)/(4*pi);
rho=2*exp(-r^2)/pi^(3/2). Scale a replaces rho by a^3*rho(a*r).

Validation: analytic Hartree energies, analytic ball density integral, independent
radial-coordinate SCE integration, scale invariance, tolerance refinement.
QUADPACK error estimates and refinement agreement are not rigorous interval bounds.
Dependencies are ranges for convenience; JSON records actually used versions.

## Sources

Seidl, Vuckovic, Gori-Giorgi, Challenging the Lieb–Oxford bound in a systematic
way, Molecular Physics 114 (2016), 1076–1085.
https://arxiv.org/abs/1508.01715
https://doi.org/10.1080/00268976.2015.1136440

Lewin, Lieb, Seiringer, Improved Lieb-Oxford bound on the indirect and exchange
energies, Letters in Mathematical Physics 112 (2022), 92.
https://arxiv.org/abs/2203.12473

This stage reproduces numerical baselines only. Literature maxima and newer
results must be checked before claiming an improvement. The project does not
require that any new mathematical result be found.
