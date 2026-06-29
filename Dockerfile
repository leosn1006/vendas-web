FROM python:3.12-slim

# Desabilita buffer de output do Python (para ver prints imediatamente)
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema necessárias para o MySQL, compilação de pacotes Python, conversão de PDF e health check
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    curl \
    poppler-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY app/ /app/
COPY static/ /static/

# Gunicorn em produção com filtro de logs do health check
CMD ["gunicorn", "-c", "gunicorn_conf.py", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
