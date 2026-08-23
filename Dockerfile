# 보이는 교실 — 컨테이너 이미지
#
# Vercel 같은 서버리스가 아니라 **프로세스가 계속 살아 있는 호스트**용이다
# (Railway, Render, Fly.io, Cloud Run, 학교 서버 등). 서버리스와 달리
# codex 백엔드·긴 턴·로컬 디스크가 전부 그대로 동작한다.
#
#   docker build -t boineun-gyosil .
#   docker run -p 8000:8000 \
#     -e SUPABASE_URL=... -e SUPABASE_ANON_KEY=... -e SUPABASE_JWT_SECRET=... \
#     -v $(pwd)/reports:/app/reports \
#     boineun-gyosil

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=8000

WORKDIR /app

# 의존성을 먼저 — 소스가 바뀌어도 이 층은 캐시된다
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 실행에 필요한 것만 (테스트·문서는 .dockerignore에서 제외)
COPY src/ ./src/
COPY personas/ ./personas/
COPY lessons/ ./lessons/

# 스냅샷·학급·리포트가 쓰이는 곳. 볼륨을 붙이지 않으면 컨테이너와 함께 사라진다
RUN mkdir -p /app/.sessions /app/.classrooms /app/reports/stage

# 루트로 돌리지 않는다
RUN useradd --create-home --shell /bin/false app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
    sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",8000)}/healthz', timeout=4).status==200 else 1)"

CMD ["sh", "-c", "python -m classroom_sim.web --host 0.0.0.0 --port ${PORT}"]
