# 先看这里：当前在做什么？

本压缩包合并了前三阶段完整项目代码、实际计算数据和阶段PDF。
它是当前已经实现部分的完整源码，不表示“开放问题已解决”或“最终作业已完成”。
不需要另外下载前两个压缩包。建议先阅读本文件，不要一开始就运行API程序。

## 我们的目标

开发一个研究型智能体，研究Lieb-Oxford最优常数问题的双电子球对称子问题。
智能体提出电子密度形状，固定数值程序计算比值并验证，再把结果返回模型修改。
真实的模型—工具反馈过程是课程要求的运行与迭代证据。

## 现在完成了什么

1. 数值评估器：能计算给定密度的能量与比值，并做正确性检查。
2. 固定搜索：完成81次候选计算，作为不用模型的对照。
3. 平滑密度工具：增加平滑边界和局部扰动。
4. 本次ChatGPT会话中的4轮提议与工具反馈，共16候选，原始数据已保存。
5. LangGraph自动循环：代码已实现，离线与模拟API测试通过。
6. 三页阶段PDF：位于output/pdf/lo_research_phase3.pdf。

当前最好lambda约1.701034599881，仍低于已核查的历史比较值1.701052。
没有严格认证新界、没有证明全局最优、没有确认最新文献纪录。
尚未完成：你本机的真实模型API自动运行、最终研究报告、上传GitHub。

## API究竟是什么？

API是电脑上的Python程序调用模型服务的接口。
你手动在聊天窗口里提问，是你把任务交给模型；程序自动循环时，需要一个程序可调用的入口。

有API：程序把实验结果发给模型，模型提出新候选，程序继续计算。
没有API：所有数值计算、已有结果复现和离线测试照常运行；不能自动向外部模型索取新研究提议。
本项目不是通过API训练模型，也不需要从头训练大模型。
本地模型也能替代外部服务，但需要配置推理服务以及匹配的接口；本包没有捆绑模型权重。
只有明确运行04_run_live_agent.py或run_live_agent.py时，才会调用你配置的API，服务可能收费。

## 建议操作顺序：先不配置API

1. 在你的Python编辑器里打开解压后的完整文件夹。
2. 若缺依赖，运行install_dependencies.py，使用当前解释器安装所需库。
3. 运行01_run_baseline.py。应看到三种密度和Checks passed: 10/10。
4. 运行02_run_fixed_search.py。应看到本轮最好截断候选和Checks: 7 / 7。
5. 运行03_run_offline_test.py。应看到Offline graph tests passed。

上面三个编号程序都不会发起模型API请求。
先理解已有程序在计算什么，再进行下一项。

## 配置API：等上面程序跑通以后再做

复制.env.example为.env（不能是.env.txt），只在本机填写接口地址、模型和密钥。
密钥、地址和模型必须来自同一个服务。不得发送密钥给聊天窗口或上传GitHub。
运行04_run_live_agent.py：最多6次真实模型请求，每次最多4个候选。
这是调用已有模型，不是训练或微调。实际收费取决于服务，不在代码中假定价格。
结果保存在results/live_时间戳/trace.jsonl和final_state.json。
HTTP或网络错误不会自动重试。

## 各部分在哪里

| 文件或目录 | 用途 |
|---|---|
| density_tools.py | 平滑密度和固定数值验证器 |
| research_agent.py | LangGraph流程、模型接口与日志 |
| research_notes.json | 当前文献笔记及历史比较值 |
| proposals/ | 本次会话的4轮实际提议 |
| results/interactive_session/ | 本次会话工具结果、汇总和哈希 |
| results/offline_test_*/ | 明确标为固定测试数据的图循环测试 |
| baselines/lo_research_step1/ | 第一阶段完整数值基线源码与结果 |
| baselines/lo_research_step2/ | 第二阶段固定搜索完整源码与结果 |
| output/pdf/lo_research_phase3.pdf | 当前3页阶段报告 |
| build_phase_report.py | 从本次会话数据重新生成阶段报告 |
| docs/stage3_README.md | 更详细的第三阶段技术说明 |
| MANIFEST_SHA256.txt | 打包文件的校验值 |

replay_session.py只重算已有提议，不生成新模型提议，不能计为新的智能体研究。
日志中的来源分类必须保留：固定搜索、会话辅助研究、离线测试和真实API自动运行是四种不同证据。

## 依赖与复现

Python 3.10+；requirements.txt包含计算、LangGraph、HTTP接口、绘图和PDF依赖。
requirements-tested.txt记录核心库的本次测试版本，并不代表其他平台都必须安装相同版本。
不使用API时也能运行前三个编号程序。01和02本身仅依赖NumPy、SciPy。
绘图是标准数值图；PDF不是研究已成功或已最终完成的声明。

## GitHub边界

.gitignore排除.env、缓存和虚拟环境；只提交.env.example。
当前尚未上传到你的GitHub，也未替你创建仓库。
最后提交前需要真实API运行记录、研究结论与局限、完整复现说明。
