#!/bin/bash

# Make sure MySQL is running
if ! docker ps | grep palona-sql > /dev/null; then
  echo "MySQL container is not running. Starting it now..."
  docker-compose up -d mysql
  
  # Wait for MySQL to be ready
  echo "Waiting for MySQL to start..."
  sleep 15
fi

# Check if the container is ready
if ! docker exec palona-sql mysql -upalona -ppalonapassword -e "SELECT 1;" > /dev/null 2>&1; then
  echo "MySQL container is not ready yet. Waiting a bit longer..."
  sleep 10
  
  # Check again
  if ! docker exec palona-sql mysql -upalona -ppalonapassword -e "SELECT 1;" > /dev/null 2>&1; then
    echo "Error: MySQL container is not responding. Please check the logs."
    exit 1
  fi
fi

echo "MySQL container is ready."

# Method selection: Ask user which method to use
echo "Choose database initialization method:"
echo "1) Using Python script (recommended)"
echo "2) Using SQL files directly"
read -r method_choice

if [[ "$method_choice" == "1" ]]; then
  # Python script method
  echo "Initializing database using Python script..."
  
  # Set environment variables for database connection
  export DB_HOST=localhost
  export DB_PORT=3306
  export DB_USER=palona
  export DB_PASSWORD=palonapassword
  export DB_NAME=palona_shop
  
if [[ "$method_choice" == "2" ]]; then
  # SQL files method
  echo "Initializing database using SQL files directly..."
  
  # Run the shell script
  if [ -f "backend/db/init/init_mysql.sh" ]; then
    backend/db/init/init_mysql.sh
  else
    echo "Error: init_mysql.sh not found in backend/db/init."
    exit 1
  fi
  
else
  echo "Invalid choice. Exiting."
  exit 1
fi

echo "Database initialization process completed." 