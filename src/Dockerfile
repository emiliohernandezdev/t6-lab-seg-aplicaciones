FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER 10001

# uvicorn con TLS y --ssl-cert-reqs 2 (CERT_REQUIRED): sin cert de cliente
# firmado por la CA del lab no hay handshake.
# 0.0.0.0 es dentro del contenedor; el puerto no se publica al host.
EXPOSE 8443
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-certfile", "/certs/orders-api.crt", "--ssl-keyfile", "/certs/orders-api.key", \
     "--ssl-ca-certs", "/certs/ca.crt", "--ssl-cert-reqs", "2", "--no-server-header"]
