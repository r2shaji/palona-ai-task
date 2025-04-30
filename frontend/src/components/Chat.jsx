// frontend/src/components/Chat.jsx
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { chatWithAgent, searchByImage, getAllProducts, API_URL } from '../api';

const processBoldText = (text) => {
  // For debugging
  console.log("Processing text:", text);
  
  // Try a different approach - manually identify all bold sections
  let result = [];
  let currentText = '';
  let inBoldSection = false;
  let currentIndex = 0;
  
  for (let i = 0; i < text.length - 1; i++) {
    if (text[i] === '*' && text[i + 1] === '*') {
      // Found a ** marker
      if (inBoldSection) {
        // End of bold section
        if (currentText) {
          result.push(<strong key={`bold-${currentIndex}`}>{currentText}</strong>);
          currentText = '';
          currentIndex++;
        }
        inBoldSection = false;
        i++; // Skip the second *
      } else {
        // Start of bold section
        if (currentText) {
          result.push(<span key={`text-${currentIndex}`}>{currentText}</span>);
          currentText = '';
          currentIndex++;
        }
        inBoldSection = true;
        i++; // Skip the second *
      }
    } else {
      currentText += text[i];
      
      // Handle the last character
      if (i === text.length - 2) {
        currentText += text[i + 1];
      }
    }
  }
  
  // Add any remaining text
  if (currentText) {
    if (inBoldSection) {
      result.push(<strong key={`bold-${currentIndex}`}>{currentText}</strong>);
    } else {
      result.push(<span key={`text-${currentIndex}`}>{currentText}</span>);
    }
  }
  
  console.log("Processed result:", result);
  
  return result.length > 0 ? result : text;
};

