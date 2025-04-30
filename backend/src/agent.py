# backend/src/agent.py
import os
import openai
from dotenv import load_dotenv
from PIL import Image
import numpy as np
import faiss
import time
from sqlalchemy import text

from models import load_clip_model, extract_features_clip
from utils import format_product_for_response
from database import get_all_products, get_product_by_id, get_products_by_category, search_products_by_description, engine

load_dotenv()

# --- OpenAI Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY not found in environment variables.")
else:
    openai.api_key = OPENAI_API_KEY

# --- OpenAI Model Configuration ---
OPENAI_MODEL = "gpt-4"
SYSTEM_PROMPT = """
You are Palona, a helpful and friendly AI assistant for a commerce website specializing in apparel.

Your responses should be:
1. Well-structured with clear formatting, using bullet points or numbered lists when appropriate
2. Concise and direct, avoiding unnecessary text
3. Helpful and focused on providing accurate information about products

You can help with:
• Recommending products based on customer preferences and descriptions
• Searching for products similar to images provided by customers

Always maintain a friendly, professional tone and prioritize clear, structured responses. Provide the recommendations based on our website's catalog. Do not provide outside links.

IMPORTANT: When users ask you to show or recommend products, do NOT make up product descriptions. Instead, explain that you're searching our product catalog, and then let the system handle finding and displaying actual products from our database.
"""

# --- Product Data Setup ---
PRODUCT_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PRODUCT_CATALOG = []


# --- Image Feature Index (using CLIP) ---
image_feature_index = None
product_id_map = {}
CLIP_FEATURE_DIMENSION = 768  

def build_image_index():
    """Builds the FAISS index for image features using CLIP."""
    global image_feature_index, product_id_map
    
    if not PRODUCT_CATALOG:
        print("Cannot build image index: Product catalog is empty.")
        return

    print("Building image index with CLIP features...")
    start_time = time.time()
    
    # Ensure CLIP model is loaded
    model, processor = load_clip_model()
    if model is None or processor is None:
        print("Cannot build image index: Failed to load CLIP model.")
        return

    features = []
    product_ids = []
    
    for product in PRODUCT_CATALOG:
        try:
            img = Image.open(product["image_path"])
            feature = extract_features_clip(img) # Use the function from models.py
            if feature is not None:
                features.append(feature)
                product_ids.append(product["id"])
            else:
                print(f"Warning: Could not extract features for {product['image_filename']}")
        except Exception as e:
            print(f"Error processing image {product['image_filename']}: {e}")

    if not features:
        print("Cannot build image index: No features were extracted.")
        return

    # Convert features to a numpy array
    features_np = np.array(features).astype("float32")
    
    # Check the actual dimension of the features
    actual_dimension = features_np.shape[1]
    print(f"Actual feature dimension: {actual_dimension}")
    
    # Build FAISS index with the actual dimension
    image_feature_index = faiss.IndexFlatL2(actual_dimension)
    image_feature_index.add(features_np)
    product_id_map = {i: pid for i, pid in enumerate(product_ids)}
    
    end_time = time.time()
    print(f"Image index built successfully with {len(product_ids)} items in {end_time - start_time:.2f} seconds.")

