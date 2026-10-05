# 放量红柱美股筛选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 实现本机美股放量黄色 K 线与 BBUY 红柱组合筛选网站。
**Architecture:** Python 本机服务计算指标、持久化股票池和行情并执行限速扫描；浏览器页面请求同源接口，以共享日期轴的 Canvas 图表显示真实行情。
**Tech Stack:** Python 3.9+、Flask、futu-api、NumPy/Pandas、exchange-calendars、SQLite、原生 JavaScript/CSS。
**Spec:** design.md（用户最新指令：放量 + BBUY，直接开始开发）。

## Global Constraints

- 只监听 127.0.0.1，使用 OpenD 行情上下文；不接入交易。
- 同日配合默认：20 日均量含当日、倍数 1.5，最新 5 根已收盘日线。
- 可选此前均量与附近配合，均不可使用尚未发生的未来信号。
- 只处理美股普通股和 ETF；未收盘过滤遵循 XNYS 日历。
- 图表、缓存、设置和启动说明均随项目交付；失败不可用模拟行情替代。

## Review Focus

- 只有放量或只有红柱时不得误命中（Task 1）。
- 当天还未收盘、假期或提前收盘时截止日期正确（Task 2）。
- 导入无效代码、重复代码和非美股代码时不得静默改变证券（Task 2）。
- 缓存有复权变化或请求失败时不得混合错误数据或显示更新成功（Task 2）。
- 网络失败、空候选、取消和忙碌状态要可识别，后续扫描要能恢复（Task 3）。

### Task 1: 指标与组合规则

Files: indicators.py, tests/test_indicators.py。
Interfaces: enrich(bars, settings)->list[dict]；match_signals(rows, settings)->dict。
- [ ] 写独立手算测试：递推 SMA、交叉等号边界、放量均值含/不含当前、BBUY、缺失前次交叉不生背离、附近配合不引用未来、放量单信号不命中。
- [ ] 运行 unittest，确认缺失实现而失败。
- [ ] 实现 VWAP、MACD、KDJ、RSI、底部柱线与原公式信号，输出 JSON 安全值。
- [ ] 运行全部指标测试并提交。

### Task 2: 行情、缓存与服务

Files: market.py, app.py, requirements.txt, tests/test_market.py, tests/test_app.py。
Consumes: Task 1 的 enrich/match_signals。
Produces: /api/status、/api/settings、/api/scan、/api/scan/cancel、/api/results、/api/chart/<symbol>、/api/export。
- [ ] 写交易日历提前收盘与周末测试、代码验证测试、设置边界测试、缓存复权刷新测试、服务同源和忙碌取消恢复测试；先运行确认失败。
- [ ] 实现 OpenD 串行行情连接，额度明细、分页、SQLite 缓存、异步扫描状态、重算与 CSV 导出。
- [ ] 运行整套测试；用 QQQ/SOXX 真行情验证，保存验证摘要，提交。

### Task 3: 页面、图表与交付

Files: static/index.html, static/style.css, static/app.js, static/chart.js, start.command, README.md。
Consumes: Task 2 的 HTTP JSON 接口。
Produces: 中文网站、本机 URL、可重复启动入口。
- [ ] 实现深色界面、股票池导入、组合筛选、候选/全部结果、历史信号表和 CSV。
- [ ] 实现共享日期轴的价格、量、MACD、KDJ、底部指标图表、缩放、拖动、悬停与箭头；黄色 K 线及红色 BBUY 柱必须直接来自计算结果。
- [ ] 在真实行情上检查页面加载、扫描/取消、重算、空结果、导入、选股、图表和导出，修复观察到的问题。
- [ ] 完整测试、独立代码审查、启动脚本验证；保存中文使用说明并打开网站，提交。

## Execution decisions

用户明确要求“帮我开始开发”，按最新规则在当前会话直接执行，不再增加方案审批。副图红柱按源码 BBUY 解读，MACD 正柱单独作为可选条件。网站为本机应用，因 OpenD 为本机 TCP 服务，不做云端部署。
