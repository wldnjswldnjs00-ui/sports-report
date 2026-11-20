# 쓰레드 카드 그리기 준비: playwright 파이썬 패키지 + 브라우저.
# GitHub 러너에 미리 깔린 크롬을 쓰고(내려받기 없음 → 실행 시간 절약, 운영체제가 바뀌어도 덜 깨짐),
# 없을 때만 playwright 크롬을 내려받는다. source 로 불러야 CHROMIUM_PATH 가 이 단계에도 적용된다.
python -c "import playwright" 2>/dev/null || { pip install -q playwright==1.47.0 || { sleep 10; pip install -q playwright==1.47.0; }; }
C="$(command -v google-chrome || command -v google-chrome-stable || command -v chromium || command -v chromium-browser || true)"
if [ -n "$C" ]; then
  export CHROMIUM_PATH="$C"
  [ -n "$GITHUB_ENV" ] && echo "CHROMIUM_PATH=$C" >> "$GITHUB_ENV"
else
  python -m playwright install --with-deps chromium >/dev/null
fi
