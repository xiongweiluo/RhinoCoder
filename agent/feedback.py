# rhinocoder/agent/feedback.py
#
# RLHF 用户反馈收集 —— JSONL 追加写入。
#
# 反馈标签：accepted | corrected | rejected
# 字段：ts, instruction, generated, edited(nullable), label, route(LOCAL/CLOUD)
#
# JSONL 格式直接兼容 HuggingFace datasets.load_dataset("json", ...)，无需转换。
# 写入前自动剥离坐标值与图层名（调用 sanitizer 模块），确保训练数据合规。
# 线程安全：open(..., "a") 在单进程内以协程串行写入，无需额外锁。
