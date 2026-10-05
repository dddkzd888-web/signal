#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")"
screen_port="${SCREENER_PORT:-8765}"
screen_url="http://127.0.0.1:${screen_port}"
screen_open=1
[[ "${1:-}" == '--no-open' ]] && screen_open=0

if curl --noproxy '*' --silent --fail --max-time 2 "${screen_url}/api/status" | /usr/bin/python3 -c 'import sys,json; sys.exit(0 if json.load(sys.stdin).get("application")=="volume-bbuy-screener" else 1)' 2>/dev/null; then
    print "筛选器已运行：${screen_url}"
    [[ "$screen_open" == 1 ]] && open "$screen_url"
    exit 0
fi

if [[ ! -x .venv/bin/python ]]; then
    print '正在准备本机运行环境…'
    /usr/bin/python3 -m venv .venv
fi
if ! cmp -s requirements.txt .venv/installed-requirements.txt; then
    print '正在安装行情与网站依赖（首次需要网络）…'
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/installed-requirements.txt
fi
print "请保持 OpenD 登录，网站地址：${screen_url}"
print '关闭此终端或按 Ctrl+C 可停止网站。'
if [[ "$screen_open" == 1 ]]; then
    (sleep 2; open "$screen_url") &
fi
exec .venv/bin/python app.py --port "$screen_port"
