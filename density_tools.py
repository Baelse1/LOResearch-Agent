"""Fixed spherical SCE evaluator for smooth compactly supported densities.

No generated Python is executed. Candidate density shapes are bounded data.
Numerical agreement is diagnostic, not an interval-arithmetic certificate.
"""
from dataclasses import dataclass, asdict, field
from math import pi
import numpy as np
from scipy.integrate import simpson, cumulative_simpson
from scipy.interpolate import PchipInterpolator
from scipy.special import roots_legendre

CX = 0.75 * (3 / pi) ** (1 / 3)
HISTORICAL_LAMBDA = 1.701052


@dataclass
class Candidate:
    alpha: float = 0.5
    radius: float = 14.0
    width: float = 1.0
    bumps: list = field(default_factory=list)

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - {'alpha', 'radius', 'width', 'bumps'}:
            raise ValueError('Candidate must contain only alpha,radius,width,bumps')
        obj = cls(**value)
        obj.alpha, obj.radius, obj.width = map(float, (obj.alpha, obj.radius, obj.width))
        if not all(np.isfinite(x) for x in (obj.alpha, obj.radius, obj.width)):
            raise ValueError('Non-finite candidate')
        if not (0 <= obj.alpha <= 2 and 3 <= obj.radius <= 30 and .1 <= obj.width <= obj.radius / 2):
            raise ValueError('Require alpha in [0,2], radius in [3,30], width in [0.1,R/2]')
        if not isinstance(obj.bumps, list) or len(obj.bumps) > 4:
            raise ValueError('At most four bumps')
        normalized = []
        for bump in obj.bumps:
            if not isinstance(bump, dict) or set(bump) != {'amplitude','center','sigma'}:
                raise ValueError('Bump keys: amplitude,center,sigma')
            b = {k:float(v) for k,v in bump.items()}
            if not all(np.isfinite(v) for v in b.values()):
                raise ValueError('Non-finite bump')
            if not (-3 <= b['amplitude'] <= 3 and 0 <= b['center'] <= obj.radius and .1 <= b['sigma'] <= obj.radius):
                raise ValueError('Bump out of range')
            normalized.append(b)
        obj.bumps = normalized
        return obj

    def shape(self, r):
        r = np.asarray(r)
        u = np.clip((self.radius-r)/self.width, 0, 1)
        taper = u*u*(3-2*u)
        perturb = np.zeros_like(r)
        for b in self.bumps:
            perturb += b['amplitude']*np.exp(-.5*((r-b['center'])/b['sigma'])**2)
        return np.power(r, self.alpha)*np.exp(-r+perturb)*taper*taper


def calculate(spec, n=8193, quantile_order=512):
    c = Candidate.parse(spec)
    if n not in (2049,4097,8193,16385,32769):
        raise ValueError('Unsupported resolution')
    theta = np.linspace(0, pi, n)
    r = c.radius*(1-np.cos(theta))/2
    shape = c.shape(r)
    norm = simpson(4*pi*r*r*shape, x=r)
    if not np.isfinite(norm) or norm <= 0:
        raise ValueError('Invalid normalization')
    A = 2/norm
    rho = A*shape
    p = 4*pi*r*r*rho
    enclosed = cumulative_simpson(p, x=r, initial=0)
    raw_t = enclosed/2
    t = np.maximum.accumulate(np.clip(raw_t,0,1))
    t[-1] = 1.0
    # A trailing roundoff plateau is possible as taper tends to zero.
    # Retain its first endpoint to avoid a spurious jump in q near t=1.
    unique_t, indices = np.unique(t, return_index=True)
    inverse = PchipInterpolator(unique_t, r[indices], extrapolate=False)
    partner = inverse(np.clip(1-t,0,1))
    D = simpson(np.divide(enclosed*p, r, out=np.zeros_like(r), where=r>0), x=r)
    V = .5*simpson(p/(r+partner), x=r)
    I = simpson(4*pi*r*r*np.power(rho,4/3), x=r)
    raw = (D-V)/I
    # Different integration variable and quadrature; CDF inverse is shared.
    z,w = roots_legendre(quantile_order)
    angle = (z+1)*pi/4
    ts = np.sin(angle)**2
    weights = w*pi/4*np.sin(2*angle)
    q = inverse(ts)
    fq = inverse(1-ts)
    Dq = np.dot(weights,4*ts/q)
    Vq = np.dot(weights,1/(q+fq))
    Iq = np.dot(weights,2*np.cbrt(A*c.shape(q)))
    lq = (Dq-Vq)/Iq/CX
    return dict(candidate=asdict(c), grid_size=n, quantile_order=quantile_order,
                normalization=float(simpson(p,x=r)), hartree=float(D), sce=float(V),
                rho_4_over_3=float(I), C_ratio=float(raw), lambda_ratio=float(raw/CX),
                quantile_lambda=float(lq), coordinate_disagreement=float(abs(raw/CX-lq)),
                cdf_monotonicity_repair=float(np.max(abs(t-raw_t))),
                boundary='C1 square-root taper; finite kinetic density class',
                certified=False)


def verify(spec):
    coarse = calculate(spec,8193,512)
    fine = calculate(spec,16385,1024)
    grid_delta = abs(fine['lambda_ratio']-coarse['lambda_ratio'])
    checks = dict(normalization=abs(fine['normalization']-2)<1e-10,
                  grid_refinement=grid_delta<5e-7,
                  coordinate_agreement=fine['coordinate_disagreement']<5e-7,
                  cdf_repair=fine['cdf_monotonicity_repair']<1e-10)
    return dict(coarse=coarse, fine=fine, grid_difference=grid_delta,
                checks=checks, accepted=all(checks.values()),
                note='Numerically cross-checked; not a certified bound or global optimum.')


def evaluate_batch(candidates):
    if not isinstance(candidates,list) or not 1<=len(candidates)<=4:
        raise ValueError('Each proposal must contain 1 to 4 candidates')
    results=[]
    for spec in candidates:
        try:
            results.append(dict(status='ok',verification=verify(spec)))
        except (ValueError,TypeError,OverflowError,FloatingPointError) as exc:
            results.append(dict(status='rejected',error=str(exc),candidate=spec))
    return results
