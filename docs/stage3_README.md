# LOResearch-Agent：阶段3

基于开源 LangGraph 开发的双电子球对称 Lieb-Oxford 密度搜索工具与研究循环。
本包包含真实的当前会话辅助实验，以及尚待本机验证的模型API自动运行入口。

## 先读清楚三种运行来源

| 来源 | 含义 | 随包状态 |
|---|---|---|
| interactive_chatgpt_session | 本次ChatGPT会话提出候选，执行工具，阅读反馈后再提下一轮 | 实际完成4轮、16候选 |
| scripted_offline_test / mocked_api_test | 固定测试数据检验图循环、接口与拒绝机制 | 已运行，通过 |
| autonomous_api | 本机配置模型后，由LangGraph连续调用模型和工具 | 本环境没有执行，不含真实API实验数据 |

replay_session.py只是重算已有提议，模式为proposal_replay，不能当作新模型研究。
会话提议的来源是项目记录的自声明，不具备模型API签名或独立token凭证。
无需把自己的密钥发到聊天中；本包不含任何可用密钥。

## Windows上不打开终端的操作

1. 将本文件夹解压到独立位置，用你的Python编辑器打开。
2. 运行install_dependencies.py。它通过当前编辑器选中的解释器安装requirements.txt。
3. 运行run_offline_test.py。应显示Offline graph tests passed；这一步不调用模型。
4. 复制.env.example，副本改名为.env。确认Windows显示扩展名，不能叫.env.txt。
5. 在.env中填写LLM_BASE_URL、LLM_MODEL、LLM_API_KEY。使用你有权限访问的API；地址与模型必须来自同一服务。
6. 默认例子是DeepSeek官方API配置；若使用其他兼容服务，替换完整配置。接口必须支持非流式/chat/completions与max_tokens参数。
7. 运行run_live_agent.py会发起真实模型请求，服务可能收费。最多6次模型调用、每次最多4个密度候选；不会后台无限运行。
8. 运行结果保存在results/live_时间戳/，包含trace.jsonl和final_state.json。HTTP错误不自动重试。

支持Python 3.10+。普通依赖范围见requirements.txt；本次精确测试版本见requirements-tested.txt。
不要不加判断地把当前Linux测试版本强装到旧Python环境。

## 工具与图流程

propose（模型给出结构化候选） -> perform（固定工具执行与验证） -> propose。
模型可以finish，也会在调用次数上限处停止。无效JSON会消耗一轮并返回错误反馈。
模型只能提交有界密度参数，不执行其生成的Python，不允许模型修改评估器。
每轮必须提供简短、可公开的研究依据，而不是索取模型私有思维过程。
当前模型只能读取随包文献笔记并改变受限密度族，尚未接入自主联网检索和全文阅读。

## 数学模型

rho(r)=A*r^alpha*exp(-r+sum b_j(r))*T((R-r)/w)^2，0<=r<=R。
T(u)=3u^2-2u^3，输入截断到[0,1]。
b_j(r)=amplitude*exp(-0.5*((r-center)/sigma)^2)。
A归一化三维电子总数为2；alpha在[0,2]，R在[3,30]，w在[0.1,R/2]。
平方根的径向梯度在原点的积分行为为r^alpha，边界为正次幂，因此此密度族满足有限动能密度的H1条件。
这不表示它一定是某个物理Coulomb外势的基态密度，也不表示奇异SCE最优耦合有有限动能。

评价lambda=(D-V_SCE)/(C_x I)，I=积分rho^(4/3)，C_x=(3/4)(3/pi)^(1/3)。
先在径向网格上积分；再转到累计电子分数坐标积分。
用8193和16385点对照；接受阈值预设为网格差和坐标差均小于5e-7。
两种积分共享CDF逆函数，不是完全独立的算法。不是区间算术，不是严格认证界。
每个候选的归一化、网格误差诊断和坐标差均保存在原始日志中。

## 本次实际结果

| 轮次 | 根据反馈作出的研究动作 | 本轮最好lambda |
|---|---|---:|
| 1 | 对硬截断候选增加平滑边界，比较宽度 | 1.700974541964 |
| 2 | 缩小幂指数搜索间隔 | 1.701027507842 |
| 3 | 比较局部正负扰动 | 1.701031337203 |
| 4 | 调整有利扰动的振幅，并保留退步实例 | 1.701034599881 |

额外32769点加密与2048阶分位数积分复核：lambda约1.701034599880545。
仍低于2016年论文式(60)的1.701052；没有证明全局最优，也没有核实当前文献纪录。
原始提议见proposals/；实际记录见results/interactive_session/trace.jsonl。
summary.json还记录测试版本、代码哈希、原始trace哈希和进一步加密结果。
哈希链只是改动检测，不是外部真实性认证。

## 检查与报告

- run_offline_test.py：7项图循环检查，测试数据均明确标为离线固定数据。
- test_integrations.py：4项API边界测试，用httpx模拟，不连接真实网络、不使用真实密钥。
- replay_session.py：重算保存的4个提议，日志写入独立的proposal_replay目录。
- summarize_session.py：汇总本次会话原始记录，并对最佳候选进一步加密。
- output/pdf/lo_research_phase3.pdf：3页阶段报告，已经检查版面。
- build_phase_report.py：重新生成阶段报告；需额外安装reportlab，报告不是API最终实验报告。

## GitHub提交前

.gitignore排除.env、虚拟环境和缓存。可以提交.env.example，不能提交填好的.env。
日志保存的是模型可见消息、最终公开响应与工具结果，不记录Authorization头或.env内容。
不要在研究提示中手动粘贴密钥。上传前检查实际暂存文件，而不只依赖.gitignore。
当前包尚未上传到用户GitHub；后续应新建独立仓库并上传代码、真实API运行证据与最终报告。

## 参考资料

Seidl, Vuckovic, Gori-Giorgi (2016). Challenging the Lieb-Oxford bound in a systematic way.
Molecular Physics 114, 1076-1085. DOI:10.1080/00268976.2015.1136440。
https://arxiv.org/abs/1508.01715

Lewin, Lieb, Seiringer (2022). Improved Lieb-Oxford bound on the indirect and exchange energies.
Letters in Mathematical Physics 112, 92. https://arxiv.org/abs/2203.12473

LangGraph文档：https://docs.langchain.com/oss/python/langgraph/quickstart
DeepSeek接口文档：https://api-docs.deepseek.com/

本项目中的数学问题范围、理论条件和文献最新状态仍需继续核查；不要把有限密度族数值搜索写成解决普适最优常数问题。
