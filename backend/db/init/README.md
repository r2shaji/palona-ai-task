# Database Initialization

This directory contains scripts and SQL files for initializing the MySQL database for the Palona AI Shop application.

## Files

- `init_db.py` - Python script that uses the application's database module to initialize the schema and insert sample data
- `init_mysql.sh` - Shell script that directly executes SQL files to initialize the database
- `schema.sql` - SQL file containing the database schema creation commands
- `sample_data.sql` - SQL file containing sample data insertion commands

## Usage

### Using SQL Files Directly

```bash
./init_mysql.sh
```

This script will detect if you're using Docker or a local MySQL instance and run the appropriate commands.

### Manual SQL Execution

For Docker:
```bash
docker exec -i palona-mysql mysql -upalona -ppalonapassword palona_shop < schema.sql
docker exec -i palona-mysql mysql -upalona -ppalonapassword palona_shop < sample_data.sql
```

For local MySQL:
```bash
mysql -upalona -ppalonapassword palona_shop < schema.sql
mysql -upalona -ppalonapassword palona_shop < sample_data.sql
```

## Notes

- The schema always drops tables before creating them, so running these scripts will reset any existing data
- The sample data provides a basic set of products, categories, and brands for testing
- When the MySQL Docker container starts for the first time, it automatically executes SQL files from /docker-entrypoint-initdb.d, initializing the database 