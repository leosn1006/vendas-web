FROM python:3.12-slim

WORKDIR /app

COPY app/requirements.txt /app/requisitos.txt
RUN pip install --no-cache-dir -r /app/requisitos.txt

COPY app/ /app/

# Gunicorn em produção
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]