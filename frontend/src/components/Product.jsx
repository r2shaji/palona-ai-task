import React from 'react';
import { API_URL } from '../api';

const Product = ({ product }) => {
  const getProductImageUrl = (product) => {
    // If API provides a full URL, use it
    if (product.image_url) {
      // Don't try to modify the URL if it's already a complete URL
      if (product.image_url.startsWith('http')) {
        return product.image_url;
      }
      // Otherwise append the API_URL
      return `${API_URL}${product.image_url.startsWith('/') ? product.image_url : '/' + product.image_url}`;
    }
    
    // If the backend provides a filename, construct the URL
    if (product.image_filename) {
      return `${API_URL}/images/${product.image_filename}`;
    }
    
    // Use a placeholder as fallback
    return 'https://via.placeholder.com/100/CCCCCC/000000?text=Product';
  };

  return (
    <div className="product-image">
      <img 
        src={getProductImageUrl(product)}
        alt={product.name}
        onError={(e) => { 
          e.target.src = 'https://via.placeholder.com/100/CCCCCC/000000?text=Product';
        }}
      />
    </div>
  );
};

export default Product;