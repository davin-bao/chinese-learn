FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask flask-sqlalchemy gunicorn

COPY . .

EXPOSE 5000

ENV FLASK_ENV=production

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]