# Bonus C18 — Infrastructure as Code : Terraform déploie le conteneur de l'API
# sur le réseau du docker compose. Commandes (depuis ce dossier) :
#   terraform init
#   terraform apply -var="api_key=..." -var="database_url=..." -var="mongo_url=..."
terraform {
  required_version = ">= 1.6"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  host = var.docker_host
}

variable "docker_host" {
  description = "Démon Docker (Windows : npipe ; Linux/macOS : unix:///var/run/docker.sock)"
  type        = string
  default     = "npipe:////.//pipe//docker_engine"
}

variable "network" {
  description = "Réseau créé par docker compose (docker network ls)"
  type        = string
  default     = "risk-platform_default"
}

variable "api_key" {
  type      = string
  sensitive = true
}

variable "database_url" {
  description = "Ex. postgresql+psycopg2://risk:<mdp>@postgres:5432/riskdb"
  type        = string
  sensitive   = true
}

variable "mongo_url" {
  type      = string
  sensitive = true
}

resource "docker_image" "api" {
  name = "risk-platform-api:tf"
  build {
    context = "${path.module}/../.."
  }
}

resource "docker_container" "api" {
  name    = "risk-api-tf"
  image   = docker_image.api.image_id
  restart = "unless-stopped"
  env = [
    "API_KEY=${var.api_key}",
    "DATABASE_URL=${var.database_url}",
    "MONGO_URL=${var.mongo_url}",
  ]
  ports {
    internal = 8000
    external = 8001
  }
  networks_advanced {
    name = var.network
  }
}

output "api_url" {
  value = "http://localhost:8001/docs"
}
