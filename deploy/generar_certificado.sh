#!/usr/bin/env bash
# Certificado TLS autofirmado para HTTPS (en producción: dominio propio + Let's Encrypt o ACM con ALB)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p certs
IP=${1:-$(curl -s --max-time 2 http://checkip.amazonaws.com || echo 127.0.0.1)}
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout certs/docuvali.key -out certs/docuvali.crt \
  -subj "/CN=docuvali" -addext "subjectAltName=IP:${IP},DNS:localhost"
echo "Certificado creado para IP ${IP} en deploy/certs/"

# Usuario y contraseña del dashboard (solo si aún no existen)
[ -f certs/.htpasswd ] || bash crear_clave_dashboard.sh || echo "Aviso: define DASHBOARD_CLAVE en .env y ejecuta deploy/crear_clave_dashboard.sh"
