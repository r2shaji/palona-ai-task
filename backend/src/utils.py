# backend/src/utils.py
import os

def format_product_for_response(product):
    """Formats a product object for API response."""
    # Create a copy to avoid modifying the original
    formatted = product.copy()
    
    # Convert file paths to relative URLs for frontend
    if 'image_path' in formatted:
        # Replace absolute path with relative URL
        formatted['image_url'] = f"/images/{formatted['image_filename']}"
        # Remove server-side path information
        del formatted['image_path']
    
    return formatted
