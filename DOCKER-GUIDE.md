# Docker Setup Guide for Palona AI Shop

This guide explains how to use Docker to set up and run the Palona AI Shop application, including MySQL database.

## Prerequisites

- Docker
- Docker Compose

## Quick Start

For the quickest setup, just run:

```bash
./start-app.sh
```

This script will:
1. Set up the environment files if they don't exist
2. Start all Docker containers (MySQL and backend)
3. Ask if you want to initialize the database
4. Provide instructions for running the frontend

## Manual Setup

### 1. Database Setup

To set up only the MySQL database:

```bash
./docker-setup.sh
```

This script will:
- Create necessary environment files
- Start a MySQL container
- Configure the database for the application

### 2. Database Initialization

To initialize the database schema and add sample data:

```bash
./docker-init-db.sh
```

This script will prompt you to choose between:
- Using the Python script (recommended)
- Using SQL files directly

#### Alternative Database Initialization Methods

You can also initialize the database directly using:

1. **Direct SQL execution**:
```bash
# Run schema creation
docker exec -i palona-mysql mysql -upalona -ppalonapassword palona_shop < backend/db/init/schema.sql

# Run sample data insertion
docker exec -i palona-mysql mysql -upalona -ppalonapassword palona_shop < backend/db/init/sample_data.sql
```

2. **Using the dedicated shell script**:
```bash
backend/db/init/init_mysql.sh
```

3. **Using the Python script**:
```bash
python backend/db/init/init_db.py
```

### 3. Starting Individual Components

**Start MySQL only:**
```bash
docker-compose up -d mysql
```

**Start Backend only:**
```bash
docker-compose up -d backend
```

**Start All Services:**
```bash
docker-compose up -d
```

## Container Management

### Check Running Containers

```bash
docker ps
```

### View Container Logs

```bash
# For MySQL
docker logs palona-mysql

# For Backend
docker logs palona-backend
```

### Accessing MySQL

```bash
docker exec -it palona-mysql mysql -upalona -ppalonapassword palona_shop
```

### Stopping Containers

```bash
# Stop and remove all containers
docker-compose down

# Stop and remove containers and volumes (deletes data)
docker-compose down -v
```

## Directory Structure

The project now uses the following structure for database initialization:

```
backend/
├── db/
│   └── init/
│       ├── init_db.py        # Python script for database initialization
│       ├── init_mysql.sh     # Shell script for direct SQL initialization
│       ├── schema.sql        # SQL schema definition
│       └── sample_data.sql   # Sample data for testing
├── src/
│   ├── database.py           # Database connectivity and operations
│   └── ...
└── ...
```

## Environment Configuration

The Docker setup uses these default values:

- **Database Name**: palona_shop
- **Database User**: palona
- **Database Password**: palonapassword
- **Backend API Port**: 5001
- **MySQL Port**: 3306

To change these values, edit:
- `docker-compose.yml` 
- `backend/.env` (created by setup script)

## Troubleshooting

### Common Issues

1. **MySQL container fails to start**
   - Check logs: `docker logs palona-mysql`
   - Ensure port 3306 is available: `lsof -i :3306`

2. **Backend can't connect to MySQL**
   - Ensure MySQL container is running: `docker ps | grep mysql`
   - Check that backend uses correct hostname: in `docker-compose.yml` the DB_HOST should be "mysql" (container name)
   - For local development, DB_HOST should be "localhost"

3. **Changes to backend code not reflected**
   - Rebuild the container: `docker-compose build backend`
   - Restart the service: `docker-compose restart backend`
   
4. **Database initialization fails**
   - Check MySQL container logs: `docker logs palona-mysql`
   - Verify the SQL files in `backend/db/init/` are correctly formatted
   - Try running initialization manually with one of the alternative methods 