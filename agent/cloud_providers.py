# rhinocoder/agent/cloud_providers.py
#
# 云端推理模型接入层 —— 适配器模式（Vendor Agnostic）。
#
# 抽象基类 CloudLLMProvider 定义统一 complete() 接口。
# 具体实现：
#   DeepSeekProvider   —— 默认主力，DeepSeek-V4-Pro，1M token 上下文
#   AnthropicProvider  —— 备选，Claude 系列（claude-sonnet-4-5）
#   OpenAIProvider     —— 备选，GPT-4o / Azure OpenAI
#
# 支持运行时热切换，由 rhinocoder.yaml cloud_llm.provider 字段控制。
# 向云端发送请求前必须经过脱敏管道（sanitize_for_cloud），本模块负责调用校验。
