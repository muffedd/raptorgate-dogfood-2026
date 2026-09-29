FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV RAPTORGATE_PUBLIC_PREVIEW=1 DJANGO_DEBUG=0
RUN DJANGO_SECRET_KEY=build-only-secret-not-used-at-runtime RAPTORGATE_PREVIEW_HOST=build.onrender.com DATABASE_URL=postgres://dummy:dummy@build.invalid:5432/dummy python src/manage.py collectstatic --noinput
CMD ["sh", "preview-start.sh"]
