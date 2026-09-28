FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "python src/manage.py migrate --noinput && python src/manage.py seed_event --if-empty && python src/manage.py runserver 0.0.0.0:8080"]
