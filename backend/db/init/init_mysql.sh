#!/bin/bash

# Database connection parameters
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"3306"}
DB_USER=${DB_USER:-"palona"}
DB_PASSWORD=${DB_PASSWORD:-"palonapassword"}
DB_NAME=${DB_NAME:-"palona_shop"}

# Directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if using Docker
if docker ps | grep -q palona-sql; then
    echo "MySQL Docker container detected. Using Docker for database initialization."
    
    # Create schema
    echo "Creating database schema..."
    docker exec -i palona-sql mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME < "$SCRIPT_DIR/schema.sql"
    
    # Insert sample data
    echo "Inserting sample data..."
    docker exec -i palona-sql mysql -u$DB_USER -p$DB_PASSWORD $DB_NAME < "$SCRIPT_DIR/sample_data.sql"
else
    # Using local MySQL
    echo "Using local MySQL for database initialization."
    
    # Create schema
    echo "Creating database schema..."
    mysql -h$DB_HOST -P$DB_PORT -u$DB_USER -p$DB_PASSWORD $DB_NAME < "$SCRIPT_DIR/schema.sql"
    
    # Insert sample data
    echo "Inserting sample data..."
    mysql -h$DB_HOST -P$DB_PORT -u$DB_USER -p$DB_PASSWORD $DB_NAME < "$SCRIPT_DIR/sample_data.sql"
fi

# Check if the last command was successful
if [ $? -eq 0 ]; then
    echo "Database initialization completed successfully!"
    exit 0
else
    echo "Error: Database initialization failed."
    exit 1
fi 