const Chat = () => {
  const [message, setMessage] = useState('');
  const [debouncedMessage, setDebouncedMessage] = useState('');
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [products, setProducts] = useState([]);
  const [backendConnected, setBackendConnected] = useState(true);
  const [isSending, setIsSending] = useState(false);

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);
  const typingTimeoutRef = useRef(null);

  useEffect(() => {
    const checkBackendConnection = async () => {
      try {
        // Try to fetch products with a timeout
        const timeoutPromise = new Promise((_, reject) => {
          setTimeout(() => reject(new Error('Connection timeout')), 5000);
        });
        
        await Promise.race([getAllProducts(), timeoutPromise]);
        setBackendConnected(true);
      } catch (error) {
        console.error('Backend connection check failed:', error);
        setBackendConnected(false);
        
        // Add error message to conversation
        setConversation(prev => [...prev, {
          text: "Sorry, I'm having trouble connecting to the server right now. Please try again later.",
          sender: 'bot',
          type: 'error'
        }]);
      }
    };
    
    // Check connection immediately and set up periodic checks
    checkBackendConnection();
    const intervalId = setInterval(checkBackendConnection, 30000); // Check every 30 seconds
    
    return () => clearInterval(intervalId); // Cleanup on unmount
  }, []);

  // Auto-scroll to bottom when conversation updates
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation]);

  // Debounce message updates to prevent excessive API calls
  useEffect(() => {
    // Clear any existing timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    
    // Only update debounced message after user stops typing for 500ms
    // and only if we're not currently sending a message
    if (!isSending) {
      typingTimeoutRef.current = setTimeout(() => {
        setDebouncedMessage(message);
      }, 500);
    }
    
    return () => {
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
    };
  }, [message, isSending]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim() || isSending) return;
    
    // Set sending flag to true to prevent multiple submissions
    setIsSending(true);
    
    // Cancel any pending typing timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
    }
    
    // Add user message to conversation
    setConversation(prev => [...prev, { 
      text: message, 
      sender: 'user',
      type: 'text'
    }]);
    
    // Clear message input immediately
    const messageCopy = message;
    setMessage('');
    
    setLoading(true);
    
    try {
      // Send the message to the backend
      const response = await chatWithAgent(messageCopy);
      
      // Check if we have a valid response
      if (!response || (!response.text && !response.response && !response.recommendations)) {
        throw new Error('Invalid response from server');
      }
      
      // Get the text from the response (handle different API formats)
      const responseText = response.text || response.response || '';
      
      // Check if this is a recommendation request
      const isRecommendation = response.is_recommendation || 
                              (response.recommendations && response.recommendations.length > 0);
      
      // Get products from response
      const responseProducts = response.recommendations || [];
      
      // Always add a text response for context
      let displayText = responseText;
      
      // If we have product recommendations but no text (or generic text),
      // create a more informative message based on the products
      if (isRecommendation && responseProducts.length > 0) {
        // Check if products are all from the same category
        const productCategories = responseProducts.map(p => p.category?.toLowerCase());
        const uniqueCategories = [...new Set(productCategories)];
        
        // Detect if this is a complementary product recommendation
        const isComplementaryQuery = messageCopy.toLowerCase().includes("go with") || 
                                     messageCopy.toLowerCase().includes("pair with") ||
                                     messageCopy.toLowerCase().includes("match with") ||
                                     messageCopy.toLowerCase().includes("wear with") ||
                                     messageCopy.toLowerCase().includes("complement") ||
                                     (uniqueCategories.length > 0 && 
                                      !uniqueCategories.some(cat => 
                                        messageCopy.toLowerCase().includes(cat.toLowerCase())));
        
        // If the response text is empty or very generic, enhance it
        if (!displayText || displayText === "Here are the products you requested:") {
          // Extract the query type from the user message
          const queryLower = messageCopy.toLowerCase();
          const isComfortQuery = queryLower.includes("comfortable") || queryLower.includes("comfort");
          const isPopularQuery = queryLower.includes("popular") || queryLower.includes("best");
          
          // Create more specific responses based on query type and product categories
          if (isComplementaryQuery) {
            // For complementary queries
            const categoryText = uniqueCategories.length > 2 
              ? `${uniqueCategories.slice(0, -1).join(', ')} and ${uniqueCategories[uniqueCategories.length - 1]}`
              : uniqueCategories.join(' and ');
              
            // Extract what we're complementing
            let mainItem = "item";
            if (queryLower.includes("pants")) mainItem = "pants";
            else if (queryLower.includes("shirt")) mainItem = "shirt";
            else if (queryLower.includes("jacket")) mainItem = "jacket";
            else if (queryLower.includes("skirt")) mainItem = "skirt";
              
            displayText = `Here are some ${categoryText} that would go perfectly with your ${mainItem}:`;
          }
          else if (uniqueCategories.length === 1) {
            const category = uniqueCategories[0];
            if (isComfortQuery) {
              displayText = `Here are our most comfortable ${category} options that customers love:`;
            } else if (isPopularQuery) {
              displayText = `These are our most popular ${category} with the highest ratings:`;
            } else {
              displayText = `Here are some great ${category} options that match your request:`;
            }
          } else {
            // Multiple categories
            if (isComfortQuery) {
              displayText = `I've found some comfortable options for you to consider:`;
            } else if (isPopularQuery) {
              displayText = `Here are some of our highest-rated items:`;
            } else {
              const categoryText = uniqueCategories.length > 2 
                ? `${uniqueCategories.slice(0, -1).join(', ')} and ${uniqueCategories[uniqueCategories.length - 1]}`
                : uniqueCategories.join(' and ');
              displayText = `I've found a selection of ${categoryText} for you:`;
            }
          }
        }
        
        // Add bot response with products
        setConversation(prev => [...prev, { 
          text: displayText, 
          sender: 'bot',
          type: 'text',
          products: responseProducts,
          isComplementary: isComplementaryQuery
        }]);
        
        // Update products state
        setProducts(responseProducts);
      } else {
        // Just a regular text response without products
        setConversation(prev => [...prev, { 
          text: displayText || "I'm not sure I understand. Could you try rephrasing that?", 
          sender: 'bot',
          type: 'text'
        }]);
      }
    } catch (error) {
      console.error('Chat error:', error);
      setConversation(prev => [...prev, { 
        text: 'Sorry, I encountered an error connecting to our AI service. Please try again in a moment.', 
        sender: 'bot',
        type: 'text'
      }]);
    } finally {
      setLoading(false);
      setIsSending(false);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      
      // Show the selected image in the chat
      const reader = new FileReader();
      reader.onload = (event) => {
        setConversation(prev => [...prev, { 
          sender: 'user', 
          type: 'image',
          imageUrl: event.target.result,
          text: 'Find products similar to this image'
        }]);
      };
      reader.readAsDataURL(file);
      
      // Call handleImageSearch with the file
      handleImageSearch(file);
    }
  };

  const handleImageSearch = async (file) => {
    setLoading(true);

    try {
      const results = await searchByImage(file);
      
      if (!results || !results.results) {
        throw new Error('Invalid response from image search');
      }
      
      // Check if the results contain an error message
      if (results.results.length === 1 && results.results[0].error) {
        const errorMessage = results.results[0].error;
        console.log("Image search error:", errorMessage);
        
        setConversation(prev => [...prev, {
          text: `We couldn't find similar products. We will add this soon!`,
          sender: 'bot',
          type: 'text'
        }]);
        return;
      }
      
      if (results.results.length === 0) {
        setConversation(prev => [...prev, {
          text: "We don't have this product right now, but check back with us later!",
          sender: 'bot',
          type: 'text'
        }]);
      } else {
        setConversation(prev => [...prev, { 
          text: 'Here are some products similar to your image:', 
          sender: 'bot',
          type: 'text',
          products: results.results
        }]);
        
        // Update products state with the results
        setProducts(results.results);
      }
    } catch (error) {
      console.error('Image search error:', error);
      setConversation(prev => [...prev, { 
        text: 'Sorry, I had trouble finding similar products. Our image recognition service might be temporarily unavailable.', 
        sender: 'bot',
        type: 'text'
      }]);
    } finally {
      setLoading(false);
      setSelectedFile(null);
    }
  };

  const handleProductClick = (productId) => {
    alert(`Viewing product ${productId}. Product details page coming soon!`);
  };

  const handleImageButtonClick = () => {
    fileInputRef.current.click();
  };

  const getProductImageUrl = (product) => {
    // If product is invalid, return placeholder
    if (!product) {
      return `https://via.placeholder.com/100/CCCCCC/000000?text=Missing`;
    }
    
    // If API provides a full URL, use it
    if (product.image_url) {
      try {
        const imageUrl = `${API_URL}${product.image_url.startsWith('/') ? product.image_url : '/' + product.image_url}`;
        return imageUrl;
      } catch (error) {
        console.error("Error processing image URL:", error);
      }
    }
    
    // If there's an image filename, construct URL
    if (product.image_filename) {
      return `${API_URL}/images/${product.image_filename}`;
    }
    
    // Use a placeholder as fallback
    const placeholderText = product.name || 'Product';
    return `https://via.placeholder.com/100/CCCCCC/000000?text=${encodeURIComponent(placeholderText)}`;
  };

  const renderSuggestedQuestions = () => {
    // Generate contextual suggested questions based on conversation
    let questions = [];
    const lastMessage = conversation[conversation.length - 1];
    
    if (lastMessage?.products && lastMessage.products.length > 0) {
      // Product-related questions based on specific categories
      const productCategories = [...new Set(lastMessage.products.map(p => p.category?.toLowerCase() || 'product'))];
      const mainCategory = productCategories[0] || 'product';

      // Generic product questions
      questions = [
        `What's your best-selling ${mainCategory}?`,
        `Do you have ${mainCategory} in different styles?`,
        `What would you recommend to go with this ${mainCategory}?`,
        `What's the best ${mainCategory} material for summer?`
      ]
      
      // Add a seasonal question based on current month
      const currentMonth = new Date().getMonth();
      if (currentMonth >= 3 && currentMonth <= 4) { // Spring (Apr-May)
        questions.push(`What ${mainCategory} are perfect for spring?`);
      } else if (currentMonth >= 5 && currentMonth <= 7) { // Summer (Jun-Aug)
        questions.push(`Do you have ${mainCategory} good for hot weather?`);
      } else if (currentMonth >= 8 && currentMonth <= 10) { // Fall (Sep-Nov)
        questions.push(`What ${mainCategory} work well for fall layering?`);
      } else { // Winter (Dec-Mar)
        questions.push(`Do you have warmer ${mainCategory} for cold weather?`);
      }
      
      // Shuffle and get 3 random questions
      questions = shuffleArray(questions).slice(0, 3);
      
    } else {
      // If no products in last message, use category-based recommendations
      const categories = ['t-shirts', 'pants', 'skirts'];
      const randomCategory = categories[Math.floor(Math.random() * categories.length)];
      
      // General discovery questions
      questions = [
        `Show me your most popular ${randomCategory}`,
        `What are your best-selling products?`,
        `Do you have any recommendations for summer?`
      ];
      
      // Add a shopping question based on the season
      const currentMonth = new Date().getMonth();
      if (currentMonth >= 3 && currentMonth <= 4) { // Spring
        questions.push(`What's trending this spring?`);
      } else if (currentMonth >= 5 && currentMonth <= 7) { // Summer
        questions.push(`What's good for hot weather?`);
      } else if (currentMonth >= 8 && currentMonth <= 10) { // Fall
        questions.push(`What do you recommend for fall?`);
      } else { // Winter
        questions.push(`What's in style this winter?`);
      }
      
      // Add a policy-related question occasionally
      if (Math.random() > 0.7) {
        questions.push(`What are your store policies?`);
      }
      
      // Shuffle and get 3 random questions
      questions = shuffleArray(questions).slice(0, 3);
    }
    
    return questions;
  };
  
  // Helper function to shuffle array
  const shuffleArray = (array) => {
    const newArray = [...array];
    for (let i = newArray.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [newArray[i], newArray[j]] = [newArray[j], newArray[i]];
    }
    return newArray;
  };

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {conversation.length === 0 && (
          <div className="welcome-message">
            <h3>Hello! I'm Palona</h3>
            <p>I can help you find products or answer questions about our store.</p>
            <p>You can also upload an image to find similar products!</p>
          </div>
        )}
        
        {conversation.map((msg, idx) => (
          <div key={idx} className={`message-container ${msg.sender}`}>
            <div className={`message ${msg.sender}`}>
              {msg.type === 'image' ? (
                <div className="message-image">
                  <img src={msg.imageUrl} alt="Uploaded" />
                  <p>{msg.text}</p>
                </div>
              ) : (
                <div className="message-text">
                  {msg.text.split('\n').map((paragraph, i) => {
                    // Check if line is a numbered list item (1. Text)
                    if (/^\d+\.\s+/.test(paragraph)) {
                      // Process bold text within numbered list items
                      const content = processBoldText(paragraph);
                      return <p key={i} className="list-item numbered">{content}</p>;
                    }
                    // Check if line is a bullet point (• Text or * Text)
                    else if (/^[•\*]\s+/.test(paragraph)) {
                      // Process bold text within bullet list items
                      const content = processBoldText(paragraph);
                      return <p key={i} className="list-item bulleted">{content}</p>;
                    }
                    // Regular paragraph
                    else if (paragraph.trim() !== '') {
                      // Process bold text
                      return <p key={i}>{processBoldText(paragraph)}</p>;
                    }
                    // Empty line
                    return <br key={i} />;
                  })}
                </div>
              )}
            </div>
            
            {msg.products && (
              <div className="product-recommendations">
                {msg.products.length > 0 ? (
                  msg.products.map(product => {
                    // Skip products with missing essential data
                    if (!product || !product.id || product.error) {
                      return null;
                    }
                    
                    return (
                      <div 
                        key={product.id} 
                        className="product-card" 
                        onClick={() => handleProductClick(product.id)}
                      >
                        <div className="product-image">
                          <img 
                            src={getProductImageUrl(product)}
                            alt={product.name || 'Product'}
                            onError={(e) => { 
                              e.target.src = `https://via.placeholder.com/100/CCCCCC/000000?text=${encodeURIComponent(product.name || 'Product')}`;
                            }}
                          />
                        </div>
                        <div className="product-info">
                          <h4>{product.name || 'Unnamed Product'}</h4>
                          <div className="product-meta">
                            <span className="product-price">${product.price || '0.00'}</span>
                            <span className="product-rating">★ {product.rating || '0.0'}</span>
                          </div>
                          <span className="view-details">View details →</span>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="no-products-message">
                    No products found matching your search.
                  </div>
                )}
              </div>
            )}
            
            {idx === conversation.length - 1 && msg.sender === 'bot' && (
              <div className="suggested-questions">
                {renderSuggestedQuestions().map((question, i) => (
                  <button 
                    key={i} 
                    className="suggested-question"
                    onClick={() => {
                      setMessage(question);
                      setTimeout(() => handleSubmit({ preventDefault: () => {} }), 100);
                    }}
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        
        {loading && (
          <div className="message-container bot">
            <div className="message bot loading">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={chatEndRef} />
      </div>
      
      <div className="chat-input-container">
        <form onSubmit={handleSubmit} className="chat-input-form">
          <button 
            type="button" 
            className="image-upload-button"
            onClick={handleImageButtonClick}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 16l4-4 4 4" />
              <path d="M5 9h3V4h8v5h3" />
              <rect x="2" y="16" width="20" height="6" rx="2" />
            </svg>
          </button>
          <input
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            ref={fileInputRef}
            style={{ display: 'none' }}
          />
          
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Ask about our products..."
            className="chat-text-input"
          />
          
          <button 
            type="submit" 
            disabled={loading || !message.trim() || isSending} 
            className="send-button"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 2L11 13" />
              <path d="M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
};

export default Chat;