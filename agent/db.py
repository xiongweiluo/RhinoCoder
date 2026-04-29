# rhinocoder/agent/db.py
#
# 本地 SQLite 路由决策日志 —— 合规审计与路由质量监控。
#
# 表结构：routing_log
#   ts, inst_hash(sha256), rule_result, clf_label, clf_conf,
#   final_route, privacy_flag, latency_ms
#
# 核心合规告警查询：
#   privacy_flag = 1 AND final_route = 'CLOUD' → 立即告警
# 路由质量预警查询：
#   AVG(clf_conf) < 0.75 → 数据漂移预警
#
# 使用标准库 sqlite3，零外部依赖。
# check_same_thread=False 适配异步主控进程的多协程写入场景。
