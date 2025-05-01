#!/bin/bash

echo "Setting up Palona AI Shop with Docker..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create .env file for backend
mkdir -p backend
cat > backend/.env << EOF
# OpenAI API Key
OPENAI_API_KEY=open-api-key-here

# Database Configuration (Docker)
DB_HOST=localhost
DB_PORT=3306
DB_USER=palona
DB_PASSWORD=palonapassword
DB_NAME=palona_shop

# Admin token for database initialization
ADMIN_TOKEN=admin-token

# API Base URL
API_BASE_URL=http://localhost:5001
EOF

echo "Created .env file for backend"

# Create .env file for frontend
mkdir -p frontend
cat > frontend/.env << EOF
# API URL
REACT_APP_API_URL=http://palona-backend:5001
EOF

echo "Created .env file for frontend"

# Start Docker containers
echo "Starting Docker containers..."
docker-compose up -d

# Wait for MySQL to be ready
echo "Waiting for MySQL to start..."
sleep 15

# Check if MySQL container is running
if ! docker ps | grep -q palona-sql; then
    echo "Error: MySQL container is not running. Please check Docker logs."
    exit 1
fi

echo "MySQL container is running."

# Check if MySQL is accessible
if ! docker exec palona-sql mysql -upalona -ppalonapassword -e "SELECT 1;" > /dev/null 2>&1; then
    echo "Error: Cannot connect to MySQL. Please check credentials and container status."
    exit 1
fi

echo "MySQL connection verified."

# Check if the database exists
if ! docker exec palona-sql mysql -upalona -ppalonapassword -e "USE palona_shop;" > /dev/null 2>&1; then
    echo "Database 'palona_shop' verified."
else
    echo "Database 'palona_shop' exists."
fi

# Check if backend container is running
if ! docker ps | grep -q palona-backend; then
    echo "Error: Backend container is not running. Please check Docker logs."
    exit 1
fi

echo "Backend container is running on http://localhost:5001."

# Check if frontend container is running
if ! docker ps | grep -q palona-frontend; then
    echo "Error: Frontend container is not running. Please check Docker logs."
    exit 1
fi

echo "Frontend container is running on http://localhost:3000."

echo ""
echo "MySQL setup completed successfully!"
echo ""
echo "To initialize the database schema and sample data, run:"
echo "./docker-init-db.sh"
echo ""
echo "All containers are running! You can access:"
echo "- Frontend: http://localhost:3000"
echo "- Backend API: http://localhost:5001"
echo ""
echo "To view logs, run:"
echo "- Backend: docker logs palona-backend -f"
echo "- Frontend: docker logs palona-frontend -f"
echo "- MySQL: docker logs palona-sql -f" 