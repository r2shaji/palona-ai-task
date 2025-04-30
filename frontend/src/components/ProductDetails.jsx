// frontend/src/components/ProductDetails.jsx
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getProductById } from '../api';

const ProductDetails = () => {
  const { productId } = useParams();
  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  
  useEffect(() => {
    const fetchProduct = async () => {
      try {
        const data = await getProductById(productId);
        setProduct(data.product);
      } catch (error) {
        console.error('Error fetching product details:', error);
        setError('Could not load product details');
      } finally {
        setLoading(false);
      }
    };
    
    fetchProduct();
  }, [productId]);
  
  if (loading) return <div className="loading-spinner">Loading product details...</div>;
  if (error) return <div className="error-message">{error}</div>;
  if (!product) return <div className="error-message">Product not found</div>;
  
  return (
    <div className="product-details">
      <button className="back-button" onClick={() => navigate(-1)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M19 12H5" />
          <path d="M12 19l-7-7 7-7" />
        </svg>
        Back
      </button>
      
      <div className="product-detail-layout">
        <div className="product-detail-image">
          <img 
            src={`/api/images/${product.image_filename}`} 
            alt={product.name}
            onError={(e) => { e.target.src = '/placeholder-image.jpg' }}
          />
        </div>
        
        <div className="product-detail-content">
          <h1 className="product-title">{product.name}</h1>
          
          <div className="product-meta-large">
            <div className="price-rating">
              <span className="product-price-large">${product.price}</span>
              <span className="product-rating-large">★ {product.rating}</span>
            </div>
            <span className="product-category">{product.category}</span>
          </div>
          
          <div className="product-description">
            <h3>About this item</h3>
            <p>{product.description}</p>
          </div>
          
          <div className="product-actions">
            <button className="add-to-cart-button">Add to Cart</button>
            <button className="buy-now-button">Buy Now</button>
          </div>
          
          <div className="ask-about-product">
            <h3>Questions about this product?</h3>
            <button 
              className="ask-question-button"
              onClick={() => {
                navigate('/');
                // You'd want to add logic to pre-fill the chat with a question about this product
              }}
            >
              Chat with Palona
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProductDetails;