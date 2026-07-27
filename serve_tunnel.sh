#!/usr/bin/env bash
# IBSEN 웹을 학생들에게 공개 (Cloudflare Tunnel).
#
# 준비: cloudflared 가 설치돼 있어야 합니다 (이미 /opt/homebrew/bin/cloudflared 확인됨).
#   없으면:  brew install cloudflared
#
# 사용법(터미널 2개):
#   [터미널 1] conda run -n ibsen --no-capture-output python web_server.py
#   [터미널 2] bash serve_tunnel.sh
#
# 실행하면 아래처럼 공개 https 주소가 뜹니다. 그 주소를 학생들에게 공유하세요:
#   https://<무작위-단어>.trycloudflare.com
#
# 로그인·계정 불필요(임시 터널). 서버(web_server.py)와 이 스크립트를 둘 다 켜두면 됩니다.
set -e

PORT="${PORT:-5000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "[IBSEN] cloudflared 가 없습니다.  brew install cloudflared  후 다시 실행하세요."
  exit 1
fi

echo "[IBSEN] http://localhost:${PORT} 를 외부에 공개합니다..."
echo "[IBSEN] 아래 trycloudflare.com 주소를 학생들에게 공유하세요. (Ctrl+C 로 종료)"
cloudflared tunnel --url "http://localhost:${PORT}"
