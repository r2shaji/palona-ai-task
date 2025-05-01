# backend/src/agent.py
from io import BytesIO
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
from database import get_all_products, get_product_by_id, get_products_by_category, search_products_by_description, engine, get_all_categories, get_top_products_by_category
import boto3
from botocore.exceptions import ClientError

load_dotenv()

# --- OpenAI Setup ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY not found in environment variables.")
else:
    openai.api_key = OPENAI_API_KEY

s3 = boto3.client('s3')           # picks up the EC2 role for creds
BUCKET = 'danieldoescode-s3'
PREFIX = 'palona/data/'

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

# --- Image Feature Index (using CLIP) ---
image_feature_index = None
product_id_map = {}
CLIP_FEATURE_DIMENSION = 768  

def build_image_index():
    """Builds the FAISS index for image features using CLIP using top products from each category."""
    global image_feature_index, product_id_map
    
    print("Building image index with CLIP features from database...")
    start_time = time.time()
    
    # Ensure CLIP model is loaded
    model, processor = load_clip_model()
    if model is None or processor is None:
        print("Cannot build image index: Failed to load CLIP model.")
        return
    
    # Get all categories from the database
    categories = get_all_categories()
    if not categories:
        print("Cannot build image index: No categories found in database.")
        return
    
    features = []
    product_ids = []
    products_processed = 0
    
    # For each category, get the top 10 products
    for category in categories:
        category_name = category['name']
        print(f"Processing top products from category: {category_name}")
        
        # Get top 10 products from this category
        top_products = get_top_products_by_category(category_name, limit=10)
        
        for product in top_products:
            try:
                # Skip products without image URLs
                if not product['image_url']:
                    print(f"Warning: Product {product['product_id']} has no image.")
                    continue

                # Get the full image URL - prepend API base URL if needed
                image_url = "/api" + product['image_url']
                # Note: You may need to adjust this depending on how your URLs are structured
                if not image_url.startswith(('http://', 'https://')):
                    # Get base URL from environment or use a default
                    base_url = os.getenv("API_BASE_URL", "http://localhost:5001")
                    image_url = f"{base_url}{image_url if image_url.startswith('/') else '/' + image_url}"
                
                try:
                    
                    img = fetch_image(product['image_url'].split("/")[-1])
                    feature = extract_features_clip(img)
                    
                    if feature is not None:
                        features.append(feature)
                        product_ids.append(product['product_id'])
                        products_processed += 1
                    else:
                        print(f"Warning: Could not extract features for product {product['product_id']}")
                except Exception as e:
                    print(f"Error fetching image for product {product['product_id']}: {e}")
                    continue
                
            except Exception as e:
                print(f"Error processing product {product['product_id']}: {e}")
    
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
    print(f"Image index built successfully with {len(product_ids)} products from {len(categories)} categories in {end_time - start_time:.2f} seconds.")

def fetch_image(filename):
    obj = s3.get_object(Bucket=BUCKET, Key=f"{PREFIX}{filename}")
    return Image.open(BytesIO(obj["Body"].read()))