class CommerceAgent:
    def __init__(self):
        self.openai_available = bool(OPENAI_API_KEY)
        if not self.openai_available:
            print("OpenAI API key not set. Chat functionality will be limited.")
        
        # Try to get products from the database
        self.use_database = False
        try:
            db_products = get_all_products()
            if db_products:
                print(f"Using MySQL database for product data. Found {len(db_products)} products.")
                self.use_database = True
        except Exception as e:
            print(f"Failed to connect to database: {e}")
            print("Falling back to file-based product catalog.")

    def chat(self, user_message):
        """Handles general conversation and product recommendations using OpenAI."""
        # Extract intent from user message
        intent = self._analyze_intent(user_message)
        print(f"Detected intent: {intent} for message: '{user_message}'")
        
        # If recommendation intent, return products with a brief intro
        if intent == "recommendation":
            # Extract category and description
            category, description = self._extract_product_type(user_message)
            print(f"Extracted category: {category}, Description: {description}")
            
            # Generate educational response with OpenAI first
            intro_text = self._get_ai_response(user_message)
            print(f"Generated AI response: {intro_text}")
            
            # For best-selling products query or if no specific category, use the original message
            if "best" in user_message.lower() or "popular" in user_message.lower() or not category:
                recommendations = self.recommend_products(user_message)
            else:
                # Pass the full message to ensure description is used
                recommendations = self.recommend_products(user_message)
            
            # Always return recommendations - if none found, the recommend_products method
            # should fall back to popular items
            return {
                "text": intro_text,
                "is_recommendation": True,
                "recommendations": recommendations
            }
        else:
            # For general conversation, get AI response
            ai_response = self._get_ai_response(user_message)
            return {
                "text": ai_response,
                "is_recommendation": False
            }

    def _analyze_intent(self, message):
        """Determine the intent of the user's message."""
        # List of keywords that strongly indicate a product search/recommendation intent
        recommendation_keywords = [
            "show me", "find", "looking for", "search", "recommend", 
            "suggest", "best", "top", "similar", "popular", "trending",
            "where can i get", "display", "list", "best-selling",
            "bestseller", "hot items", "featured"
        ]
        
        # List of keywords that indicate general questions
        general_question_indicators = [
            "what are you", "who are you", "how do you", "what can you",
            "help me understand", "explain how you", "tell me about you", 
            "what is your purpose", "why were you", "how were you", 
            "where are you", "policy", "contact", "support", "customer service"
        ]
        
        message_lower = message.lower()
        
        # First check for keywords that definitely indicate product request
        for keyword in recommendation_keywords:
            if keyword in message_lower:
                print(f"Product recommendation intent detected: '{keyword}' found in '{message_lower}'")
                return "recommendation"
        
        # Then check for general question indicators
        for indicator in general_question_indicators:
            if indicator in message_lower:
                print(f"Conversation intent detected: '{indicator}' found in '{message_lower}'")
                return "conversation"
        
        # If the message contains product-related terms, consider it a recommendation intent
        category, _ = self._extract_product_type(message)
        if category:
            print(f"Product recommendation intent inferred from product type: '{category}'")
            return "recommendation"
        
        # If no clear intent is detected, default to conversation
        print(f"No clear intent detected in: '{message_lower}', defaulting to conversation")
        return "conversation"

    def _get_ai_response(self, user_message):
        """Generate a response to user messages using OpenAI."""
        if not self.openai_available:
            return "I'm sorry, but the AI chat service is currently unavailable. Please try again later."
        
        try:
            # Determine if this is a product recommendation query
            is_recommendation = self._analyze_intent(user_message) == "recommendation"
            
            if is_recommendation:
                # For product recommendation queries, first provide helpful information then transition to recommendations
                prompt = f"""
                The user has asked: "{user_message}"
                
                You are Palona, a shopping assistant for an online clothing store. The user's question appears to be requesting 
                product recommendations or information about clothing items.
                
                Please provide a helpful, informative response that:
                
                1. Actually answers the user's specific question or provides educational information related to their query
                2. Includes 2-3 sentences of helpful, factual information relevant to what they're asking about 
                   (like explaining fabric types, clothing care, style advice, seasonal considerations, etc.)
                3. Ends with a brief transition indicating you'll show some relevant products
                
                Make your response natural and conversational. Focus on being genuinely helpful by providing 
                real educational content related to their specific query.
                
                IMPORTANT: DO NOT make up or mention specific products, prices, or inventory items.
                Our system will automatically display relevant products after your response.
                
                Keep your entire response under 5 sentences.
                """
                
                response = openai.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=250
                )
            else:
                # For general conversation, proceed normally
                response = openai.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_message}
                    ],
                    temperature=0.7,
                    max_tokens=250
                )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error during OpenAI conversation: {e}")
            return "I'm sorry, but I encountered an error while processing your message. Please try again."

    def _extract_product_type(self, message):
        """Extract the product type and description from a user message."""
        # Define the mapping of product types to category names
        type_to_category = {
            "t-shirt": "T-Shirts", 
            "tshirt": "T-Shirts", 
            "t shirt": "T-Shirts", 
            "t-shirts": "T-Shirts",
            "t shirts": "T-Shirts",
            "tshirts": "T-Shirts", 
            "shirt": "T-Shirts", 
            "shirts": "T-Shirts", 
            "tee": "T-Shirts", 
            "tees": "T-Shirts", 
            "teeshirt": "T-Shirts",
            "teeshirts": "T-Shirts",
            "jean": "Pants", 
            "jeans": "Pants", 
            "pant": "Pants", 
            "pants": "Pants",
            "trouser": "Pants",
            "trousers": "Pants",
            "jacket": "Jackets", 
            "jackets": "Jackets", 
            "coat": "Jackets",
            "coats": "Jackets",
            "skirt": "Skirts", 
            "skirts": "Skirts"
        }
        
        if not self.openai_available:
            # Simple extraction based on message content
            message_lower = message.lower()
            
            # Check for product types in the message
            for product_type, category in type_to_category.items():
                if product_type in message_lower:
                    print(f"Detected product type '{product_type}' mapping to category '{category}'")
                    # Return category name with no description when OpenAI is not available
                    return category, None
            
            # If no specific product type is found
            return None, None
        
        try:
            # Use OpenAI to extract the product type and description
            prompt = f"""
            Extract the main product type or category from this query: "{message}"
            Focus on identifying clothing items like t-shirts, pants, skirts, etc.
            If the query mentions "tee", "teeshirt" or similar, identify it as "T-Shirts".
            If the query mentions pants, jeans or trousers, identify it as "Pants".
            If the query mentions skirt, identify it as "Skirts".
            If the query mentions jacket or coat, identify it as "Jackets".
            If no specific product type is mentioned, return "none".
            Return the category exactly as specified above (with correct capitalization).
            
            Example inputs and outputs:
            "Show me some t-shirts" -> "T-Shirts"
            "I want black pants" -> "Pants"
            "Looking for a warm skirt" -> "Skirts"
            "What's new in your store?" -> "none"
            """
            
            response = openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts product categories from search queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=50
            )
            
            category = response.choices[0].message.content.strip()
            print(f"OpenAI extracted category: {category}")
            
            # Normalize the category if needed
            category_lower = category.lower()
            normalized_category = None
            
            # First try exact matches in our mapping
            for product_type, category_value in type_to_category.items():
                if product_type == category_lower:
                    normalized_category = category_value
                    print(f"Exact match: '{product_type}' -> '{normalized_category}'")
                    break
            
            # If no exact match, try partial matches
            if not normalized_category:
                for product_type, category_value in type_to_category.items():
                    if product_type in category_lower or category_lower in product_type:
                        normalized_category = category_value
                        print(f"Partial match: '{product_type}' in '{category_lower}' -> '{normalized_category}'")
                        break
            
            # If we found a normalized category, use it
            if normalized_category:
                category = normalized_category
            
            # Extract description separately
            description_prompt = f"""
            Analyze this query and extract any descriptive terms about the product: "{message}"
            Focus on attributes like color, material, style, occasion, season, etc.
            If no descriptive terms are found, return "none".
            Return ONLY the descriptive terms as simple words or short phrases, no sentences or explanations.
            Do not include the product type itself in the description.
            
            Example inputs and outputs:
            "Show me some t-shirts" -> "none"
            "I want black pants" -> "black"
            "Looking for a warm jacket for winter" -> "warm, winter"
            "Show me more black pants" -> "black"
            "Soft cotton shirts for summer" -> "soft, cotton, summer"
            """
            
            description_response = openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts product attributes from search queries."},
                    {"role": "user", "content": description_prompt}
                ],
                temperature=0.3,
                max_tokens=50
            )
            
            description = description_response.choices[0].message.content.strip().lower()
            if description == "none":
                description = None
            
            # Additional processing to extract just key descriptive terms
            if description and len(description) > 30:  # If description is too long, it's likely not just attributes
                # Try to extract just the key descriptive terms by looking for common attributes
                colors = ["black", "white", "blue", "red", "green", "yellow", "purple", "pink", "orange", 
                          "brown", "gray", "grey", "beige", "navy", "teal", "maroon", "olive"]
                materials = ["cotton", "wool", "linen", "silk", "denim", "leather", "synthetic", "polyester", 
                             "nylon", "spandex", "fleece", "velvet", "cashmere"]
                styles = ["casual", "formal", "business", "elegant", "vintage", "modern", "classic", "sporty",
                          "athletic", "loose", "tight", "fitted", "baggy", "relaxed", "slim"]
                
                # Extract words that match known attributes
                key_terms = []
                desc_words = description.lower().split()
                for word in desc_words:
                    if word in colors or word in materials or word in styles:
                        key_terms.append(word)
                
                # If we found key terms, use only those
                if key_terms:
                    description = ", ".join(key_terms)
                    print(f"Simplified description to key terms: {description}")
            
            print(f"OpenAI extracted description: {description}")
            
            # If OpenAI returns "none" or similar, return None
            if category.lower() in ["none", "no product", "not found", "n/a"]:
                return None, description
                
            print(f"Final category: {category}, Description: {description}")
            return category, description
            
        except Exception as e:
            print(f"Error during product type extraction: {e}")
            # Fall back to simple keyword matching
            message_lower = message.lower()
            
            # Check for product types in the message
            for product_type, category in type_to_category.items():
                if product_type in message_lower:
                    print(f"Fallback detection: '{product_type}' -> '{category}'")
                    return category, None
                    
            return None, None  # Return None on errors

    def recommend_products(self, query):
        """Recommends products based on a text query using OpenAI for better understanding."""
        print(f"Received recommendation query: {query}")
        
        # Check if using database and OpenAI is available
        if self.use_database and self.openai_available:
            try:
                # Use OpenAI to understand the query intent and recommend appropriate products
                analysis_prompt = f"""
                Analyze this shopping query: "{query}"
                
                Determine:
                1. What type of query is this? (direct product search, complementary item search, outfit recommendation, etc.)
                2. What product categories should be recommended?
                
                For example:
                - "Show me t-shirts" = direct search for T-Shirts category
                - "What goes with these pants?" = complementary search, recommend T-Shirts and Jackets
                - "I need a whole outfit" = outfit recommendation, suggest multiple categories
                
                Format your response EXACTLY as a valid JSON object with these fields:
                {{
                  "query_type": "direct_search | complementary_search | outfit_recommendation",
                  "primary_category": "Category to search for if direct search",
                  "complementary_categories": ["Category1", "Category2"] (if complementary search)
                }}
                
                Only use these exact category names: "T-Shirts", "Pants", "Skirts", "Jackets"
                
                IMPORTANT: Return ONLY the JSON object, nothing else.
                """
                
                # Get analysis from OpenAI
                response = openai.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a helpful fashion assistant that outputs valid JSON."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=150
                )
                
                # Parse the response
                try:
                    content = response.choices[0].message.content.strip()
                    print(f"OpenAI analysis: {content}")
                    import json
                    import re
                    
                    # Try to extract JSON from the response if it's not already pure JSON
                    json_match = re.search(r'({.*})', content, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                        try:
                            result = json.loads(json_str)
                        except json.JSONDecodeError:
                            # Try cleaning the string further
                            print("Initial JSON parsing failed, trying to clean the string")
                            cleaned_str = json_str.replace("'", '"')  # Replace single quotes with double quotes
                            result = json.loads(cleaned_str)
                    else:
                        # If no JSON pattern found, try loading the entire content
                        result = json.loads(content)
                    
                    print(f"Parsed result: {result}")
                    
                    query_type = result.get("query_type", "direct_search")
                    primary_category = result.get("primary_category")
                    complementary_categories = result.get("complementary_categories", [])
                    
                    print(f"Query type: {query_type}")
                    print(f"Primary category: {primary_category}")
                    print(f"Complementary categories: {complementary_categories}")
                    
                    # Handle different query types
                    if query_type == "complementary_search" and complementary_categories:
                        # Get products from complementary categories
                        all_complementary_products = []
                        
                        for category in complementary_categories:
                            # Ensure category is valid
                            if not category or not isinstance(category, str):
                                continue
                                
                            print(f"Searching for complementary products in category: {category}")
                            category_products = get_products_by_category(category)
                            
                            if category_products:
                                # Format products for response
                                for product in category_products:
                                    formatted_product = {
                                        "id": product['product_id'],
                                        "name": product['name'],
                                        "description": product['description'],
                                        "price": float(product['price']),
                                        "image_filename": product['image_url'].split('/')[-1] if product['image_url'] else None,
                                        "image_url": product['image_url'],
                                        "rating": float(product['average_rating']),
                                        "category": product['categories'][0]['name'] if product['categories'] else "Unknown"
                                    }
                                    all_complementary_products.append(formatted_product)
                        
                        if all_complementary_products:
                            # Sort by rating for best results
                            all_complementary_products.sort(key=lambda p: float(p.get('rating', 0)), reverse=True)
                            print(f"Found {len(all_complementary_products)} complementary products")
                            return all_complementary_products[:5]
                    
                    # For direct search or if complementary search fails, use primary category
                    if primary_category:
                        print(f"Using primary category: {primary_category}")
                        category_products = get_products_by_category(primary_category)
                        
                        if category_products:
                            # Format products for response
                            formatted_products = []
                            for product in category_products:
                                formatted_product = {
                                    "id": product['product_id'],
                                    "name": product['name'],
                                    "description": product['description'],
                                    "price": float(product['price']),
                                    "image_filename": product['image_url'].split('/')[-1] if product['image_url'] else None,
                                    "image_url": product['image_url'],
                                    "rating": float(product['average_rating']),
                                    "category": product['categories'][0]['name'] if product['categories'] else "Unknown"
                                }
                                formatted_products.append(formatted_product)
                            
                            print(f"Found {len(formatted_products)} products in primary category '{primary_category}'")
                            
                            # Sort by rating for best results
                            sorted_products = sorted(formatted_products, key=lambda p: float(p.get('rating', 0)), reverse=True)
                            return sorted_products[:5]
                
                except Exception as e:
                    print(f"Error processing OpenAI analysis: {e}")
                    # Continue with standard processing below
            
            except Exception as e:
                print(f"Error during intelligent recommendation: {e}")
                # Continue with standard processing below
        
        # Standard processing (fallback if OpenAI analysis fails or is not available)
        # Extract category and description from query
        category, description = self._extract_product_type(query)
        print(f"Starting product search with category: {category}, description: {description}")
        
        # Check if using database
        if self.use_database:
            try:
                # If we have a category from the extraction
                if category:
                    print(f"Using category: {category}")
                    
                    # If we have a description from the extraction, use it to search
                    if description and len(description) > 2:
                        print(f"Using extracted description for search: '{description}' in category '{category}'")
                        description_results = search_products_by_description(description, category)
                        
                        if description_results:
                            # Format products for response
                            formatted_results = []
                            for product in description_results:
                                formatted_product = {
                                    "id": product['product_id'],
                                    "name": product['name'],
                                    "description": product['description'],
                                    "price": float(product['price']),
                                    "image_filename": product['image_url'].split('/')[-1] if product['image_url'] else None,
                                    "image_url": product['image_url'],
                                    "rating": float(product['average_rating']),
                                    "category": product['categories'][0]['name'] if product['categories'] else "Unknown"
                                }
                                formatted_results.append(formatted_product)
                            
                            print(f"Found {len(formatted_results)} products matching description in category '{category}'")
                            return formatted_results[:5]
                
                    # If no results from description search or no description available,
                    # query products directly by category
                    print(f"Querying products directly by category: {category}")
                    filtered_products = get_products_by_category(category)
                    
                    # Format products for response
                    formatted_products = []
                    for product in filtered_products:
                        formatted_product = {
                            "id": product['product_id'],
                            "name": product['name'],
                            "description": product['description'],
                            "price": float(product['price']),
                            "image_filename": product['image_url'].split('/')[-1] if product['image_url'] else None,
                            "image_url": product['image_url'],
                            "rating": float(product['average_rating']),
                            "category": product['categories'][0]['name'] if product['categories'] else "Unknown"
                        }
                        formatted_products.append(formatted_product)
                    filtered_products = formatted_products
                    print(f"Found {len(filtered_products)} products in category '{category}'")
                    
                    # For best-selling or popular queries, sort by rating within the already filtered products
                    if query and any(term in query.lower() for term in ["best-selling", "bestselling", "popular", "top", "comfortable", "best", "what"]):
                        print("Getting best products by rating from filtered results")
                        
                        # Sort filtered products by rating and return top 5
                        sorted_products = sorted(filtered_products, key=lambda p: float(p.get('rating', 0)), reverse=True)
                        return sorted_products[:5]
                
                # Return the already filtered products if any are found
                if filtered_products and len(filtered_products) > 0:
                    return filtered_products[:5]
            
            except Exception as e:
                print(f"Error performing database product search: {e}")
                print("Falling back to file-based product search")
                # Fall back to file-based implementation
                pass
        
        # File-based implementation from here (existing code)
        if not PRODUCT_CATALOG:
            print("Product catalog is empty!")
            return []  # Return empty list if catalog is empty
            
        print(f"Product catalog has {len(PRODUCT_CATALOG)} items")
            
        # For "best-selling" or similar queries, sort by rating and return top items
        if query and any(term in query.lower() for term in ["best-selling", "bestselling", "popular", "top"]):
            print("Getting best-selling products by rating")
            
            # If product type is specified, filter by category
            if category:
                # Filter products by matching category
                filtered_products = [p for p in PRODUCT_CATALOG 
                                    if category.lower() in p.get("category", "").lower()]
                
                if filtered_products:
                    # Sort filtered products by rating and return top 5
                    sorted_products = sorted(filtered_products, key=lambda p: p.get("rating", 0), reverse=True)
                    return [format_product_for_response(p) for p in sorted_products[:5]]
            
            # If no product type or no matching products, return top rated products
            sorted_products = sorted(PRODUCT_CATALOG, key=lambda p: p.get("rating", 0), reverse=True)
            return [format_product_for_response(p) for p in sorted_products[:5]]
        
        # If no specific query or matching fails, fall back to serving some products
        if not query or not self.openai_available:
            print("Using fallback method to find products")
            # Just return some products (first 5)
            if len(PRODUCT_CATALOG) > 0:
                return [format_product_for_response(p) for p in PRODUCT_CATALOG[:5]]
            return []
        
        try:
            # Use OpenAI to understand the query better and extract key attributes
            prompt = f"""
            I need to find products based on this query: "{query}"
            Extract key attributes that would be relevant for finding matching products.
            Consider product types, colors, styles, patterns, occasions, materials, etc.
            Return only a comma-separated list of keywords, no explanations.
            """
            
            response = openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts key product attributes from search queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            # Extract keywords from the response
            keywords = response.choices[0].message.content.strip().split(',')
            keywords = [k.strip().lower() for k in keywords]
            print(f"Extracted keywords: {keywords}")
            
            # Add the original query terms
            query_terms = query.lower().split()
            keywords.extend(query_terms)
            
            # If product type is specified, add it as an important keyword with high weight
            if category:
                keywords.extend([category.lower()] * 5)  # Add multiple times to increase weight
            
            # Score products based on keyword matches
            scored_products = []
            for product in PRODUCT_CATALOG:
                score = 0
                product_text = (product["name"] + " " + product["description"] + " " + product.get("category", "")).lower()
                
                # If product type is specified, strongly prioritize category matches
                if category and category.lower() in product.get("category", "").lower():
                    score += 10  # Significant boost for category match
                
                # Calculate keyword matches
                for keyword in keywords:
                    if keyword in product_text:
                        score += 1
                        # Give bonus points for matches in the name
                        if keyword in product["name"].lower():
                            score += 0.5
                
                # Add a small base score to ensure some products are returned
                score += 0.1
                
                # Add the product with its score for debugging
                print(f"Product: {product['name']}, Category: {product.get('category', 'Unknown')}, Score: {score}")
                scored_products.append((score, product))
            
            # Sort by score (descending) and return top matches
            scored_products.sort(reverse=True, key=lambda x: x[0])
            
            # If no products with good matches, fall back to returning some products
            if not scored_products or scored_products[0][0] <= 0.5:
                print("No good matches found, using fallback")
                
                # Try to filter by product type if specified
                if category:
                    filtered_products = [p for p in PRODUCT_CATALOG 
                                      if category.lower() in p.get("category", "").lower()]
                    
                    if filtered_products:
                        # Sort filtered products by rating and return top 5
                        sorted_by_rating = sorted(filtered_products, key=lambda p: p.get("rating", 0), reverse=True)
                        return [format_product_for_response(p) for p in sorted_by_rating[:5]]
                
                # Otherwise return top rated products
                sorted_by_rating = sorted(PRODUCT_CATALOG, key=lambda p: p.get("rating", 0), reverse=True)
                return [format_product_for_response(p) for p in sorted_by_rating[:5]]
                
            # Return formatted products
            recommendations = [format_product_for_response(p[1]) for p in scored_products[:5]]
            return recommendations
            
        except Exception as e:
            print(f"Error during OpenAI-powered recommendation: {e}")
            # Fall back to returning some products
            sorted_by_rating = sorted(PRODUCT_CATALOG, key=lambda p: p.get("rating", 0), reverse=True)
            return [format_product_for_response(p) for p in sorted_by_rating[:5]]

    def search_by_image(self, image_file):
        """Searches for similar products based on an uploaded image using CLIP and direct database querying."""
        print(f"Received image search request for file: {image_file.filename}")
        
        try:
            # Extract features from the uploaded image
            img = Image.open(image_file.stream)
            query_feature = extract_features_clip(img)
            
            if query_feature is None:
                return [{"error": "Failed to extract features from the uploaded image."}]

            # If using database, query all products and compare them directly
            if self.use_database:
                try:
                    # Get all products from database
                    db_products = get_all_products()
                    
                    if not db_products:
                        return [{"error": "No products found in database."}]
                    
                    # Load CLIP model
                    model, processor = load_clip_model()
                    if model is None or processor is None:
                        return [{"error": "Failed to load CLIP model."}]
                    
                    # Compare query image with each product image
                    results = []
                    
                    for product in db_products:
                        # Skip products without images
                        if not product.get('image_url'):
                            continue
                            
                        try:
                            # Get the product image path
                            image_path = os.path.join(PRODUCT_DATA_DIR, os.path.basename(product['image_url']))
                            
                            # If the file doesn't exist, skip this product
                            if not os.path.exists(image_path):
                                continue
                                
                            # Extract features from product image
                            product_img = Image.open(image_path)
                            product_feature = extract_features_clip(product_img)
                            
                            if product_feature is not None:
                                # Calculate similarity (using cosine similarity)
                                query_feature_np = np.array(query_feature)
                                product_feature_np = np.array(product_feature)
                                
                                # Normalize vectors
                                query_feature_np = query_feature_np / np.linalg.norm(query_feature_np)
                                product_feature_np = product_feature_np / np.linalg.norm(product_feature_np)
                                
                                # Calculate cosine similarity
                                similarity = np.dot(query_feature_np, product_feature_np)
                                
                                # Format product with similarity score
                                formatted_product = {
                                    "id": product['product_id'],
                                    "name": product['name'],
                                    "description": product['description'],
                                    "price": float(product['price']),
                                    "image_filename": os.path.basename(product['image_url']) if product['image_url'] else None,
                                    "image_url": product['image_url'],
                                    "rating": float(product['average_rating']),
                                    "category": product['categories'][0]['name'] if product['categories'] else "Unknown",
                                    "similarity_score": float(similarity)
                                }
                                
                                results.append(formatted_product)
                        except Exception as e:
                            print(f"Error processing product image for product {product['product_id']}: {e}")
                            continue
                    
                    # Sort results by similarity (highest first)
                    results = [r for r in results if r.get("similarity_score", 0) >= 0.7]
                    results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                    
                    # Limit results
                    results = results[:5]
                    
                    if not results:
                        return [{"error": "No similar products found."}]
                        
                    return results
                    
                except Exception as e:
                    print(f"Error during database image search: {e}")
                    # Fall back to file-based method if database search fails
            
            # Fall back to file-based approach if not using database or if database approach failed
            if image_feature_index is None or image_feature_index.ntotal == 0:
                # Try to build the index if it doesn't exist
                build_image_index()
                
                # Check again if index was built successfully
                if image_feature_index is None or image_feature_index.ntotal == 0:
                    return [{"error": "Image search index could not be built. Please check your product catalog."}]

            # Search the FAISS index
            k = 5 # Number of nearest neighbors to find
            query_feature_np = np.array([query_feature]).astype("float32")
            
            # Check if dimensions match
            if query_feature_np.shape[1] != image_feature_index.d:
                print(f"Feature dimension mismatch: got {query_feature_np.shape[1]}, expected {image_feature_index.d}")
                return [{"error": "Incompatible image feature dimensions."}]
                
            distances, indices = image_feature_index.search(query_feature_np, k)
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1: # FAISS returns -1 for invalid indices
                    product_id = product_id_map.get(idx)
                    if product_id is not None:
                        # Find the product in the catalog
                        product = next((p for p in PRODUCT_CATALOG if p["id"] == product_id), None)
                        if product:
                            # Add similarity score (inverse of distance)
                            product_with_score = format_product_for_response(product)
                            product_with_score["similarity_score"] = float(1.0 / (1.0 + distances[0][i]))
                            results.append(product_with_score)
            
            # Sort by similarity score (descending)
            print(f"Results before sorting: {results}")
            results = [r for r in results if r.get("similarity_score", 0) >= 0.7]
            results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            print(f"Found {len(results)} similar products.")
            
            if not results:
                return [{"error": "No similar products found."}]
                
            return results

        except Exception as e:
            print(f"Error during image search: {e}")
            return [{"error": "Failed to process image search."}]

    def get_all_products(self):
        """Returns the entire product catalog, formatted for response."""
        if self.use_database:
            try:
                # Get products from the database
                db_products = get_all_products()
                
                # Format them similar to the file-based format
                products = []
                for product in db_products:
                    formatted_product = {
                        "id": product['product_id'],
                        "name": product['name'],
                        "description": product['description'],
                        "price": float(product['price']),
                        "image_filename": product['image_url'].split('/')[-1] if product['image_url'] else None,
                        "image_url": product['image_url'],
                        "rating": float(product['average_rating']),
                        "category": product['categories'][0]['name'] if product['categories'] else "Unknown"
                    }
                    products.append(formatted_product)
                    print(f"Formatted product: {formatted_product}")
                return products
            except Exception as e:
                print(f"Error getting products from database: {e}")
                # Fall back to file-based catalog
                return [format_product_for_response(p) for p in PRODUCT_CATALOG]
        else:
            # Use file-based catalog
            return [format_product_for_response(p) for p in PRODUCT_CATALOG]

