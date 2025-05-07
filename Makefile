# Makefile for MLOps Docker environment

.PHONY: up down up-airflow up-mlflow restart clean logs ps

# Start all services
up:
	docker-compose --profile all up -d

# Start only Airflow services
up-airflow:
	docker-compose --profile airflow up -d

# Start only MLflow services
up-mlflow:
	docker-compose --profile mlflow up -d

# Stop all services
down:
	docker-compose down

# Restart all services
restart: down up

# Stop and remove containers, networks, images, and volumes
clean:
	docker-compose down -v --rmi local

# View logs of all services
logs:
	docker-compose logs -f

# View running containers
ps:
	docker-compose ps

# Create default .env file if it doesn't exist
init:
	@if [ ! -f .env ]; then \
		echo "Creating default .env file"; \
		echo "AIRFLOW_UID=$$(id -u)" > .env; \
		echo "AIRFLOW_GID=0" >> .env; \
		echo "PG_USER=airflow" >> .env; \
		echo "PG_PASSWORD=airflow" >> .env; \
		echo "PG_DATABASE=airflow" >> .env; \
		echo "MINIO_ACCESS_KEY=minio" >> .env; \
		echo "MINIO_SECRET_ACCESS_KEY=minio123" >> .env; \
		echo "MLFLOW_BUCKET_NAME=mlflow" >> .env; \
		echo "DATA_REPO_BUCKET_NAME=data" >> .env; \
		echo "_AIRFLOW_WWW_USER_USERNAME=airflow" >> .env; \
		echo "_AIRFLOW_WWW_USER_PASSWORD=airflow" >> .env; \
	fi

# Run this first time to set up environment
setup: init up

# Help command
help:
	@echo "Available commands:"
	@echo "  make up            - Start all services"
	@echo "  make up-airflow    - Start only Airflow services"
	@echo "  make up-mlflow     - Start only MLflow services"
	@echo "  make down          - Stop all services"
	@echo "  make restart       - Restart all services"
	@echo "  make clean         - Remove all containers, networks, and volumes"
	@echo "  make logs          - View logs of all services"
	@echo "  make ps            - View running containers"
	@echo "  make init          - Create default .env file"
	@echo "  make setup         - Initialize environment and start all services" 