class CommerceAgent:
    def __init__(self):
        self.openai_available = bool(OPENAI_API_KEY)
        if not self.openai_available:
            print("OpenAI API key not set. Chat functionality will be limited.")
        
        # Always use database mode
        self.use_database = True
        try:
            db_products = get_all_products()
            print(f"Using MySQL database for product data. Found {len(db_products)} products.")
            
            # Build the image index using database products
            if image_feature_index is None:
                print("Building image index for similar product search...")
                build_image_index()
        except Exception as e:
            print(f"Error connecting to database: {e}")
            # We don't have a fallback anymore - everything is database-based

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
            
            # CRITICAL FIX: Explicitly handle "General" category from OpenAI -> treat as no category
            # Also catch quoted versions from logs like "General"
            if category and category.lower().strip('"\'') == "general":
                print("DEBUG: Treating extracted 'General' category as None")
                category = None
                
            # Reset description if it's "none"
            if description and description.lower() == "none":
                print("DEBUG: Setting 'none' description to None in chat method")
                description = None
            
            # First check if we're going to find products matching these criteria
            has_specific_product = False
            alternate_message = None
            
            # Check if this was a request for a category we don't have
            if hasattr(self, 'alternative_suggestion') and self.alternative_suggestion:
                original_category = self.original_category
                alternate_message = f"We don't have {original_category} available in our store. Here are some {category} options you might like instead:"
                print(f"DEBUG: Using alternative category message: {alternate_message}")
                has_specific_product = False
            # Check for specific products ONLY if category and description are valid and category is not 'General'
            elif category and description:
                # Only check for specific products if we have a meaningful description
                # Try to find the specific products requested
                try:
                    test_recommendations = self.recommend_products(user_message, category, description, check_only=True)
                    if test_recommendations and isinstance(test_recommendations, dict) and test_recommendations.get('has_exact_match') is False:
                        # We found that there are no exact matches, but we have alternatives
                        has_specific_product = False
                        alternate_message = f"We don't have {description} {category} at the moment. Here are other {category} options you might like:"
                        print(f"DEBUG: Using no exact match message: {alternate_message}")
                    else:
                        has_specific_product = True
                except Exception as e:
                    print(f"Error during product availability check: {e}")
                    has_specific_product = True  # Default to showing normal response
            # Handle cases with category OR description, but not both (or general queries)
            else:
                has_specific_product = True  # No specific criteria to check against, so assume general display
            
            # Generate educational response with OpenAI first, but only if we have the specific product
            # or no specific product/category was requested
            if has_specific_product:
                intro_text = self._get_ai_response(user_message, intent="recommendation")
                print(f"DEBUG: Using AI response intro: {intro_text[:50]}...")
            else:
                # Use our alternate message instead of the AI response
                intro_text = alternate_message
                print(f"DEBUG: Using alternate message intro: {intro_text}")
            
            # CRITICAL FIX: More robust detection of best-selling, trending, popular type queries
            # Use best sellers/general popular items if query implies it or no category specified
            best_seller_indicators = ["best", "popular", "trending", "top", "bestselling", "best-selling", "favorite"]
            is_best_seller_query = any(term in user_message.lower() for term in best_seller_indicators)
            
            # CRITICAL FIX: Handle category-specific best-seller queries correctly
            if is_best_seller_query and category:
                print(f"DEBUG: Fetching best-sellers specifically for category='{category}'")
                recommendations = self.recommend_products(user_message, category, description)
            elif not category or is_best_seller_query:
                print(f"DEBUG: Fetching general best-selling products. Category={category}, is_best_seller_query={is_best_seller_query}")
                recommendations = self.recommend_products(user_message) # Gets best sellers
            else:
                # Fetch products based on category and description
                print(f"DEBUG: Fetching products for category='{category}', description='{description}'")
                recommendations = self.recommend_products(user_message, category, description)
            
            # Clean up potential alternate messages from recommendations if already handled
            if recommendations and len(recommendations) > 0 and 'alternate_message' in recommendations[0]:
                if not has_specific_product or 'none' in recommendations[0]['alternate_message'].lower():
                    print(f"DEBUG: Removing alternate_message from recommendations[0]: {recommendations[0]['alternate_message']}")
                    del recommendations[0]['alternate_message']
            
            # Final check to fix intro_text if it contains problematic phrases like "We don't have..." when category is None
            if not category and intro_text and "we don't have" in intro_text.lower():
                 print(f"DEBUG: Fixing intro_text for general query: {intro_text}")
                 # Replace with a generic intro or the AI response if available
                 ai_response_fallback = self._get_ai_response(user_message, intent="recommendation")
                 intro_text = ai_response_fallback if ai_response_fallback else "Here are some popular options:"
            
            # Always return recommendations - if none found, the recommend_products method
            # should fall back to popular items
            return {
                "text": intro_text,
                "is_recommendation": True,
                "recommendations": recommendations
            }
        else:
            # For general conversation, get AI response
            ai_response = self._get_ai_response(user_message, intent="conversation")
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
                print(f"Product recommendation intent detected: '{keyword}'")
                return "recommendation"
        
        # Then check for general question indicators
        for indicator in general_question_indicators:
            if indicator in message_lower:
                print(f"Conversation intent detected: '{indicator}' ")
                return "conversation"
        
        # If the message contains product-related terms, consider it a recommendation intent
        category, _ = self._extract_product_type(message)
        if category:
            print(f"Product recommendation intent inferred from product type: '{category}'")
            return "recommendation"
        
        # If no clear intent is detected, default to conversation
        print(f"No clear intent detected in: '{message_lower}', defaulting to conversation")
        return "conversation"

    def _get_ai_response(self, user_message, intent=None):
        """Generate a response to user messages using OpenAI.
        
        Args:
            user_message: The user's message
            intent: The pre-detected intent (optional)
        """
        if not self.openai_available:
            return "I'm sorry, but the AI chat service is currently unavailable. Please try again later."
        
        try:
            # Use the provided intent or analyze it if not provided
            is_recommendation = intent == "recommendation" if intent else self._analyze_intent(user_message) == "recommendation"
            
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

    def _get_product_type_mapping(self):
        """Get the mapping of product types to category names."""
        return {
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

    def _extract_category_using_openai(self, message):
        """Extract the product category from a message using OpenAI.
        
        Args:
            message: User message to analyze
            
        Returns:
            str: Normalized category name or None
        """
        try:
            # Use OpenAI to extract the product type and description
            prompt = f"""
            Analyze the following query from a customer shopping at a clothing store: "{message}"

            Our store only has these valid product categories: T-Shirts, Pants, Skirts.

            VALID ANSWER FORMAT:
            - Return ONLY ONE of these exact strings:
            * "T-Shirts" (if query is about shirts/tops)
            * "Pants" (if query is about pants/bottoms)
            * "Skirts" (if query is about skirts)
            * "Alternative:T-Shirts" (if query is about tops we don't carry, like jackets)
            * "Alternative:Pants" (if query is about bottoms we don't carry)
            * "Alternative:Skirts" (if query is about skirts or similar items)
            * "T-shirts" (if query is about what goes well with skirts, because it is a complementary query)
            * "Pants" (if query is about what goes well with white t-shirt, because it is a complementary query)
            * "General" (if query is about trending/seasonal items or general browsing)
            
            Task 1: Determine if this query is:
                -A specific product search 
                - A complementary product query. A complementary product query would be something like "what goes well with skirts" or "what should I wear with jeans".
                - A general browsing request (trending items, seasonal products, etc.)
            
            Task 2: Based on your analysis, extract ONE product type/category from the query:
            
            For specific product searches:
                * If the product exactly matches one of our valid categories, return just that category name
                * If the product is something we don't carry (like "jackets" or "dresses"), return "Alternative:NearestCategory" 
                    where NearestCategory is the most similar valid category (e.g., "Alternative:T-Shirts" for jackets)
            
            - If this is a COMPLEMENTARY product query:
              * Identify what product the user already has (like skirts, pants, etc.)
              * Determine what would go well with that product
              * For tops, return "T-Shirts"
              * For bottoms, return "Pants" or "Skirts" as appropriate
              * For outerwear, return "Jackets"
              * Return ONLY the complementary category name
              * If you identified jackets or other similar wear which don't match the valid categories, return "General"

            - If this is a GENERAL browsing request (like trending items, best sellers, what are trending, hot products,etc.):
                * Return ONLY the word "General"

            IMPORTANT: 
            1. Descriptive terms (colors, seasons, materials) are NOT categories
            2. Return ONLY a valid category, "Alternative:Category", or "General" with no explanation
            3. Make your best judgment to match non-valid categories to our valid ones based on apparel type
                
            Example valid responses:
            "T-Shirts" (for regular search for shirts or if complementary to pants/skirts)
            "Pants" (for regular search for pants/jeans or if complementary to shirts)
            "Skirts" (for regular search for skirts or if complementary to tops)

            """
            
            response = openai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a fashion expert assistant who understands clothing combinations and can extract product categories from user queries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=50
            )
            
            category = response.choices[0].message.content.strip()
            print(f"OpenAI extracted category: {category}")

            # Reset alternative suggestion flags
            self.alternative_suggestion = False
            self.original_category = None
            self.suggested_alternative = None

            # CRITICAL FIX: More robust General category check - handle with/without quotes, case insensitive
            # This ensures we catch all variations: General, "General", 'general', etc.
            if category.lower().strip('"\'') == "general":
                print("Query identified as general browsing request by OpenAI.")
                return None # Return None for General category
            
            # Handle alternative category suggestions
            if "alternative:" in category.lower():
                parts = category.split(":", 1)
                if len(parts) > 1:
                    alternative_category = parts[1].strip()
                    original_category_guess = "product" # Default guess
                    # Extract the original category the user asked for
                    # This is a simple extraction and could be improved with OpenAI
                    for word in ["jackets", "jacket", "coats", "coat", "sweaters", "sweatshirts", "dresses", "dress"]:
                        if word in message.lower():
                            original_category_guess = word
                            break
                    
                    print(f"Similar but invalid category detected: original '{original_category_guess}', suggested alternative: '{alternative_category}'")
                    
                    # Store the original invalid category and suggested alternative for better messaging
                    self.alternative_suggestion = True
                    self.original_category = original_category_guess # Store the guessed original request
                    self.suggested_alternative = alternative_category
                    
                    # Return the normalized alternative category
                    return self._normalize_category(alternative_category)
            
            # Normalize the category - check if the result is 'General' again after normalization
            normalized_category = self._normalize_category(category)
            if normalized_category and normalized_category.lower() == "general":
                 print("Normalized category resulted in 'General', returning None.")
                 return None
                 
            return normalized_category
            
        except Exception as e:
            print(f"Error during OpenAI category extraction: {e}")
            return None
    
    def _extract_description_using_openai(self, message):
        """Extract product description attributes from a message using OpenAI.
        
        Args:
            message: User message to analyze
            
        Returns:
            str: Extracted description or None
        """
        try:
            description_prompt = f"""
            Analyze this query and extract any descriptive terms about the product: "{message}"
            
            Focus on attributes like:
            - Objective attributes: color, material, pattern, size, occasion, season, etc.
            - NOT subjective qualifiers like: stylish, fashionable, trendy, cool, nice, beautiful, gorgeous

            Rules:
            1. If the query only contains subjective qualifiers (stylish, fashionable, trendy, etc.), return "none"
            2. If the query contains both objective attributes and subjective qualifiers, return ONLY the objective attributes
            3. If no descriptive terms are found, return "none"
            
            Return ONLY the descriptive terms as simple words or short phrases, no sentences or explanations.
            Do not include the product type itself in the description.
            
            Example inputs and outputs:
            "Show me some t-shirts" -> "none"
            "I want black pants" -> "black"
            "Looking for stylish pants" -> "none"
            "Looking for a warm jacket for winter" -> "warm, winter"
            "Show me more black pants" -> "black"
            "Show me more fashionable black shirts" -> "black"
            "Soft cotton shirts for summer" -> "soft, cotton, summer"
            "Do you have trendy skirts" -> "none"
            "Do you have red stylish pants" -> "red"
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
                return None
                
            # Process and clean up the description
            return self._process_description(description)
            
        except Exception as e:
            print(f"Error during OpenAI description extraction: {e}")
            return None
    
    def _normalize_category(self, category):
        """Normalize a category name to match our standard categories.
        
        Args:
            category: Category name to normalize
            
        Returns:
            str: Normalized category name or original if no match
        """
        if not category:
            return None
            
        type_to_category = self._get_product_type_mapping()
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
        
        # If we found a normalized category, use it, otherwise return original
        if normalized_category:
            return normalized_category
            
        # Check if category itself matches one of our standard categories
        standard_categories = set(type_to_category.values())
        for std_category in standard_categories:
            if std_category.lower() == category_lower:
                return std_category
                
        # If none of the above, check if the category is a clear negative
        if category_lower in ["none", "no product", "not found", "n/a"]:
            return None
            
        return category  # Return original if no match found
    
    def _process_description(self, description):
        """Process and clean up a product description.
        
        Args:
            description: Raw description to process
            
        Returns:
            str: Processed description or None
        """
        if not description:
            return None
            
        # If description is too long, it's likely not just attributes
        if len(description) > 30:
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
        
        print(f"Processed description: {description}")
        return description
    
    def _fallback_extract_product_type(self, message):
        """Extract product type using simple keyword matching as fallback.
        
        Args:
            message: User message to analyze
            
        Returns:
            tuple: (category, description) or (None, None)
        """
        type_to_category = self._get_product_type_mapping()
        message_lower = message.lower()
        
        # Check for product types in the message
        for product_type, category in type_to_category.items():
            if product_type in message_lower:
                print(f"Fallback detection: '{product_type}' -> '{category}'")
                return category, None
                
        return None, None  # Return None on errors
        
    def _extract_product_type(self, message):
        """Extract the product type and description from a user message."""
        # Use simple keyword matching if OpenAI is not available
        if not self.openai_available:
            return self._fallback_extract_product_type(message)
        
        try:
            # Extract category using OpenAI
            category = self._extract_category_using_openai(message)
            
            # Extract description separately
            description = self._extract_description_using_openai(message)
            
            print(f"Final category: {category}, Description: {description}")
            return category, description
            
        except Exception as e:
            print(f"Error during product type extraction: {e}")
            # Fall back to simple keyword matching on errors
            return self._fallback_extract_product_type(message)

    def _check_product_availability(self, description, category):
        """Check if products with specific description and category exist.
        
        Returns:
            dict: Contains has_exact_match indicating if specific products exist
        """
        
        if self.use_database:
            try:
                # Check if specific products exist
                specific_products = search_products_by_description(description, category)
                
                # If no specific products, try fallback categories
                if not specific_products:
                    category_fallbacks = self._get_category_fallbacks()
                    
                    for fallback_category in category_fallbacks.get(category, []):
                        fallback_products = search_products_by_description(description, fallback_category)
                        if fallback_products:
                            specific_products = fallback_products
                            break
                
                # Return result of check
                has_exact_match = len(specific_products) > 0
                return {'has_exact_match': has_exact_match}
            except Exception as e:
                print(f"Error during product availability check: {e}")
                return {'has_exact_match': True}  # Assume products exist if check fails
        else:
            # For non-database mode, assume products exist
            return {'has_exact_match': True}
    
    def _get_category_fallbacks(self):
        """Get mapping of categories to their fallback categories."""
        return {
            "T-Shirts": ["Shirts", "Tops"],
            "Pants": ["Jeans", "Trousers", "Bottoms"],
            "Jackets": ["Outerwear", "Coats"],
            "Skirts": ["Bottoms"]
        }
    
    def _search_by_description(self, description, category, explicit_category_request):
        """Search for products using description and category.
        
        Returns:
            list: Formatted product list or None if no results
        """
        try:
            category_fallbacks = self._get_category_fallbacks()
            description_results = search_products_by_description(description, category)
            
            # If no results and we have a fallback category, try with that
            if not description_results and category in category_fallbacks:
                for fallback_category in category_fallbacks.get(category, []):
                    print(f"Trying fallback category '{fallback_category}' with description '{description}'")
                    description_results = search_products_by_description(description, fallback_category)
                    if description_results:
                        print(f"Found {len(description_results)} products using fallback category")
                        break
                        
            # Try without category constraint only if appropriate
            if not description_results and description and not explicit_category_request:
                print(f"Trying description '{description}' without category constraint")
                description_results = search_products_by_description(description)
                
                # If we got results, make sure they match the requested category group
                # This prevents returning t-shirts when asking for pants, etc.
                if description_results and explicit_category_request:
                    # Determine the valid categories
                    valid_categories = [category] + category_fallbacks.get(category, [])
                    print(f"Filtering uncategorized results to match: {valid_categories}")
                    
                    # Filter the results to only include products in requested category family
                    filtered_results = []
                    for product in description_results:
                        if any(cat['name'] in valid_categories for cat in product['categories']):
                            filtered_results.append(product)
                            
                    if filtered_results:
                        description_results = filtered_results
                        print(f"Kept {len(filtered_results)} products after category filtering")
                    else:
                        # If filtering removed all results and category was explicit, don't show results
                        if explicit_category_request:
                            description_results = []
                            print("Removed all results due to category mismatch with explicit request")
                
            if description_results:
                return self._format_products(description_results, limit=5)
                
            return None
        except Exception as e:
            print(f"Error in description search: {e}")
            return None

    def _search_by_category(self, category, description=None, alternative_suggestion=False, original_description=None, original_query=None):
        """Search for products by category with optional description filtering.
        
        Returns:
            list: Formatted product list or None if no results
        """
        print(f"Querying products directly by category: {category}")
        category_fallbacks = self._get_category_fallbacks()

        # Check if this is an alternative suggestion
        has_alternative_msg = hasattr(self, 'alternative_suggestion') and self.alternative_suggestion
        
        # Check if this is a seasonal or general browsing query
        seasonal_terms = ["spring", "summer", "winter", "fall", "autumn", "trending", "season"]
        is_seasonal_description = original_description and any(term in original_description.lower() for term in seasonal_terms)
        is_seasonal_query = original_query and any(term in original_query.lower() for term in seasonal_terms)
        is_general_category = not category or (category and category.lower() == "general")
        
        # Block generating alternate messages for seasonal/trending queries
        if is_seasonal_description or is_seasonal_query or is_general_category:
            alternative_suggestion = False
            print(f"DEBUG: Blocking alternate message for seasonal/trending query or general category")
        
        filtered_products = get_products_by_category(category)

        if filtered_products:
            # Format products
            formatted_products = self._format_products(filtered_products)
            
            # Add alternative message if this was a suggestion for an unsupported category
            # AND not a seasonal/trending query
            if has_alternative_msg and category == self.suggested_alternative and not is_seasonal_query:
                alt_message = f"We don't have the exact product you're looking for, but here are some {category} you might like instead:"
                if formatted_products:
                    formatted_products[0]['alternate_message'] = alt_message
            # Or add alternate message if needed for description not found
            # AND not a seasonal/trending query AND not a general category
            elif alternative_suggestion and original_description and original_description.lower() != "none" and not is_seasonal_description and not is_general_category:
                print(f"Showing alternative products from category '{category}' instead of '{original_description} {category}'")
                # Create a message that never mentions "none" or "general"
                alternate_message = f"Here are some popular {category} options:"
                if original_description and original_description.lower() != "none" and "general" not in original_description.lower() and not is_seasonal_description:
                    alternate_message = f"We don't have {original_description} {category} at the moment. Here are other {category} options you might like:"
                
                if formatted_products:
                    formatted_products[0]['alternate_message'] = alternate_message
            
            return formatted_products
        
        # For category-only search, let's try to filter by description ourselves
        if filtered_products and description and not alternative_suggestion and description.lower() != "none":
            print(f"Filtering {len(filtered_products)} products from '{category}' by description '{description}'")
            matching_products = []
            description_terms = description.lower().split()
            
            for product in filtered_products:
                product_text = (product['name'] + ' ' + product['description']).lower()
                # Product matches if all description terms are found in product text
                if all(term in product_text for term in description_terms):
                    matching_products.append(product)
                    
            if matching_products:
                print(f"Found {len(matching_products)} products after manual filtering by description")
                filtered_products = matching_products

        
        # If no results with primary category, try fallback categories
        if not filtered_products and category in category_fallbacks:
            for fallback_category in category_fallbacks.get(category, []):
                print(f"Trying fallback category: {fallback_category}")
                fallback_products = get_products_by_category(fallback_category)
                
                # Also apply description filtering to fallback results if available
                if fallback_products and description and not alternative_suggestion and description.lower() != "none":
                    matching_fallback = []
                    description_terms = description.lower().split()
                    
                    for product in fallback_products:
                        product_text = (product['name'] + ' ' + product['description']).lower()
                        if all(term in product_text for term in description_terms):
                            matching_fallback.append(product)
                            
                    if matching_fallback:
                        filtered_products = matching_fallback
                        print(f"Found {len(filtered_products)} products in fallback category matching description")
                        break
                elif fallback_products:
                    filtered_products = fallback_products
                    print(f"Found {len(filtered_products)} products using fallback category")
                    break
        
        if filtered_products:
            # Format products
            formatted_products = self._format_products(filtered_products)
            
            # Add alternate message if needed - BUT ONLY IF not seasonal/trending AND not general category
            if alternative_suggestion and original_description and original_description.lower() != "none" and not is_seasonal_description and not is_general_category:
                print(f"Showing alternative products from category '{category}' instead of '{original_description} {category}'")
                # Create a message that never mentions "none"
                alternate_message = f"Here are some popular {category} options:"
                if original_description and original_description.lower() != "none" and "general" not in original_description.lower() and not is_seasonal_description:
                    alternate_message = f"We don't have {original_description} {category} at the moment. Here are other {category} options you might like:"
                
                if formatted_products:
                    formatted_products[0]['alternate_message'] = alternate_message
                    
            return formatted_products
            
        return None
        
    def _get_best_sellers(self):
        """Get best-selling products as a fallback."""
        print("Falling back to general best-selling products from database")
        all_products = get_all_products()  # Already sorted by rating in the DB function
        if all_products:
            return self._format_products(all_products, limit=5)
        return []
        
    def _format_products(self, products, limit=5, sort_by_rating=False):
        """Format database products into a consistent response format."""
        formatted_products = []
        
        for product in products[:limit]:  # Apply limit here
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
            
        if sort_by_rating:
            formatted_products = sorted(formatted_products, key=lambda p: float(p.get('rating', 0)), reverse=True)
            
        return formatted_products[:limit]  # Ensure we don't exceed the limit
        
    def _search_file_based(self, category, description, explicit_category_request, original_description):
        """Simple fallback search method using database queries when regular search fails.
        Simplified version that only uses the database."""
        print("Using fallback database search method")
        
        # Reset description if it's "none"
        if description and description.lower() == "none":
            print("DEBUG: Setting 'none' description to None in _search_file_based")
            description = None
            original_description = None
        
        # Try to get products by category first
        if category:
            products = get_products_by_category(category)
            
            # Filter by description if we have one
            if description and products and description.lower() != "none":
                description_terms = description.lower().split()
                filtered_products = []
                
                # Apply manual filtering
                for product in products:
                    product_text = (product['name'] + ' ' + product['description']).lower()
                    # Product matches if all description terms are found in product text
                    if all(term in product_text for term in description_terms):
                        filtered_products.append(product)
            
            if filtered_products:
                print(f"Found {len(filtered_products)} products matching '{description}' in category '{category}'")
                formatted_results = self._format_products(filtered_products, limit=5)
                return formatted_results
            
            # If we have products for the category but no matches with description,
            # show category products as alternatives if this was a specific request
            if products and explicit_category_request and description and description.lower() != "none":
                print(f"No {description} {category} found, suggesting alternatives from category")
                formatted_results = self._format_products(products, limit=5)
                
                # Add alternative message
                if formatted_results and original_description and original_description.lower() != "none":
                    alternate_message = f"We don't have {original_description} {category} at the moment. Here are other {category} options you might like:"
                    print(f"DEBUG: Setting alternate_message in _search_file_based: {alternate_message}")
                    formatted_results[0]['alternate_message'] = alternate_message
                
                return formatted_results
            
            # Return category products without any description filtering
            if products:
                return self._format_products(products, limit=5)
        
        # Honor explicit category requests by returning empty for no matches
        if explicit_category_request:
            return []
            
        # Final fallback - get popular products
        return self._get_best_sellers()

    def recommend_products(self, query, category=None, description=None, check_only=False):
        """Recommends products based on a text query, potentially using pre-extracted category/description."""
        # Extract category and description from the query if not provided
        if category is None or description is None:
            extracted_category, extracted_description = self._extract_product_type(query)
            category = category or extracted_category
            description = description or extracted_description
            print(f"Extracted from query - category: '{category}', description: '{description}'")

        # CRITICAL FIX: Normalize "General" category to None in ALL forms (with or without quotes)
        if category:
            # Check for the various forms "General" might appear from logs
            general_patterns = ["general", '"general"', "'general'"]
            if any(category.lower().strip('"\'') == pattern.lower().strip('"\'') for pattern in general_patterns):
                print(f"DEBUG: Converting category '{category}' to None (general query)")
                category = None
        
        # Track if category was explicitly requested
        explicit_category_request = category is not None
        
        # Store initial description for message creation if needed
        original_description = description
        
        # If description is "none", treat it as None
        if description and (description.lower() == "none" or description.lower() == '"none"' or description.lower() == "'none'"):
            description = None
            original_description = None
        
        # Check if this is a best-seller type query
        best_seller_terms = ["best", "best-selling", "bestselling", "popular", "top", "trending"]
        is_best_seller_query = any(term in query.lower() for term in best_seller_terms)
        
        # Handle seasonal or general browsing queries
        seasonal_terms = ["spring", "summer", "winter", "fall", "autumn", "season"]
        is_seasonal_query = any(term in query.lower() for term in seasonal_terms)
        is_general_query = category is None  # Since we normalized "General" to None above
        
        # CRITICAL FIX: Only bypass normal flow for GENERAL best-seller queries (no specific category)
        # For category-specific best-seller queries (e.g., "best-selling pants"), use the category filter
        if is_general_query and (is_best_seller_query or is_seasonal_query):
            print(f"DEBUG: Bypassing normal query flow for general best-seller query: '{query}'")
            return self._get_best_sellers()
        
        # For category-specific best-seller queries, continue with normal flow but use sorting by rating later

        # If this is just a check for product availability, handle it separately
        if check_only and category and description:
            return self._check_product_availability(description, category)

        # --- Database search path ---
        if self.use_database:
            try:
                # 1. Try description + category search first
                if description and category:
                    description_results = self._search_by_description(description, category, explicit_category_request)
                    if description_results:
                        # If this is a best-seller query, sort by rating
                        if is_best_seller_query:
                            description_results = sorted(description_results, 
                                                       key=lambda p: float(p.get('rating', 0)), 
                                                       reverse=True)
                        return description_results
                
                # 2. If description search failed, try category search with alternatives
                alternative_suggestion = False
                if explicit_category_request and description and category:
                    alternative_suggestion = True
                    print(f"No {description} {category} found, will suggest alternatives from {category}")
                
                if category:
                    category_results = self._search_by_category(
                        category, 
                        description, 
                        alternative_suggestion,
                        original_description,
                        query  # Pass the original query to check for seasonal/trending terms
                    )
                    
                    if category_results:
                        print(f"Found {len(category_results)} products in category '{category}'")
                        
                        # Sort by rating if this is a best-seller query or query implies 'best'
                        if is_best_seller_query or any(term in query.lower() for term in [
                            "comfortable", "best", "comfort"
                        ]):
                            print(f"DEBUG: Sorting {category} products by rating (best-seller query)")
                            category_results = sorted(category_results, 
                                                   key=lambda p: float(p.get('rating', 0)), 
                                                   reverse=True)
                        
                        # Safety check: Remove any alternate_message with 'none' in it
                        if len(category_results) > 0 and 'alternate_message' in category_results[0]:
                            message = category_results[0]['alternate_message']
                            if 'none' in message.lower() or 'general' in message.lower():
                                print(f"DEBUG: Cleaning up problematic alternate_message: {message}")
                                del category_results[0]['alternate_message']
                            
                        return category_results[:5]
                
                # 3. For explicit category searches with no results, don't return empty but use best-sellers
                # CRITICAL FIX: Always fall back to best-sellers rather than empty results
                print(f"DEBUG: Falling back to best-sellers after no specific matches found")
                return self._get_best_sellers()

            except Exception as e:
                print(f"Error performing database product search: {e}")
                # Fall back to file-based implementation
        
        # --- File-based search path (if database fails or unavailable) ---
        results = self._search_file_based(category, description, explicit_category_request, original_description)
        
        # Final safety check for any 'none' or 'general' references in alternate_message
        if results and len(results) > 0 and 'alternate_message' in results[0]:
            message = results[0]['alternate_message'] 
            if 'none' in message.lower() or 'general' in message.lower() or any(term in message.lower() for term in seasonal_terms):
                print(f"DEBUG: Removing problematic alternate_message in final safety check: {message}")
                del results[0]['alternate_message']
        
        # CRITICAL FIX: If no results, always return best-sellers
        if not results or len(results) == 0:
            print(f"DEBUG: No results from file-based search, returning best-sellers")
            return self._get_best_sellers()
        
        return results

    def _get_best_sellers_by_category(self, category, limit=5):
        """Get best-selling products from a specific category."""
        print(f"DEBUG: Getting best-sellers specifically for category: {category}")
        try:
            # Get products directly from the category with proper sorting
            products = get_top_products_by_category(category, limit=limit)
            if products:
                return self._format_products(products, limit=limit)
            
            # If no direct results, try to find by category directly
            category_products = get_products_by_category(category)
            if category_products:
                # Sort by rating ourselves
                sorted_products = sorted(category_products, 
                                       key=lambda p: float(p['average_rating']), 
                                       reverse=True)
                return self._format_products(sorted_products, limit=limit, sort_by_rating=True)
            
            # If still no results, return general best-sellers
            print(f"DEBUG: No products found for category {category}, returning general best-sellers")
            return self._get_best_sellers(limit)
        except Exception as e:
            print(f"Error getting best-sellers for category {category}: {e}")
            return self._get_best_sellers(limit)

    def _extract_image_features(self, img):
        """Extract features from an image using CLIP.
        
        Args:
            img: PIL Image object
            
        Returns:
            numpy array: Feature vector or None if extraction failed
        """
        try:
            # Extract features from the uploaded image
            query_feature = extract_features_clip(img)
            if query_feature is None:
                print("Failed to extract features from the image")
                return None
            return query_feature
        except Exception as e:
            print(f"Error extracting image features: {e}")
            return None
            
    def _search_database_by_image(self, query_feature):
        """Search for similar products in the database using image features.
        
        Args:
            query_feature: CLIP feature vector from query image
            
        Returns:
            list: List of formatted product dictionaries with similarity scores
        """
        try:
            # If we have a FAISS index built from the database, use it
            if image_feature_index is not None and image_feature_index.ntotal > 0:
                print("Using pre-built FAISS index for image search")
                # Search the FAISS index
                k = min(5, image_feature_index.ntotal)  # Number of nearest neighbors
                query_feature_np = np.array([query_feature]).astype("float32")
                
                # Check if dimensions match
                if query_feature_np.shape[1] != image_feature_index.d:
                    print(f"Feature dimension mismatch: query has {query_feature_np.shape[1]}, index has {image_feature_index.d}")
                    return [{"error": "Incompatible image feature dimensions."}]
                    
                distances, indices = image_feature_index.search(query_feature_np, k)
                
                results = []
                for i, idx in enumerate(indices[0]):
                    if idx != -1:  # FAISS returns -1 for invalid indices
                        product_id = product_id_map.get(idx)
                        if product_id is not None:
                            # Get the product from database
                            product = get_product_by_id(product_id)
                            if product:
                                # Add similarity score (inverse of distance)
                                similarity = 1.0 / (1.0 + distances[0][i])
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
                
                # Filter by minimum similarity
                results = [r for r in results if r.get("similarity_score", 0) >= 0.7]
                # Sort by similarity (highest first)
                results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                
                if not results:
                    return [{"error": "No similar products found."}]
                    
                return results
            
            # Fallback method - direct comparison if index not available
            # Get all products from database
            db_products = get_all_products()
            
            if not db_products:
                print("No products found in database.")
                return [{"error": "No products found in database."}]
            
            # Load CLIP model
            model, processor = load_clip_model()
            if model is None or processor is None:
                print("Failed to load CLIP model.")
                return [{"error": "Failed to load CLIP model."}]
            
            # Compare query image with each product image
            results = []
            
            for product in db_products:
                # Skip products without images
                if not product.get('image_url'):
                    continue
                    
                try:
                    
                    img = fetch_image(product['image_url'].split("/")[-1])
                    product_feature = extract_features_clip(img)
                    
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
            
            # Sort results by similarity (highest first) and filter by threshold
            results = [r for r in results if r.get("similarity_score", 0) >= 0.7]
            results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            
            # Limit results
            results = results[:5]
            
            if not results:
                return [{"error": "No similar products found."}]
                
            return results
                
        except Exception as e:
            print(f"Error during database image search: {e}")
            return [{"error": f"Database search error: {e}"}]
            
    def _search_faiss_by_image(self, query_feature):
        """Search for similar products using FAISS index.
        
        Args:
            query_feature: CLIP feature vector from query image
            
        Returns:
            list: List of formatted product dictionaries with similarity scores
        """
        try:
            if image_feature_index is None or image_feature_index.ntotal == 0:
                # Try to build the index if it doesn't exist
                build_image_index()
                
                # Check again if index was built successfully
                if image_feature_index is None or image_feature_index.ntotal == 0:
                    return [{"error": "Image search index could not be built. Please check your product database."}]

            # Search the FAISS index
            k = 5  # Number of nearest neighbors to find
            query_feature_np = np.array([query_feature]).astype("float32")
            
            # Check if dimensions match
            if query_feature_np.shape[1] != image_feature_index.d:
                print(f"Feature dimension mismatch: got {query_feature_np.shape[1]}, expected {image_feature_index.d}")
                return [{"error": "Incompatible image feature dimensions."}]
                
            distances, indices = image_feature_index.search(query_feature_np, k)
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx != -1:  # FAISS returns -1 for invalid indices
                    product_id = product_id_map.get(idx)
                    if product_id is not None:
                        # Get the product from database
                        product = get_product_by_id(product_id)
                        if product:
                            # Add similarity score (inverse of distance)
                            formatted_product = {
                                "id": product['product_id'],
                                "name": product['name'],
                                "description": product['description'],
                                "price": float(product['price']),
                                "image_filename": os.path.basename(product['image_url']) if product['image_url'] else None,
                                "image_url": product['image_url'],
                                "rating": float(product['average_rating']),
                                "category": product['categories'][0]['name'] if product['categories'] else "Unknown",
                                "similarity_score": float(1.0 / (1.0 + distances[0][i]))
                            }
                            results.append(formatted_product)
            
            # Sort by similarity score (descending)
            print(f"Results before sorting: {results}")
            results = [r for r in results if r.get("similarity_score", 0) >= 0.7]
            results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            
            if not results:
                return [{"error": "No similar products found."}]
                
            return results
            
        except Exception as e:
            print(f"Error during FAISS search: {e}")
            return [{"error": f"FAISS search error: {e}"}]

    def search_by_image(self, image_file):
        """Searches for similar products based on an uploaded image using CLIP and direct database querying."""
        print(f"Received image search request for file: {image_file.filename}")
        
        try:
            # Extract features from the uploaded image
            img = Image.open(image_file.stream)
            query_feature = self._extract_image_features(img)
            
            if query_feature is None:
                return [{"error": "Failed to extract features from the uploaded image."}]

            # Query all products and compare them directly using database
            return self._search_database_by_image(query_feature)

        except Exception as e:
            print(f"Error during image search: {e}")
            return [{"error": "Failed to process image search."}]

    def get_all_products(self):
        """Returns the entire product catalog, formatted for response."""
        try:
            # Get products from the database
            db_products = get_all_products()
            
            # Format them
            products = []
            for product in db_products:
                formatted_product = {
                    "id": product['product_id'],
                    "name": product['name'],
                    "description": product['description'],
                    "price": float(product['price']),
                    "image_filename": os.path.basename(product['image_url']) if product['image_url'] else None,
                    "image_url": product['image_url'],
                    "rating": float(product['average_rating']),
                    "category": product['categories'][0]['name'] if product['categories'] else "Unknown"
                }
                products.append(formatted_product)
                print(f"Formatted product: {formatted_product}")
            return products
        except Exception as e:
            print(f"Error getting products from database: {e}")
            return []

