# 使用ChatGPT账号自动研究：本次先完成登录

你已完成01数值基线、02固定搜索和03离线图测试。现在使用05登录和06自动研究，无需重新进行前三项。
本包包含全部代码，建议解压到新的独立文件夹，保留原实验文件夹。

## 一、安装新增依赖

在Python编辑器中运行install_dependencies.py。新增PyJWT及加密依赖，HTTP库增加SOCKS代理支持。
不需要打开终端。安装完成后再运行下面入口。

## 二、运行05_chatgpt_login.py

会出现LOResearch-Agent登录窗口：

1. 第一次保留“添加新账号 / 工作区”。
2. 点击 Continue with ChatGPT。
3. 系统默认浏览器会打开OpenAI官方授权页面，登录你要使用的ChatGPT账号。
4. 核对应用名称LOResearch-Agent，并审阅是否允许使用ChatGPT计划额度。
5. 完成后回到程序窗口。它会从已授权账号获取实际可用模型，不预设必须拥有某个型号。
6. 选择模型，点击“保存账号和模型”。

可添加或选择其他账号/工作区；不同注册不混用令牌。
程序不收集账号密码，不读取浏览器Cookie，不要求把令牌发到聊天中。
若提示不可用、缺少资格或未授权计划调用，将停止；“账号登录成功”不等于获得模型权限。
授权最长等待5分钟，超时后重新发起。不要把完整回调网址发给别人。

## 三、运行06_run_chatgpt_agent.py

在账号和模型保存完成后运行。
程序使用官方公共Responses接口与授权的ChatGPT计划额度；不需要API Key或.env。
最多6次模型请求，每次最多4个候选。模型可提前finish，不一定运行满6次。
额度受账号限制，不承诺无限使用；本入口不会自动转到另行计费的API Key方式。

正常结束显示：ChatGPT automatic research completed. Output: ...
结果在results/chatgpt_时间戳/，包含trace.jsonl和final_state.json。
失败会保留已有trace并输出安全错误，不把部分流式文本当作成功结果。

## 四、本次先反馈什么

先完成登录。告诉我窗口是否打开、是否完成授权、是否获得模型列表。
可提供不含私人信息的错误文字。不要发送密码、令牌、完整回调网址或凭证文件。
授权后再运行06，并反馈结束信息或报错。

## 已验证与尚未验证

- 已运行15项离线测试：PKCE、state/client ID、ID令牌签名/issuer/audience/过期/nonce、权限、存储、刷新轮换、模型列表、请求参数、流式终止与模拟模型—工具闭环。
- 测试使用自建测试签名和模拟HTTP响应，不代表OpenAI已接受当前账号注册。
- 当前环境未代替你进行真实浏览器登录或订阅推理；Windows DPAPI分支需在你的Windows上实际验证。
- GUI源码已做语法检查，真实窗口显示也需在你本机确认。
- 如果官方预览接口或资格发生变化，根据安全错误调整；不使用未经支持的后端接口。

## 本地凭证与退出

凭证在项目之外：Windows默认位于本机用户LocalAppData下的LOResearch-Agent/siwc，令牌经DPAPI绑定当前Windows用户保护；Unix使用仅所有者可读的文件。
不要复制凭证目录给他人或放入GitHub。.gitignore另排除了常见凭证文件名。
在05窗口退出会尝试撤销远程会话，再清除本机令牌；未确认撤销时会提示到ChatGPT设置断开应用。
研究日志不记录令牌、Authorization头或包含ID-token hint的授权链接。

## 研究范围

仍是受限球对称双电子密度搜索，尚未自主检索全文、形式化证明或认证最优常数。
完成登录只能建立自动模型—工具闭环，不表示已解决数学问题。
旧阶段3 PDF记录的是会话辅助研究；新的自动运行结果需另行汇总更新报告。

## 官方依据（2026-10-27核查）

https://developers.openai.com/siwc/token-sharing-open-source
https://developers.openai.com/siwc/token-sharing-open-source/sign-in
https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions

首次使用官方dynamic_agent_client入口与本机稳定host ID，收到正式client ID后交换授权码。
使用PKCE、state、nonce，验证ID令牌并确认chatgpt.tokens.use.direct权限。
推理使用https://api.openai.com/v1/responses，store=false、stream=true，收到response.completed才返回结果。
不发送预览接口禁止的max_output_tokens、temperature等字段，不使用backend-api或借用其他应用client ID。
