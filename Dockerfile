FROM python:3.12-slim
WORKDIR /service
COPY app /service/app
RUN mkdir -p /service/data && useradd -u 10001 -m fno && chown -R fno:fno /service/data
USER fno
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FNO_DB=/service/data/observatory.db FNO_BIND=0.0.0.0
EXPOSE 8765
CMD ["python", "-m", "app.server"]
