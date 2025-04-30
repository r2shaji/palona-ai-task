# Palona AI Shop

An e-commerce platform with AI-powered product recommendations and search capabilities.

## Features

- AI-powered product recommendations
- Visual search for products using image uploads
- Chat interface for customer queries
- Product catalog stored in MySQL database
- RESTful API for product data

## Tech Stack

- **Frontend**: React.js
- **Backend**: Flask (Python)
- **Database**: MySQL
- **AI**: OpenAI GPT-4 for chat and recommendations, CLIP for image similarity search
- **ORM**: SQLAlchemy

## Prerequisites

- Python 3.8+
- Node.js 14+
- Docker and Docker Compose (for containerized MySQL)
- OpenAI API Key

## Installation and Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd palona-ai-task
```

### 2. Set up the backend

```bash
# Navigate to the backend directory
cd backend

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Set up MySQL Database

#### Option 1: Using Docker (Recommended)

```bash
# Make the setup script executable
chmod +x docker-setup.sh

# Run the setup script
./docker-setup.sh
```

This script will:
- Create the necessary .env file
- Start a MySQL container
- Configure the database for the application

#### Option 2: Local MySQL Installation

Make sure MySQL is installed and running on your system.

```bash
# Create a new database
mysql -u root -p -e "CREATE DATABASE palona_shop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 4. Configure Environment Variables

If you're using Docker, the setup script creates this file automatically.
Otherwise, create a `.env` file in the backend directory:

```
# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=palona_shop
```

### 5. Initialize the Database

```bash
# Navigate to the src directory
cd src

# Run the database initialization script
python db_init.py
```

### 6. Set up the frontend

```bash
# Navigate to the frontend directory
cd ../../frontend

# Install dependencies
npm install
```

## Running the Application

### 1. Start the backend server

```bash
# From the backend directory, with the virtual environment activated
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
cd src
python main.py
```

The backend server will start at http://localhost:5001.

### 2. Start the frontend development server

```bash
# From the frontend directory
cd frontend
npm start
```

The frontend will be available at http://localhost:3000.

## API Endpoints

- `/api/health` - Health check endpoint
- `/api/chat` - Chat with the AI assistant
- `/api/recommend` - Get product recommendations
- `/api/search_by_image` - Search for products by image
- `/api/products` - Get all products
- `/api/products/:id` - Get a specific product
- `/api/categories/:id/products` - Get products by category
- `/api/images/:filename` - Get product images
- `/api/init-db` - Initialize the database (admin access only)

## Docker MySQL Management

### Accessing the MySQL Container

```bash
# Connect to the MySQL instance
docker exec -it palona-mysql mysql -upalona -ppalonapassword

# Select the database
USE palona_shop;
```

### Stopping the MySQL Container

```bash
docker-compose down
```

### Restart the MySQL Container

```bash
docker-compose up -d
```

## Troubleshooting

### Database Connection Issues

If you encounter database connection issues:

1. If using Docker:
   - Check if the container is running: `docker ps`
   - Restart the container: `docker-compose restart mysql`
   - Check logs: `docker logs palona-mysql`

2. If using local MySQL:
   - Verify that MySQL is running: `systemctl status mysql` or `mysql.server status`
   - Check the connection details in the `.env` file
   - Make sure the database exists: `mysql -u root -p -e "SHOW DATABASES;"`
   - Verify that the user has appropriate permissions

### OpenAI API Issues

If OpenAI API calls fail:

1. Verify your API key in the `.env` file
2. Check that you have sufficient credits on your OpenAI account
3. The application will fall back to a file-based catalog if OpenAI is unavailable

## License

[MIT License](LICENSE)

