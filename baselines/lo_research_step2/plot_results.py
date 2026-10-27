"""Optional static scientific plots from measured JSON data."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
data=json.loads((root/'results/search_results.json').read_text(encoding='utf-8'))
fig,axes=plt.subplots(1,2,figsize=(11,4.2),constrained_layout=True)
for alpha in (0,.25,.5,.75,1):
    rows=[r for r in data['scan'] if r['stage']=='grid_scan' and r['alpha']==alpha and r['cutoff'] is not None]
    axes[0].plot([r['cutoff'] for r in rows],[r['lambda_ratio'] for r in rows],'-o',ms=4,label=f'alpha={alpha:g}')
axes[0].set(xlabel='Dimensionless cutoff R',ylabel='lambda ratio',title='Fixed-grid search: full range')
axes[0].legend(fontsize=8)
rows=[r for r in data['scan'] if r['stage']=='grid_scan' and r['cutoff'] is None]
axes[1].plot([r['alpha'] for r in rows],[r['lambda_ratio'] for r in rows],'-o',label='Untruncated gamma density')
best=data['refined'][-1]
axes[1].scatter([best['alpha']],[best['lambda_ratio']],marker='*',s=110,label='Validated cutoff candidate',zorder=4)
axes[1].axhline(1.701052,color='black',ls='--',lw=1,label='Seidl et al. (2016), Eq. 60')
axes[1].set(xlabel='Power alpha',ylabel='lambda ratio',title='Density shape and historical benchmark')
axes[1].legend(fontsize=8)
for ax in axes:
    ax.grid(alpha=.22)
    ax.ticklabel_format(axis='y',style='plain',useOffset=False)
fig.savefig(root/'results/search_comparison.png',dpi=180)
print(root/'results/search_comparison.png')
