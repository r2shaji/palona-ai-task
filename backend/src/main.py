# backend/src/main.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS  # Make sure you have flask-cors installed
from dotenv import load_dotenv
import os
from flask import Flask, Response, abort
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client('s3')           # picks up the EC2 role for creds
BUCKET = 'danieldoescode-s3'
PREFIX = 'palona/data/'

# Load environment variables 
load_dotenv()

# Import agent logic and database functions
from agent import CommerceAgent
from database import get_all_products, get_product_by_id, get_products_by_category

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, 
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "Access-Control-Allow-Credentials"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]) # Enable CORS for all routes

# Initialize the agent 
agent = CommerceAgent()

# Simple health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    # Check that OpenAI key is available
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        return jsonify({
            'status': 'warning',
            'message': 'OpenAI API key not found in environment variables.'
        }), 200
    
    return jsonify({
        'status': 'ok',
        'message': 'Server is running',
        'openai_key_available': bool(openai_key)
    }), 200

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'Invalid request. Message is required.'}), 400
    
    try:
        user_message = data['message']
        response = agent.chat(user_message)
        
        return jsonify(response)
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/recommend', methods=['POST'])
def handle_recommendation():
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Invalid request. Query is required.'}), 400
    
    query = data['query']
    recommendations = agent.recommend_products(query)
    
    return jsonify({'recommendations': recommendations})

@app.route('/api/search_by_image', methods=['POST'])
def handle_image_search():
    # Check if image file is present in the request
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided.'}), 400
    
    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({'error': 'Empty image file.'}), 400
    
    # Process the image and search for similar products
    results = agent.search_by_image(image_file)
    
    return jsonify({'results': results})

# @app.route('/api/images/<filename>', methods=['GET'])
# def serve_product_image(filename):
#     # Define the path to the product images
#     product_data_dir = os.path.join(os.path.dirname(__file__), "data")
#     return send_from_directory(product_data_dir, filename)

@app.route('/api/products', methods=['GET'])
def get_products():
    # Return a list of all products 
    try:
        # Try to get products from the database first
        products = get_all_products()
        if products:
            return jsonify({'products': products})
    except Exception as e:
        print(f"Database error, falling back to agent: {e}")
    
    # Fall back to the agent's products if database fails
    products = agent.get_all_products()
    return jsonify({'products': products})

@app.route('/api/products/<product_id>', methods=['GET'])
def get_product(product_id):
    # Return a specific product by ID
    try:
        # Try to get the product from the database
        product = get_product_by_id(product_id)
        if product:
            return jsonify(product)
    except Exception as e:
        print(f"Database error: {e}")
    
    # Return 404 if not found
    return jsonify({'error': f'Product with ID {product_id} not found'}), 404

@app.route('/api/categories/<category_id>/products', methods=['GET'])
def get_category_products(category_id):
    # Return products in a specific category
    try:
        # Convert to int as it comes from URL as a string
        category_id = int(category_id) 
        products = get_products_by_category(category_id)
        return jsonify({'products': products})
    except ValueError:
        return jsonify({'error': 'Invalid category ID'}), 400
    except Exception as e:
        print(f"Error getting category products: {e}")
        return jsonify({'error': str(e)}), 500
    

@app.route('/api/images/<filename>')
def get_asset(filename):
    key = f'{PREFIX}{filename}'
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return Response(
            obj['Body'].iter_chunks(8192),
            content_type=obj['ContentType']
        )
    except ClientError as e:
        code = e.response['Error']['Code']
        if code in ('NoSuchKey', '404'):
            return jsonify({'error': str(e)}), 404
        else:
            print(f"S3 error: {e}")
            return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
