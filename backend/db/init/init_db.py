#!/usr/bin/env python3
import os
import sys

# Add the parent directory to sys.path to make imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import from the src folder
from src.database import init_db, insert_sample_data

def main():
    print("Initializing database schema...")
    schema_created = init_db()
    print(f"Schema created: {schema_created}")

    if schema_created:
        print("Inserting sample data...")
        data_inserted = insert_sample_data()
        print(f"Sample data inserted: {data_inserted}")
        
        if data_inserted:
            print("Database initialization completed successfully!")
            return True
        else:
            print("Failed to insert sample data.")
            return False
    else:
        print("Failed to create database schema.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 