-- Insert sample brands
INSERT INTO brands (name, logo_url, website_url) VALUES 
('Palona', '/images/brands/palona.png', 'https://palona.com'),
('Comfort Wear', '/images/brands/comfort_wear.png', 'https://comfortwear.com'),
('Urban Style', '/images/brands/urban_style.png', 'https://urbanstyle.com');

-- Insert sample categories
INSERT INTO categories (name, description, parent_category_id) VALUES 
('Apparel', 'All clothing items', 1);

-- Insert subcategories under Apparel
INSERT INTO categories (name, description, parent_category_id) VALUES 
('T-Shirts', 'All types of t-shirts', 1),
('Pants', 'All types of pants', 1),
('Skirts', 'All types of skirts', 1);

-- Insert sample products for T-Shirts
INSERT INTO products (product_id, sku, name, description, brand_id, price, image_url, average_rating, rating_count) VALUES 
('tshirt-1', 'TSH001', 'Beige Classic Tee', 'A comfortable cotton t-shirt in beige for everyday wear', 1, 19.99, '/images/tee_beige.webp', 4.5, 120),
('tshirt-2', 'TSH002', 'Blue Casual Tee', 'Soft blue t-shirt with a comfortable fit', 2, 24.99, '/images/tee_blue.webp', 4.2, 85),
('tshirt-3', 'TSH003', 'Red Graphic Tee', 'Vibrant red t-shirt with modern design', 3, 22.99, '/images/tee_red.webp', 4.7, 95),
('tshirt-4', 'TSH004', 'White Basic Tee', 'Classic white t-shirt in breathable fabric', 1, 18.99, '/images/tee_white.webp', 4.6, 110),
('tshirt-5', 'TSH005', 'DBlack Basic Tee', 'Premium graphic t-shirt with unique design', 2, 29.99, '/images/tshirt_image_1.webp', 4.8, 75);

-- Insert sample products for Pants
INSERT INTO products (product_id, sku, name, description, brand_id, price, image_url, average_rating, rating_count) VALUES 
('pants-1', 'PNT001', 'Beige Casual Pants', 'Comfortable beige pants for everyday wear', 2, 39.99, '/images/pants_beige.webp', 4.3, 68),
('pants-2', 'PNT002', 'Black Slim Pants', 'Elegant black pants with modern slim fit', 3, 45.99, '/images/pants_black.webp', 4.5, 92),
('pants-3', 'PNT003', 'Blue Denim Pants', 'Classic blue denim pants with perfect fit', 1, 49.99, '/images/pants_blue.webp', 4.7, 105),
('pants-4', 'PNT004', 'Cargo Pants', 'Practical cargo pants with multiple pockets', 2, 42.99, '/images/pants_cargo.webp', 4.1, 58),
('pants-5', 'PNT005', 'Pink Fashion Pants', 'Trendy pink pants for a bold look', 3, 47.99, '/images/pants_pink.webp', 4.4, 62),
('pants-6', 'PNT006', 'Yellow Summer Pants', 'Bright yellow pants perfect for summer', 1, 38.99, '/images/pants_yellow.webp', 4.2, 45);

-- Insert sample products for Skirts
INSERT INTO products (product_id, sku, name, description, brand_id, price, image_url, average_rating, rating_count) VALUES 
('skirt-1', 'SKT001', 'Polka Dot Skirt', 'Playful skirt with dotted pattern', 3, 34.99, '/images/skirt_dotted.webp', 4.6, 78),
('skirt-2', 'SKT002', 'Green A-Line Skirt', 'Elegant green skirt with A-line cut', 1, 36.99, '/images/skirt_green.webp', 4.4, 65),
('skirt-3', 'SKT003', 'Denim Skirt', 'Classic denim skirt for casual wear', 2, 39.99, '/images/skirt_jeans.webp', 4.5, 87),
('skirt-4', 'SKT004', 'Pink Mini Skirt', 'Trendy pink mini skirt for a stylish look', 3, 32.99, '/images/skirt_pink.webp', 4.7, 92),
('skirt-5', 'SKT005', 'Purple Fashion Skirt', 'Elegant purple skirt for special occasions', 1, 38.99, '/images/skirt_purple.webp', 4.8, 78),
('skirt-6', 'SKT006', 'Red Flared Skirt', 'Vibrant red skirt with flared design', 2, 37.99, '/images/skirt_red.webp', 4.6, 83),
('skirt-7', 'SKT007', 'White Summer Skirt', 'Light white skirt perfect for summer', 3, 33.99, '/images/skirt_white.webp', 4.5, 75),
('skirt-8', 'SKT008', 'Classic Basic Skirt', 'Versatile skirt for any occasion', 1, 29.99, '/images/skirt.webp', 4.3, 69);

-- Assign products to categories
-- T-Shirts
INSERT INTO product_categories (product_id, category_id) VALUES 
('tshirt-1', 2), ('tshirt-2', 2), ('tshirt-3', 2), ('tshirt-4', 2), ('tshirt-5', 2);

-- Pants
INSERT INTO product_categories (product_id, category_id) VALUES 
('pants-1', 3), ('pants-2', 3), ('pants-3', 3), ('pants-4', 3), ('pants-5', 3), ('pants-6', 3);

-- Skirts
INSERT INTO product_categories (product_id, category_id) VALUES 
('skirt-1', 4), ('skirt-2', 4), ('skirt-3', 4), ('skirt-4', 4), ('skirt-5', 4), ('skirt-6', 4), ('skirt-7', 4), ('skirt-8', 4); 