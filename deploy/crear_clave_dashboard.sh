#!/usr/bin/env bash
# Crea el usuario y la contraseña que Nginx pide antes de mostrar el dashboard.
# Toma DASHBOARD_USUARIO y DASHBOARD_CLAVE del archivo .env (o los recibe como argumentos).
# Uso: bash deploy/crear_clave_dashboard.sh [usuario] [clave]
set -euo pipefail
cd "$(dirname "$0")"
leer() { grep -E "^$1=" ../.env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r"' || true; }
USUARIO=${1:-$(leer DASHBOARD_USUARIO)}
CLAVE=${2:-$(leer DASHBOARD_CLAVE)}
USUARIO=${USUARIO:-revisor}
if [ -z "${CLAVE}" ]; then
  echo "Falta DASHBOARD_CLAVE en .env (o pásala como segundo argumento)." >&2
  exit 1
fi
mkdir -p certs
HASH=$(openssl passwd -apr1 "${CLAVE}")
echo "${USUARIO}:${HASH}" > certs/.htpasswd
chmod 644 certs/.htpasswd  # Nginx debe poder leerlo
echo "Acceso al dashboard creado: usuario '${USUARIO}' (archivo deploy/certs/.htpasswd)"
