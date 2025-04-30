#!/bin/bash

echo "Setting up Palona AI Shop with Docker MySQL..."

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
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration (Docker)
DB_HOST=localhost
DB_PORT=3306
DB_USER=palona
DB_PASSWORD=palonapassword
DB_NAME=palona_shop

# Admin token for database initialization
ADMIN_TOKEN=admin-token
EOF

echo "Created .env file for backend"

# Start Docker containers
echo "Starting Docker containers..."
docker-compose up -d

# Wait for MySQL to be ready
echo "Waiting for MySQL to start..."
sleep 15

# Check if MySQL container is running
if ! docker ps | grep -q palona-mysql; then
    echo "Error: MySQL container is not running. Please check Docker logs."
    exit 1
fi

echo "MySQL container is running."

# Check if MySQL is accessible
if ! docker exec palona-mysql mysql -upalona -ppalonapassword -e "SELECT 1;" > /dev/null 2>&1; then
    echo "Error: Cannot connect to MySQL. Please check credentials and container status."
    exit 1
fi

echo "MySQL connection verified."

# Check if the database exists
if ! docker exec palona-mysql mysql -upalona -ppalonapassword -e "USE palona_shop;" > /dev/null 2>&1; then
    echo "Database 'palona_shop' verified."
else
    echo "Database 'palona_shop' exists."
fi

echo ""
echo "MySQL setup completed successfully!"
echo ""
echo "To initialize the database schema and sample data, run:"
echo "./docker-init-db.sh"
echo ""
echo "To start the application:"
echo "1. Activate your Python virtual environment"
echo "2. Run backend: cd backend/src && python main.py"
echo "3. In a new terminal, run frontend: cd frontend && npm start" 