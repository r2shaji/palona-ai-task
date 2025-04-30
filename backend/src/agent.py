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
            
            # First check if we're going to find products matching these criteria
            has_specific_product = False
            alternate_message = None
            
            if category and description:
                # Do a preliminary search to see if we have the specific products
                try:
                    # Try to find the specific products requested
                    test_recommendations = self.recommend_products(user_message, category, description, check_only=True)
                    if test_recommendations and isinstance(test_recommendations, dict) and test_recommendations.get('has_exact_match') is False:
                        # We found that there are no exact matches, but we have alternatives
                        has_specific_product = False
                        alternate_message = f"We don't have {description} {category} at the moment. Here are other {category} options you might like:"
                    else:
                        has_specific_product = True
                except Exception as e:
                    print(f"Error during product availability check: {e}")
                    has_specific_product = True  # Default to showing normal response
            else:
                has_specific_product = True  # No specific criteria, so proceed normally
            
            # Generate educational response with OpenAI first, but only if we have the specific product
            # or no specific product was requested
            if has_specific_product:
                intro_text = self._get_ai_response(user_message, intent="recommendation")
            else:
                # Use our alternate message instead of the AI response
                intro_text = alternate_message
            
            # For best-selling products query or if no specific category, use the original message
            if "best" in user_message.lower() or "popular" in user_message.lower() or not category:
                recommendations = self.recommend_products(user_message)
            else:
                # Pass the full message to ensure description is used
                recommendations = self.recommend_products(user_message, category, description)
            
            # If we have an alternate message in the recommendations, remove it since we've already
            # used it as the main response text
            if not has_specific_product and recommendations and len(recommendations) > 0 and 'alternate_message' in recommendations[0]:
                del recommendations[0]['alternate_message']
            
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
            
            Task 1: Determine if this is a regular product search or a "complementary product" query.
            A complementary product query would be something like "what goes well with skirts" or "what should I wear with jeans".
            
            Task 2: Based on your analysis, extract ONE product type/category from the query:
            
            - If this is a REGULAR product search:
              * Extract the main product category the user is looking for
              * Valid categories are: T-Shirts, Pants, Jackets, Skirts
              * Return ONLY the category name exactly as listed above
            
            - If this is a COMPLEMENTARY product query:
              * Identify what product the user already has (like skirts, pants, etc.)
              * Determine what would go well with that product
              * For tops, return "T-Shirts"
              * For bottoms, return "Pants" or "Skirts" as appropriate
              * For outerwear, return "Jackets"
              * Return ONLY the complementary category name
            
            Example valid responses:
            "T-Shirts" (for regular search for shirts or if complementary to pants/skirts)
            "Pants" (for regular search for pants/jeans or if complementary to shirts)
            "Jackets" (for regular search for jackets/coats or as a complementary layer)
            "Skirts" (for regular search for skirts or if complementary to tops)
            
            Return ONLY the category name with no additional explanation or text.
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
            
            # Normalize the category
            normalized_category = self._normalize_category(category)
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

    def _search_by_category(self, category, description=None, alternative_suggestion=False, original_description=None):
        """Search for products by category with optional description filtering.
        
        Returns:
            list: Formatted product list or None if no results
        """
        print(f"Querying products directly by category: {category}")
        category_fallbacks = self._get_category_fallbacks()
        
        filtered_products = get_products_by_category(category)
        
        # For category-only search, let's try to filter by description ourselves
        if filtered_products and description and not alternative_suggestion:
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
                if fallback_products and description and not alternative_suggestion:
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
            
            # Add alternate message if needed
            if alternative_suggestion and original_description:
                print(f"Showing alternative products from category '{category}' instead of '{original_description} {category}'")
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
        """Search for products using file-based approach."""
        print("Using file-based product search")
        if not PRODUCT_CATALOG:
            print("Product catalog is empty!")
            return []

        alternative_file_suggestion = explicit_category_request and description and category

        # Use passed category/description for file search too
        filtered_products = PRODUCT_CATALOG
        if category:
            filtered_products = [p for p in filtered_products if category.lower() in p.get("category", "").lower()]

        if description and not alternative_file_suggestion:
             # Simple keyword matching for file-based description search
             desc_keywords = description.lower().split()
             desc_filtered = [p for p in filtered_products if all(kw in (p['name'].lower() + " " + p['description'].lower()) for kw in desc_keywords)]
             
             # If we found matches with the description, use them
             if desc_filtered:
                 filtered_products = desc_filtered
             # Otherwise, if this was a specific query, keep the category-only results as alternatives
             elif alternative_file_suggestion:
                 print(f"No {description} {category} found in file-based search, suggesting alternatives")
                 # Keep filtered_products as is - they're just the category matches

        # Sort remaining products (by rating or original order)
        if filtered_products:
            sorted_products = sorted(filtered_products, key=lambda p: p.get("rating", 0), reverse=True)
            formatted_results = [format_product_for_response(p) for p in sorted_products[:5]]
            
            # If we're showing alternative suggestions, add a note
            if alternative_file_suggestion:
                alternate_message = f"We don't have {original_description} {category} at the moment. Here are other {category} options you might like:"
                if formatted_results:
                    formatted_results[0]['alternate_message'] = alternate_message
                    
            return formatted_results
            
        elif explicit_category_request:
            # Honor the explicit category request by returning empty results
            return []
        else:
             # Fallback to top-rated overall if filtering yields nothing
             # but only for non-explicit category requests
             sorted_products = sorted(PRODUCT_CATALOG, key=lambda p: p.get("rating", 0), reverse=True)
             return [format_product_for_response(p) for p in sorted_products[:5]]

    def recommend_products(self, query, category=None, description=None, check_only=False):
        """Recommends products based on a text query, potentially using pre-extracted category/description."""
        # Extract category and description from the query if not provided
        if category is None or description is None:
            extracted_category, extracted_description = self._extract_product_type(query)
            category = category or extracted_category
            description = description or extracted_description
            print(f"Extracted from query - category: '{category}', description: '{description}'")

        # Track if category was explicitly requested
        explicit_category_request = category is not None
        # Store initial description for message creation if needed
        original_description = description

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
                        original_description
                    )
                    
                    if category_results:
                        print(f"Found {len(category_results)} products in category '{category}'")
                        
                        # Sort by rating if query implies 'best'
                        if query and any(term in query.lower() for term in [
                            "best-selling", "bestselling", "popular", "top", "comfortable", "best", "what"
                        ]):
                            category_results = sorted(category_results, key=lambda p: float(p.get('rating', 0)), reverse=True)
                            
                        return category_results[:5]
                
                # 3. For explicit category searches with no results, honor the request
                if explicit_category_request and category:
                    print(f"No products found at all for explicit category request: {category}")
                    return []

                # 4. Fallback to best-sellers for non-explicit category requests
                if not explicit_category_request:
                    return self._get_best_sellers()
                else:
                    # Honor explicit category request by returning empty results
                    return []

            except Exception as e:
                print(f"Error performing database product search: {e}")
                # Fall back to file-based implementation
        
        # --- File-based search path (if database fails or unavailable) ---
        return self._search_file_based(category, description, explicit_category_request, original_description)

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
                    return [{"error": "Image search index could not be built. Please check your product catalog."}]

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

            # If using database, query all products and compare them directly
            if self.use_database:
                return self._search_database_by_image(query_feature)
            
            # Fall back to file-based approach using FAISS index
            return self._search_faiss_by_image(query_feature)

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

