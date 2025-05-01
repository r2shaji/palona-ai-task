// frontend/src/api.js
export const API_URL = (process.env.REACT_APP_API_URL ? process.env.REACT_APP_API_URL + '/api' : 'http://localhost:5001/api')
console.log("API_URL is:", API_URL, process.env.REACT_APP_API_URL );
// Add this for debugging
const logApiCall = (endpoint, success, data = null, error = null) => {
  console.log(`API ${endpoint} - ${success ? 'SUCCESS' : 'ERROR'}`, 
              success ? data : error);
};

export const checkHealth = async () => {
  console.log(`Checking API health at ${API_URL}/health`);
  try {
    const response = await fetch(`${API_URL}/health`);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API Health Error (${response.status}): ${errorText}`);
      throw new Error(`API health error: ${response.status} - ${errorText}`);
    }
    
    const data = await response.json();
    logApiCall('checkHealth', true, data);
    return data;
  } catch (error) {
    logApiCall('checkHealth', false, null, error);
    throw error;
  }
};

export const chatWithAgent = async (message) => {
  console.log(`Sending chat request to ${API_URL}/chat`);
  try {
    const response = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API Error (${response.status}): ${errorText}`);
      throw new Error(`API error: ${response.status} - ${errorText}`);
    }
    
    const data = await response.json();
    logApiCall('chatWithAgent', true, data);
    return data;
  } catch (error) {
    logApiCall('chatWithAgent', false, null, error);
    throw error;
  }
};

export const searchByImage = async (imageFile) => {
  console.log(`Sending image search request to ${API_URL}/search_by_image`);
  try {
    const formData = new FormData();
    formData.append('image', imageFile);
    
    const response = await fetch(`${API_URL}/search_by_image`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API Error (${response.status}): ${errorText}`);
      throw new Error(`API error: ${response.status} - ${errorText}`);
    }
    
    const data = await response.json();
    logApiCall('searchByImage', true, data);
    return data;
  } catch (error) {
    logApiCall('searchByImage', false, null, error);
    throw error;
  }
};

export const getAllProducts = async () => {
  console.log(`Fetching all products from ${API_URL}/products`);
  try {
    const response = await fetch(`${API_URL}/products`);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API Error (${response.status}): ${errorText}`);
      throw new Error(`API error: ${response.status} - ${errorText}`);
    }
    
    const data = await response.json();
    logApiCall('getAllProducts', true, data);
    return data;
  } catch (error) {
    logApiCall('getAllProducts', false, null, error);
    throw error;
  }
};