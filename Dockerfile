FROM python:3.12-slim

# Desabilita buffer de output do Python (para ver prints imediatamente)
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema necessárias para o MySQL e compilação de pacotes Python
RUN apt-get update && apt-get install -y default-libmysqlclient-dev build-essential pkg-config

WORKDIR /app

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY app/ /app/

# Gunicorn em produção com logs visíveis
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info", "app:app"]
