# backend/src/database.py
import os
import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "palona_shop")

# Create database URL
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create engine
engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

def get_db():
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_product_by_id(product_id):
    """Get a product by its ID."""
    try:
        with engine.connect() as connection:
            query = text("""
            SELECT p.*, b.name as brand_name 
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.brand_id
            WHERE p.product_id = :product_id
            """)
            result = connection.execute(query, {"product_id": product_id}).fetchone()
            
            if result:
                # Convert to dict
                product = dict(result._mapping)
                
                # Get categories
                categories_query = text("""
                SELECT c.* FROM categories c
                JOIN product_categories pc ON c.category_id = pc.category_id
                WHERE pc.product_id = :product_id
                """)
                categories = connection.execute(categories_query, {"product_id": product_id}).fetchall()
                product['categories'] = [dict(category._mapping) for category in categories]
                
                return product
            return None
    except Exception as e:
        print(f"Error getting product by ID: {e}")
        return None

def get_all_products():
    """Get all products."""
    try:
        with engine.connect() as connection:
            query = text("""
            SELECT p.*, b.name as brand_name 
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.brand_id
            WHERE p.is_active = TRUE
            ORDER BY p.average_rating DESC
            """)
            results = connection.execute(query).fetchall()
            
            products = []
            for row in results:
                product = dict(row._mapping)
                
                # Get categories
                categories_query = text("""
                SELECT c.* FROM categories c
                JOIN product_categories pc ON c.category_id = pc.category_id
                WHERE pc.product_id = :product_id
                """)
                categories = connection.execute(categories_query, {"product_id": product['product_id']}).fetchall()
                product['categories'] = [dict(category._mapping) for category in categories]
                
                products.append(product)
                
            return products
    except Exception as e:
        print(f"Error getting all products: {e}")
        return []

def get_products_by_category(category_name):
    """Get products by category name using a single query."""
    try:
        with engine.connect() as connection:
            # Single query to get products by category name with JOIN
            query = text("""
            SELECT p.*, b.name as brand_name, c.category_id, c.name as category_name
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.brand_id
            JOIN product_categories pc ON p.product_id = pc.product_id
            JOIN categories c ON pc.category_id = c.category_id
            WHERE c.name = :category_name AND p.is_active = TRUE
            ORDER BY p.average_rating DESC
            """)
            results = connection.execute(query, {"category_name": category_name}).fetchall()
            
            if not results:
                print(f"No products found in category: {category_name}")
                return []
                
            # Process results and group by product_id
            product_map = {}
            for row in results:
                row_dict = dict(row._mapping)
                product_id = row_dict['product_id']
                
                if product_id not in product_map:
                    # Create new product entry
                    product = {
                        'product_id': product_id,
                        'name': row_dict['name'],
                        'description': row_dict['description'],
                        'price': row_dict['price'],
                        'image_url': row_dict['image_url'],
                        'average_rating': row_dict['average_rating'],
                        'is_active': row_dict['is_active'],
                        'brand_name': row_dict['brand_name'],
                        'categories': [{
                            'category_id': row_dict['category_id'],
                            'name': row_dict['category_name']
                        }]
                    }
                    product_map[product_id] = product
                else:
                    # Add category to existing product
                    product_map[product_id]['categories'].append({
                        'category_id': row_dict['category_id'],
                        'name': row_dict['category_name']
                    })
            
            print(f"Found {len(product_map)} products in category '{category_name}'")
            return list(product_map.values())
            
    except Exception as e:
        print(f"Error getting products by category: {e}")
        return []

def search_products_by_description(description, category_name=None, limit=5):
    """Search products by description keywords and optionally filter by category.
    
    Args:
        description (str): Keywords or phrases to search for in product descriptions
        category_name (str, optional): Category name to filter results
        limit (int, optional): Maximum number of results to return
        
    Returns:
        List of product dictionaries matching the search criteria
    """
    try:
        # Split description into keywords for better matching
        keywords = description.lower().split()
        if not keywords:
            print("No keywords provided for search")
            return []
            
        print(f"Searching for products with keywords: {keywords}")
            
        with engine.connect() as connection:
            # Base query - start with the common parts
            query_parts = [
                "SELECT p.*, b.name as brand_name, c.category_id, c.name as category_name",
                "FROM products p",
                "LEFT JOIN brands b ON p.brand_id = b.brand_id",
                "JOIN product_categories pc ON p.product_id = pc.product_id",
                "JOIN categories c ON pc.category_id = c.category_id",
                "WHERE p.is_active = TRUE"
            ]
            
            # Add category filter if provided
            params = {}
            if category_name:
                query_parts.append("AND c.name = :category_name")
                params["category_name"] = category_name
                
            # Add description search criteria - create individual clauses for each keyword
            description_conditions = []
            
            for i, keyword in enumerate(keywords):
                # Skip very short keywords (less than 3 chars) unless they're likely a color
                if len(keyword) < 3 and keyword not in ["red", "tan", "black", "blue"]:
                    continue
                    
                # Clean up the keyword - remove any special characters
                keyword = ''.join(c for c in keyword if c.isalnum())
                if not keyword:
                    continue
                    
                keyword_param = f"keyword_{i}"
                # Search in both name and description
                description_conditions.append(
                    f"(LOWER(p.description) LIKE :{keyword_param} OR LOWER(p.name) LIKE :{keyword_param})"
                )
                params[keyword_param] = f"%{keyword}%"
                
            if description_conditions:
                # Use AND between conditions to require matching all keywords
                query_parts.append("AND " + " AND ".join(description_conditions))
                
            # Add sorting and limit
            query_parts.append("ORDER BY p.average_rating DESC")
            query_parts.append("LIMIT :limit")
            params["limit"] = limit
            
            # Combine all parts into a complete query
            query_text = " ".join(query_parts)
            print(f"Search query: {query_text}")
            print(f"Search params: {params}")
            
            query = text(query_text)
            
            # Execute the query
            results = connection.execute(query, params).fetchall()
            
            if not results:
                print(f"No products found matching description: {description}" + 
                     (f" in category: {category_name}" if category_name else ""))
                return []
                
            # Process results and group by product_id
            product_map = {}
            for row in results:
                row_dict = dict(row._mapping)
                product_id = row_dict['product_id']
                
                if product_id not in product_map:
                    # Create new product entry
                    product = {
                        'product_id': product_id,
                        'name': row_dict['name'],
                        'description': row_dict['description'],
                        'price': row_dict['price'],
                        'image_url': row_dict['image_url'],
                        'average_rating': row_dict['average_rating'],
                        'is_active': row_dict['is_active'],
                        'brand_name': row_dict['brand_name'],
                        'categories': [{
                            'category_id': row_dict['category_id'],
                            'name': row_dict['category_name']
                        }]
                    }
                    product_map[product_id] = product
                else:
                    # Add category to existing product
                    product_map[product_id]['categories'].append({
                        'category_id': row_dict['category_id'],
                        'name': row_dict['category_name']
                    })
            
            print(f"Found {len(product_map)} products matching description: {description}" + 
                 (f" in category: {category_name}" if category_name else ""))
            return list(product_map.values())
            
    except Exception as e:
        print(f"Error searching products by description: {e}")
        return []