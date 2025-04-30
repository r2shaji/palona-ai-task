#!/bin/bash

# Check if .env file exists for backend
if [ ! -f "backend/.env" ]; then
    echo "Backend .env file not found. Running setup first..."
    ./docker-setup.sh
fi

# Start all Docker services
echo "Starting Palona AI Shop services..."
docker-compose up -d

# Wait for MySQL to be ready
echo "Waiting for MySQL to initialize..."
sleep 10

# Run database initialization if needed
echo "Do you want to initialize the database with schema and sample data? (y/n)"
read -r init_db

if [[ "$init_db" =~ ^[Yy]$ ]]; then
    echo "Initializing database..."

    echo "Using local database initialization script..."
    ./docker-init-db.sh
    fi
fi

echo ""
echo "Palona AI Shop is now running!"
echo ""
echo "- Backend API: http://localhost:5001"
echo "- MySQL Database: localhost:3306"
echo ""
echo "For the frontend, you need to run separately:"
echo "cd frontend && npm start"
echo ""
echo "To stop all services:"
echo "docker-compose down" 