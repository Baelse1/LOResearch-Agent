"""Generate the provisional Chinese report from actual session measurements."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak

ROOT=Path(__file__).resolve().parent
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
FONT='STSong-Light'
BLUE=colors.HexColor('#183A58')
TEXT=colors.HexColor('#243746')
STYLES={
 'title':ParagraphStyle('title',fontName=FONT,fontSize=21,leading=29,textColor=BLUE,spaceAfter=16),
 'sub':ParagraphStyle('sub',fontName=FONT,fontSize=12,leading=19,textColor=BLUE,spaceBefore=12,spaceAfter=7),
 'body':ParagraphStyle('body',fontName=FONT,fontSize=10.5,leading=18,textColor=TEXT,spaceAfter=8),
 'small':ParagraphStyle('small',fontName=FONT,fontSize=9,leading=14,textColor=TEXT,spaceAfter=5),
 'cell':ParagraphStyle('cell',fontName=FONT,fontSize=9,leading=14,textColor=TEXT),
}


def para(text,style='body'):
    return Paragraph(escape(text),STYLES[style])


def table(rows,widths):
    t=Table([[para(str(c),'cell') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
      ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF1F6')),
      ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F6F8FA')]),
      ('LINEBELOW',(0,0),(-1,0),.6,BLUE),('LINEBELOW',(0,-1),(-1,-1),.3,colors.HexColor('#B6C4CE')),
      ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
      ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),
      ('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    return t


def footer(canvas,doc):
    canvas.setStrokeColor(colors.HexColor('#CBD5DF'))
    canvas.line(44,42,A4[0]-44,42)
    canvas.setFont(FONT,9)
    canvas.setFillColor(TEXT)
    canvas.drawString(44,28,'智能体开发 | 阶段3：会话辅助研究与接口验证')
    canvas.drawRightString(A4[0]-44,28,str(doc.page))


def main():
    s=json.loads((ROOT/'results/interactive_session/summary.json').read_text(encoding='utf-8'))
    target=ROOT/'output/pdf/lo_research_phase3.pdf'
    target.parent.mkdir(parents=True,exist_ok=True)
    story=[]
    story += [para('Lieb-Oxford 最优常数问题\n研究型智能体阶段报告','title'),
              para('阶段3 | 2026年10月27日 | 双电子球对称密度','small'),
              para('报告状态','sub'),
              para('已实现开源 LangGraph 研究循环，完成离线图测试与4项模拟API边界测试。当前研究证据来自本次ChatGPT会话中逐轮提出候选、执行工具、读取反馈后再修改的过程；不是已经完成的API全自动研究运行。'),
              para('研究目标与范围','sub'),
              para('在三维双电子球对称密度中，搜索较大的间接Coulomb能比值。lambda=(D-V_SCE)/(C_x I)，I为rho的4/3次幂积分，C_x=(3/4)(3/pi)^(1/3)。这一受限搜索不能确定任意电子数的普适最优常数。'),
              para('密度表示','sub'),
              para('rho=A r^alpha exp(-r+sum b_j(r)) T((R-r)/w)^2。T(u)=3u^2-2u^3，输入截断到[0,1]；b_j是高斯局部扰动。A保证总电子数为2。边界的平方根平滑消失，避免前阶段硬截断的跳跃。'),
              para('逐轮结果','sub')]
    rows=[['轮次','本轮研究动作','本轮最好lambda']]
    labels=['比较平滑层宽度','调整原点幂指数','测试正负局部扰动','细化有利扰动振幅']
    for item,label in zip(s['rounds'],labels):
        rows.append([item['round'],label,f"{item['best_lambda']:.12f}"])
    story += [table(rows,[48,288,170]),Spacer(1,10),
              para(f"本轮最终复核值约为{s['extra_refinement']['lambda_ratio']:.12f}。仍低于2016年论文式(60)的1.701052；没有获得新的严格界或全局最优解。"),PageBreak()]

    story += [para('候选实验与反馈记录','title'),
              para('共4轮会话提议、16个候选。下表全部为实际运行结果；每个候选均通过预设数值检查。固定批量计算不等同于API自主决策。','small')]
    rows=[['轮次','alpha','宽度w','局部扰动','lambda']]
    for item in s['rounds']:
        for entry in item['results']:
            f=entry['verification']['fine'];c=f['candidate']
            b=c['bumps']
            perturb='无' if not b else f"振幅{b[0]['amplitude']:g}, 中心{b[0]['center']:g}"
            rows.append([item['round'],f"{c['alpha']:g}",f"{c['width']:g}",perturb,f"{f['lambda_ratio']:.12f}"])
    story += [table(rows,[38,48,48,202,170]),Spacer(1,10),
              para('观察到的退步与修正','sub'),
              para('宽度2不如宽度1；alpha=0.55明显退步；内侧负扰动不如正扰动；正扰动振幅从0.025增加到0.075后结果下降。因此“平滑越宽越好”或“正扰动越强越好”都不符合本轮数据。这里只否定这些具体参数变化的单调假设，不能外推为一般定理。'),PageBreak()]

    e=s['extra_refinement']
    story += [para('验证、复现与剩余工作','title'),para('数值验证','sub'),
              table([['项目','结果'],
                ['密度归一化',f"{e['normalization']:.12f}"],
                ['网格进一步加密',f"16385到32769点，lambda变化{s['extra_grid_difference']:.3e}"],
                ['不同积分坐标',f"最后一次lambda差异{e['coordinate_disagreement']:.3e}"],
                ['与历史比较值的差距',f"{s['gap_to_historical_2016']:.3e}"],
                ['额外模型API请求','0；本报告不含API自主运行结果']], [165,341]),
              Spacer(1,9),
              para('网格加密与不同坐标积分共享累计密度逆函数，因此不构成完全独立的验证。以上为数值诊断，未使用区间算术，不是严格误差界。密度的有限动能可容许性也不意味着奇异SCE最优耦合本身具有有限动能。'),
              para('代码与运行入口','sub'),
              para('先运行install_dependencies.py安装依赖，再运行run_offline_test.py验证图循环。replay_session.py仅重算已有提议，不产生新模型研究结果。复制.env.example为.env，在本机填写API地址、模型名和密钥，运行run_live_agent.py才会发起最多6次真实模型请求。密钥不得上传GitHub。'),
              para('证据与局限','sub'),
              para('trace.jsonl保存本次会话提议与工具结果；summary.json记录最佳候选、版本与代码哈希。哈希链仅用于发现意外改动，不能认证提议作者。当前会话没有独立的模型ID或token使用凭证。尚未实现自主联网全文阅读、形式化证明或任意密度代码生成。'),
              para('下一步','sub'),
              para('在本机运行真实API闭环，记录模型响应、工具执行和反馈；以相同候选预算比较固定扫描与模型提议。随后核查更新文献、做更强的误差控制，整理最终报告并提交个人GitHub。目前不是最终课程提交版。'),
              para('参考资料','sub'),
              para('[1] Seidl, Vuckovic, Gori-Giorgi. Challenging the Lieb-Oxford bound in a systematic way. Molecular Physics 114 (2016), 1076-1085. DOI: 10.1080/00268976.2015.1136440. 历史值见式(60)。','small'),
              para('[2] Lewin, Lieb, Seiringer. Improved Lieb-Oxford bound on the indirect and exchange energies. Letters in Mathematical Physics 112 (2022), 92. arXiv:2203.12473.','small'),
              para('[3] LangGraph官方文档：docs.langchain.com/oss/python/langgraph/quickstart。模型接口参考DeepSeek官方文档：api-docs.deepseek.com。','small')]
    doc=SimpleDocTemplate(str(target),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=43,bottomMargin=58,
                          title='Lieb-Oxford研究型智能体阶段3报告',author='研究项目阶段记录')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(target)


if __name__=='__main__': main()
