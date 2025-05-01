#!/bin/bash

# Make sure the script stops on errors
set -e

echo "Starting Palona AI Shop with Docker..."

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    # First try to get it from .env file
    if [ -f "backend/.env" ]; then
        OPENAI_API_KEY=$(grep OPENAI_API_KEY backend/.env | cut -d '=' -f2)
        if [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ] || [ -z "$OPENAI_API_KEY" ]; then
            echo "Warning: OpenAI API key not found or not set properly."
            echo "Please set it in backend/.env or as an environment variable before running."
            read -p "Do you want to continue without the API key? (y/n) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        else
            export OPENAI_API_KEY
        fi
    else
        echo "Warning: OpenAI API key not set and no .env file found."
        read -p "Do you want to continue without the API key? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Check if containers are already running
if docker ps | grep -q palona; then
    echo "Some Palona containers are already running."
    read -p "Do you want to restart them? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping existing containers..."
        docker-compose down
    fi
fi

# Start all services
echo "Starting all containers (MySQL, Backend, Frontend)..."
docker-compose up -d

echo "Waiting for services to start up..."
sleep 5

# Check if MySQL container is running
if ! docker ps | grep -q palona-sql; then
    echo "Error: MySQL container is not running. Please check Docker logs."
    exit 1
fi

# Wait for MySQL to be ready (container is running but MySQL service might not be)
echo "Waiting for MySQL to be ready..."
until docker exec palona-sql mysqladmin ping -h localhost -u palona -p"palonapassword" --silent; do
    echo "MySQL is not ready yet - waiting..."
    sleep 2
done

echo "MySQL is up and running!"

# Check if database is initialized
if ! docker exec palona-sql mysql -u palona -p"palonapassword" -e "USE palona_shop; SELECT COUNT(*) FROM products;" > /dev/null 2>&1; then
    echo "Database not initialized or tables missing."
    read -p "Do you want to initialize the database now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Run the database initialization script
        ./docker-init-db.sh
    else
        echo "Skipping database initialization. Note that the application may not work correctly."
    fi
else
    echo "Database already initialized."
fi

# Check if backend and frontend are running
if ! docker ps | grep -q palona-backend; then
    echo "Error: Backend container is not running. Check Docker logs with: docker logs palona-backend"
    exit 1
fi

if ! docker ps | grep -q palona-frontend; then
    echo "Error: Frontend container is not running. Check Docker logs with: docker logs palona-frontend"
    exit 1
fi

echo ""
echo "All services are running!"
echo ""
echo "You can access the application at:"
echo "- Frontend: http://localhost:3000"
echo "- Backend API: http://localhost:5001"
echo ""
echo "To view logs, run:"
echo "- All services: docker-compose logs -f"
echo "- Backend only: docker logs palona-backend -f"
echo "- Frontend only: docker logs palona-frontend -f"
echo "- MySQL only: docker logs palona-sql -f"
echo ""
echo "To stop all services, run: docker-compose down" 