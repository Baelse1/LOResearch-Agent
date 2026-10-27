"""Create the actual-run report from audited user logs; never call a model."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'results/audited_actual_run'
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
FONT='STSong-Light';BLUE=colors.HexColor('#173B57');INK=colors.HexColor('#243746')
styles={k:ParagraphStyle(k,fontName=FONT,fontSize=size,leading=lead,textColor=BLUE if k in ('title','sub') else INK,
         spaceAfter=gap,spaceBefore=6 if k=='sub' else 0) for k,size,lead,gap in
         [('title',20,27,14),('sub',12,18,7),('body',10.2,17,8),('small',8.8,13.5,5),('cell',8.7,13,0)]}

def p(text,style='body'):
    return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])

def table(rows,widths,compact=False):
    t=Table([[p(x,'cell') for x in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
    pad=4 if compact else 7
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF1F6')),
      ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F7F9FB')]),
      ('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.6,BLUE),
      ('LINEBELOW',(0,-1),(-1,-1),.35,colors.HexColor('#B7C7D3')),
      ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
      ('TOPPADDING',(0,0),(-1,-1),pad),('BOTTOMPADDING',(0,0),(-1,-1),pad)]))
    return t

def formula_file(name,lines,height):
    fig=plt.figure(figsize=(10,height));fig.patch.set_facecolor('white')
    for i,text in enumerate(lines):fig.text(.02,1-(i+.65)/len(lines),text,fontsize=15,color='#173B57')
    fig.savefig(DATA/name,dpi=180,bbox_inches='tight',pad_inches=.12);plt.close(fig)
    return DATA/name

def footer(c,doc):
    c.setStrokeColor(colors.HexColor('#C7D4DE'));c.line(44,41,A4[0]-44,41)
    c.setFont(FONT,8.8);c.setFillColor(INK)
    c.drawString(44,27,'智能体开发 | 实际运行审阅版 v0.5 | 2026-10-27')
    c.drawRightString(A4[0]-44,27,str(doc.page))

def img(path,width=506,height=None):
    from PIL import Image as PillowImage
    with PillowImage.open(path) as source:
        w,h=source.size
    return Image(str(path),width=width,height=height if height else width*h/w)

def main():
    s=json.loads((DATA/'audit_summary.json').read_text(encoding='utf-8'))
    best=s['best'];v=s['independent_verifications'][-1]
    f1=formula_file('definitions.png',[
      r'$\lambda[\rho]=\frac{D[\rho]-V_{\rm SCE}[\rho]}{C_x I[\rho]},\qquad C_x=\frac{3}{4}(3/\pi)^{1/3},\quad \int\rho=2$',
      r'$I[\rho]=\int_{\mathbb{R}^3}\rho^{4/3},\qquad D[\rho]=\frac{1}{2}\iint\frac{\rho(x)\rho(y)}{|x-y|}\,dx\,dy$',
      r'$N_e(r)=4\pi\int_0^r s^2\rho(s)\,ds,\quad f(r)=N_e^{-1}(2-N_e(r)),\quad V_{\rm SCE}=\frac{1}{2}\int_0^R\frac{4\pi r^2\rho(r)}{r+f(r)}\,dr$'],2.45)
    f2=formula_file('best_formula.png',[
      r'$\rho(r)=A r^{0.42} e^{-r+B(r)} T(15-r)^2,\qquad 0\leq r\leq15$',
      r'$B(r)=-0.2e^{-(r-5.25)^2/(2\cdot1.75^2)}+0.03e^{-(r-2)^2/2}$',
      r'$T(u)=3z^2-2z^3,\quad z=\min(1,\max(0,u)),\qquad A\simeq0.0564961977073$'],2.25)
    story=[p('双电子 Lieb-Oxford 比值搜索\n自动研究与独立数值复核','title'),
      p('基于用户上传的实际运行日志 | 2026年10月27日','small'),
      p('审阅结论','sub'),
      p('已完成一次模型驱动的自动反馈循环。6次模型请求产生24个候选，全部通过原程序的数值检查。后续提议引用前轮结果并调整密度参数，具备智能体运行与迭代的直接记录。'),
      table([['项目','实际记录'],['模型',s['model']],['轮次与候选','6轮 / 24个候选'],
             ['运行时间',f"{s['elapsed_seconds']:.2f}秒；北京时间12:37:17至12:38:41"],
             ['最好比值',f"lambda = {best['lambda_ratio']:.12f}"],
             ['停止原因','达到预设6次模型调用上限；并非模型自行finish']], [130,376]),
      Spacer(1,9),img(DATA/'iteration_curve.png',506,228),
      p('最好候选数值上超过所选2016年比较值1.701052。独立实现复核一致，但尚无严格认证界、最新纪录核实或全局最优性证明。本报告不宣称已解决原始开放问题。'),PageBreak()]

    story += [p('1 研究问题与最好候选','title'),
      p('研究范围为三维、球对称、总电子数为2的密度。使用严格关联电子（SCE）密度泛函，将电子排斥能最小化转化为可计算的一维积分。搜索目标为增大下式中的lambda；它与未归一化C比值相差固定因子C_x。'),
      img(f1,506),Spacer(1,9),
      p('本轮最好候选','sub'),img(f2,506),
      p('参数为alpha=0.42、R=15、平滑层宽度w=1；两项局部扰动分别抑制r约5.25处的密度，并轻微增强r约2处的密度。A由积分自动归一化，r大于15时密度为零。'),
      img(DATA/'best_density.png',506,174),
      p('这些密度不一定来自真实Coulomb外势的基态。密度的有限动能可容许性，也不意味着奇异SCE最优耦合本身是有限动能电子波函数。','small'),PageBreak()]

    story += [p('2 六轮自动研究如何迭代','title')]
    labels=['平滑候选与初步形状比较','细化幂指数，改变负扰动位置','增强外侧抑制，比较扰动中心',
            '比较扰动宽度与幂指数','细化宽度，检验更大计算区域','细化振幅，加入第二项扰动']
    rows=[['轮次','模型依据反馈采取的动作','本轮最好lambda']]
    for item,label in zip(s['rounds'],labels):rows.append([item['round'],label,f"{item['best_lambda']:.12f}"])
    story += [table(rows,[35,316,155]),Spacer(1,12),
      p('反馈改变了后续提议','sub'),
      p('第一轮正的宽扰动使结果降低。第二轮模型据此尝试负扰动，但发现中心3附近并不有利，而中心5的负扰动带来明显改善。第三轮随后比较中心4.5、5和5.5；第四轮又比较中心5.25与不同宽度。'),
      p('第五轮发现sigma=1.75优于1.5和2.5，并检验更大的区域。第六轮没有盲目增加单项扰动强度，而是加入第二项局部扰动；r约2处的正扰动使比值进一步提高。'),
      p('保留退步结果','sub'),
      p('振幅从-0.2增至-0.3时，中心5候选的结果下降；alpha从0.42增至0.54同样退步；第二项扰动使用负振幅也不如正振幅。这些均为实际记录，不是只保留成功候选。'),
      p('停止状态的解释','sub'),
      p('final_state中的stop=false与日志中的ended_by_model=false相一致。程序在第六轮工具执行后按预算结束，run_end正常写入；这不是异常，也不是数学收敛证明。'),
      p('证据强度','sub'),
      p('日志包含每轮公开研究依据、候选参数、实际工具结果、后续请求历史与服务返回的模型/用量信息。它支持“本轮自动反馈研究已经运行”；单次运行不支持“该智能体普遍优于传统优化算法”。'),PageBreak()]

    story += [p('3 全部24个候选结果','title'),
      p('R为区域半径，w为平滑宽度。扰动记作“振幅/中心/标准差”；空白表示无扰动。所有候选均通过原程序检查。','small')]
    rows=[['轮-号','alpha','R/w','局部扰动参数','lambda']]
    for x in s['candidates']:
        c=x['candidate'];b=c['bumps']
        perturb='无' if not b else '\n'.join(f"{y['amplitude']:g} / {y['center']:g} / {y['sigma']:g}" for y in b)
        rows.append([f"{x['round']}-{x['candidate_id']}",f"{c['alpha']:g}",f"{c['radius']:g}/{c['width']:g}",perturb,f"{x['lambda_ratio']:.12f}"])
    story += [table(rows,[42,40,45,230,149],compact=True),Spacer(1,9),
      p('最好候选为6-3；所有原始提议及失败方向均保留。表内末位数字用于复现核对，不表示已经获得同等位数的严格误差保证。','small'),PageBreak()]

    story += [p('4 独立数值复核与结果边界','title'),
      p('首先使用本地原程序重算最佳候选，再使用另一实现：自适应积分计算累计密度，Brent求根计算伴随半径，重新计算各能量。不使用原程序的CDF网格或PCHIP插值。两者共享物理公式，不共享数值反演实现。'),
      table([['方法','设置','lambda'],
        *[['原程序网格',str(x['grid_size'])+'点',f"{x['lambda_ratio']:.12f}"] for x in s['local_recomputations']],
        *[['独立积分/求根','容差'+str(x['tolerance']),f"{x['lambda_ratio']:.12f}"] for x in s['independent_verifications']]], [128,205,173]),
      Spacer(1,10),
      table([['独立计算量','结果'],['Hartree能 D',f"{v['hartree']:.12f}"],
        ['SCE排斥能 V',f"{v['sce']:.12f}"],['密度积分 I',f"{v['rho_4_over_3']:.12f}"],
        ['未归一化C比值',f"{v['C_ratio']:.12f}"],
        ['高精度独立值与上传结果之差',f"{abs(v['lambda_ratio']-best['lambda_ratio']):.3e}"]], [240,266]),
      Spacer(1,10),p('可以写入结论的内容','sub'),
      p(f"最佳比值约1.701296427，较所选2016年比较值高{s['difference_above_historical_2016']:.6e}；不同数值实现得到一致结果。原始24个候选全部通过预设检查。"),
      p('尚不能写入的结论','sub'),
      p('不能称为已证明的新下界、最新世界纪录或普适最优常数。积分容差及多实现一致性不是区间包围。当前只搜索受限密度族；也未完成把SCE构造转移到量子波函数类的严格逼近论证。'),
      p('与固定搜索的比较限制','sub'),
      p('前阶段81次固定搜索得到约1.700974139，本轮数值更高；但两者密度族、先验和预算不同，不能据此单独归因于模型。公平比较需要相同搜索空间、相同评估预算和多次重复。'),PageBreak()]

    story += [p('5 证据审计、复现与提交准备','title'),
      table([['核查项','结果'],['原始日志事件','20条，哈希链验证通过'],['状态与日志','6轮工具结果逐项一致'],
        ['反馈历史','每轮请求包含此前模型提议和工具反馈'],
        ['服务报告的token用量',f"输入{s['usage']['input_tokens']}，输出{s['usage']['output_tokens']}，合计{s['usage']['total_tokens']}"],
        ['时间分解',f"模型等待{s['model_seconds']:.2f}秒；工具执行{s['tool_seconds']:.2f}秒"]], [150,356]),
      Spacer(1,9),
      p('哈希链可发现意外改动，不能独立认证模型服务或作者身份。用量为服务在日志中报告的token，缓存已包含在输入统计中；本报告不推算货币费用。本次审阅和独立复核没有额外调用模型。'),
      p('复现入口','sub'),
      p('上传原始文件保存在results/actual_chatgpt_run_20261027。运行independent_verify.py可重做最佳候选的独立计算；运行audit_run.py可核查日志、复算并生成CSV和图。运行build_actual_run_report.py可生成本报告。以上入口不调用模型。'),
      p('源码与材料','sub'),
      p('代码包包括原模型调用与授权代码、原始日志、24候选CSV、审计JSON、独立验证代码与结果、图表及本PDF。登录令牌保存在用户本机项目外，不随包提供。继续运行06会创建新的研究过程，不等同于从当前最佳候选续跑。'),
      p('后续工作','sub'),
      p('先完成同预算基线和进一步文献核查，再决定扩展密度族或严格误差控制。最终提交前补充作者与课程信息，建立个人GitHub仓库并上传代码、报告和复现说明。当前尚未上传至用户GitHub。'),
      p('参考资料','sub'),
      p('[1] Seidl M., Vuckovic S., Gori-Giorgi P. Challenging the Lieb-Oxford bound in a systematic way. Molecular Physics 114 (2016), 1076-1085. DOI:10.1080/00268976.2015.1136440. 历史比较值见式(60)。','small'),
      p('[2] Lewin M., Lieb E. H., Seiringer R. Improved Lieb-Oxford bound on the indirect and exchange energies. Letters in Mathematical Physics 112 (2022), 92. DOI:10.1007/s11005-022-01584-5.','small'),
      p('[3] 本次直接证据：用户上传trace.jsonl与final_state.json；模型gpt-6.1-sol，运行时间2026-10-27 12:37至12:38（上海时间）。','small')]
    target=ROOT/'output/pdf/LOResearch_actual_run_verified_v0.5.pdf'
    doc=SimpleDocTemplate(str(target),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=56,
                          title='双电子Lieb-Oxford比值搜索：自动研究与独立数值复核',author='研究项目实际运行审阅')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(target)


if __name__=='__main__':main()
