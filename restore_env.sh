#!/usr/bin/env bash
# IBSEN 환경 복구 스크립트
# pip install 실수로 버전이 깨졌을 때 검증된 핀 버전으로 되돌립니다.
# 사용법:  bash restore_env.sh
set -e

echo "[IBSEN] 검증된 버전으로 복구합니다..."
conda run -n ibsen pip install \
  "numpy==1.23.5" \
  "pandas==2.1.0" \
  "pydantic==1.10.12" \
  "scikit-learn==1.3.0" \
  "langchain==0.0.354" \
  "langchain-core==0.1.23" \
  "langchain-community==0.0.20" \
  "langsmith==0.0.87" \
  "guidance==0.0.64" \
  "tiktoken==0.7.0" \
  "openai==0.28.0" \
  python-Levenshtein flask flask-cors

echo "[IBSEN] 검증 중..."
conda run -n ibsen python -c "from openai.error import InvalidRequestError; from server.stage import GenerativeStage; print('[IBSEN] 복구 완료 - 정상입니다.')"

# 참고: faiss-cpu 는 pip 이 아니라 conda 로 설치되어 있습니다.
#   conda install -y -n ibsen -c conda-forge faiss-cpu=1.7.4
