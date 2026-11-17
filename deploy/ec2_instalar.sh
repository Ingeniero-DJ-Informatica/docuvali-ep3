#!/usr/bin/env bash
# Prepara una instancia EC2 Amazon Linux 2023 y levanta DocuVali.
# Uso (dentro de la EC2):  bash deploy/ec2_instalar.sh
set -euo pipefail
sudo dnf install -y docker git openssl
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
# Docker Compose v2 como plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -sSL "https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

[ -f .env ] || { cp .env.example .env; echo ">> Edita el archivo .env con tus claves y vuelve a ejecutar"; exit 1; }
bash deploy/generar_certificado.sh
sudo docker compose -f docker-compose.yml -f docker-compose.aws.yml up -d --build
sudo docker compose ps
IP=$(curl -s http://checkip.amazonaws.com)
echo ">> Dashboard: https://${IP}/dashboard/   API (Swagger): https://${IP}/docs"
