from flask import Flask, render_template, request, jsonify, redirect, url_for
import pdfplumber
import google.generativeai as genai
import json
import os
from werkzeug.utils import secure_filename
import tempfile

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure Gemini API
# Set your API key as environment variable: GEMINI_API_KEY
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyDfdxDrJkA6Cql442cOLVPageiYoEzZGEE')
genai.configure(api_key=GEMINI_API_KEY)

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using pdfplumber"""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text if text.strip() else None
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return None

def structure_menu_with_gemini(menu_text):
    """Use Gemini to structure the menu text into JSON format"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        You are an expert restaurant menu parser. Analyze the following menu text which may have mixed formatting, separated prices, or unclear structure.

        IMPORTANT INSTRUCTIONS:
        1. Extract ALL menu items and their prices, even if they appear separated in the text
        2. Group items by their category headings (like "STARTERS", "MAIN COURSE", "DESSERTS", etc.)
        3. If prices appear as ₹XX or just numbers, extract the numeric value
        4. Create logical categories if none are explicitly mentioned
        5. Generate appropriate descriptions for items (keep them brief and appetizing)
        6. Handle ANY menu format - prices can be before/after items, in separate lines, etc.

        OUTPUT FORMAT: Return ONLY valid JSON in this exact structure:
        {{
          "Category Name": [
            {{"name": "Item Name", "price": 100, "desc": "Brief description"}},
            {{"name": "Another Item", "price": 150, "desc": "Another description"}}
          ],
          "Another Category": [...]
        }}

        MENU TEXT TO PARSE:
        {menu_text}

        Remember: 
        - Extract ALL items you can identify
        - Match items with their prices (even if separated)
        - Create reasonable descriptions
        - Use proper category names
        - Return ONLY the JSON, no explanations
        """
        
        response = model.generate_content(prompt)
        
        # Clean the response to get just the JSON
        response_text = response.text.strip()
        
        # Remove markdown formatting if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # Parse JSON
        menu_json = json.loads(response_text)
        
        # Validate the structure
        if not isinstance(menu_json, dict):
            raise ValueError("Invalid JSON structure")
        
        # Ensure all items have required fields
        for category, items in menu_json.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not all(key in item for key in ['name', 'price', 'desc']):
                    # Fill missing fields
                    if 'name' not in item:
                        item['name'] = 'Unknown Item'
                    if 'price' not in item:
                        item['price'] = 0
                    if 'desc' not in item:
                        item['desc'] = 'Delicious and fresh'
                # Ensure price is a number
                if isinstance(item['price'], str):
                    # Extract number from price string
                    import re
                    price_match = re.search(r'\d+', str(item['price']))
                    item['price'] = int(price_match.group()) if price_match else 0
        
        return menu_json
        
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print(f"Gemini response was: {response_text[:500]}...")
        return create_fallback_menu(menu_text)
    except Exception as e:
        print(f"Error with Gemini API: {e}")
        return create_fallback_menu(menu_text)

def create_fallback_menu(menu_text):
    """Create a fallback menu structure if Gemini fails"""
    import re
    
    # Try to extract items and prices using regex
    fallback_menu = {"Menu Items": []}
    
    # Look for price patterns (₹XX or numbers)
    price_pattern = r'₹?(\d+)'
    prices = re.findall(price_pattern, menu_text)
    
    # Look for potential item names (words/phrases before prices or in caps)
    lines = menu_text.split('\n')
    items = []
    
    for line in lines:
        line = line.strip()
        if line and not line.isdigit() and '₹' not in line and len(line) > 2:
            # Skip obvious non-menu items
            skip_words = ['ORDER', 'ONLINE', 'STREET', 'CITY', 'PHONE', '+', 'REALLYGREATSITE', 'COM']
            if not any(word in line.upper() for word in skip_words):
                items.append(line)
    
    # Combine items with prices
    for i, item in enumerate(items[:len(prices)]):
        price = int(prices[i]) if i < len(prices) else 50
        fallback_menu["Menu Items"].append({
            "name": item.title(),
            "price": price,
            "desc": "Freshly prepared dish"
        })
    
    # If no items found, create a basic menu
    if not fallback_menu["Menu Items"]:
        fallback_menu["Menu Items"] = [
            {
                "name": "Menu Item",
                "price": 100,
                "desc": "Unable to parse menu completely. Please try with a clearer PDF."
            }
        ]
    
    return fallback_menu

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['pdf_file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.lower().endswith('.pdf'):
        temp_file_path = None
        try:
            # Create temp file
            temp_fd, temp_file_path = tempfile.mkstemp(suffix='.pdf')
            
            # Save uploaded file to temp location
            with os.fdopen(temp_fd, 'wb') as temp_file:
                file.save(temp_file)
            
            # Extract text from PDF
            menu_text = extract_text_from_pdf(temp_file_path)
            
            # Debug: Print extracted text
            print("=== EXTRACTED TEXT ===")
            print(repr(menu_text))
            print("=== END EXTRACTED TEXT ===")
            
            if not menu_text:
                return jsonify({'error': 'Could not extract text from PDF'}), 400
            
            # Structure with Gemini
            structured_menu = structure_menu_with_gemini(menu_text)
            
            # Debug: Print structured menu
            print("=== STRUCTURED MENU ===")
            print(json.dumps(structured_menu, indent=2))
            print("=== END STRUCTURED MENU ===")
            
            return jsonify({
                'success': True,
                'menu': structured_menu
            })
                
        except Exception as e:
            print(f"Full error details: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Error processing file: {str(e)}'}), 500
        finally:
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass  # Ignore cleanup errors
    
    return jsonify({'error': 'Please upload a valid PDF file'}), 400

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Create the HTML template
    html_template = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Restaurant Menu Parser</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        .main-container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            margin: 20px auto;
            max-width: 1200px;
            overflow: hidden;
        }
        
        .upload-section {
            background: linear-gradient(45deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 40px;
            text-align: center;
        }
        
        .upload-area {
            border: 3px dashed rgba(255,255,255,0.5);
            border-radius: 15px;
            padding: 40px;
            margin: 20px 0;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .upload-area:hover {
            border-color: white;
            background: rgba(255,255,255,0.1);
        }
        
        .menu-section {
            padding: 30px;
        }
        
        .category-header {
            background: linear-gradient(45deg, #4CAF50, #45a049);
            color: white;
            padding: 15px 25px;
            border-radius: 10px;
            margin: 25px 0 15px 0;
            font-weight: bold;
            font-size: 1.2em;
        }
        
        .menu-item {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 15px;
            padding: 20px;
            margin: 15px 0;
            transition: all 0.3s ease;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .menu-item:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
        }
        
        .item-name {
            font-weight: bold;
            font-size: 1.1em;
            color: #2c3e50;
            margin-bottom: 8px;
        }
        
        .item-desc {
            color: #7f8c8d;
            margin-bottom: 15px;
            font-size: 0.9em;
        }
        
        .item-price {
            color: #e74c3c;
            font-weight: bold;
            font-size: 1.2em;
        }
        
        .quantity-controls {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 15px 0;
        }
        
        .qty-btn {
            background: #3498db;
            color: white;
            border: none;
            border-radius: 50%;
            width: 35px;
            height: 35px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.3s ease;
        }
        
        .qty-btn:hover {
            background: #2980b9;
            transform: scale(1.1);
        }
        
        .qty-display {
            background: white;
            border: 2px solid #3498db;
            border-radius: 5px;
            padding: 5px 15px;
            font-weight: bold;
            min-width: 50px;
            text-align: center;
        }
        
        .add-to-cart {
            background: linear-gradient(45deg, #FF6B6B, #FF8E53);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 10px 25px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
            margin-top: 10px;
        }
        
        .add-to-cart:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(255,107,107,0.4);
        }
        
        .cart-sidebar {
            position: fixed;
            right: -400px;
            top: 0;
            width: 400px;
            height: 100vh;
            background: white;
            box-shadow: -5px 0 15px rgba(0,0,0,0.1);
            transition: right 0.3s ease;
            z-index: 1000;
            overflow-y: auto;
        }
        
        .cart-sidebar.open {
            right: 0;
        }
        
        .cart-header {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 20px;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .cart-toggle {
            position: fixed;
            right: 20px;
            bottom: 20px;
            background: linear-gradient(45deg, #FF6B6B, #FF8E53);
            color: white;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5em;
            cursor: pointer;
            box-shadow: 0 5px 15px rgba(255,107,107,0.4);
            z-index: 999;
            transition: all 0.3s ease;
        }
        
        .cart-toggle:hover {
            transform: scale(1.1);
        }
        
        .cart-badge {
            position: absolute;
            top: -5px;
            right: -5px;
            background: #e74c3c;
            color: white;
            border-radius: 50%;
            width: 25px;
            height: 25px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .cart-item {
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
        }
        
        .cart-total {
            background: #f8f9fa;
            padding: 20px;
            font-weight: bold;
            font-size: 1.2em;
        }
        
        .loading {
            text-align: center;
            padding: 50px;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #3498db;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        @media (max-width: 768px) {
            .cart-sidebar {
                width: 100%;
                right: -100%;
            }
            .main-container {
                margin: 10px;
                border-radius: 15px;
            }
            .upload-section {
                padding: 30px 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="main-container">
            <div class="upload-section" id="uploadSection">
                <h1><i class="fas fa-utensils"></i> Restaurant Menu Parser</h1>
                <p class="lead">Upload a PDF menu and we'll create an interactive menu for you!</p>
                
                <div class="upload-area" onclick="document.getElementById('pdfFile').click()">
                    <i class="fas fa-cloud-upload-alt fa-3x mb-3"></i>
                    <h4>Click to Upload PDF Menu</h4>
                    <p>Drag and drop or click to select your restaurant menu PDF</p>
                </div>
                
                <input type="file" id="pdfFile" accept=".pdf" style="display: none;">
                <button class="btn btn-light btn-lg mt-3" onclick="uploadFile()" id="uploadBtn">
                    <i class="fas fa-magic"></i> Parse Menu
                </button>
            </div>
            
            <div class="menu-section" id="menuSection" style="display: none;">
                <div id="menuContent"></div>
            </div>
            
            <div class="loading" id="loadingSection" style="display: none;">
                <div class="spinner"></div>
                <h4 class="mt-3">Processing your menu...</h4>
                <p>This may take a few moments</p>
            </div>
        </div>
    </div>
    
    <!-- Cart Sidebar -->
    <div class="cart-sidebar" id="cartSidebar">
        <div class="cart-header">
            <div class="d-flex justify-content-between align-items-center">
                <h4><i class="fas fa-shopping-cart"></i> Your Cart</h4>
                <button class="btn btn-light btn-sm" onclick="toggleCart()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
        <div id="cartItems"></div>
        <div class="cart-total" id="cartTotal">
            Total: ₹0
        </div>
    </div>
    
    <!-- Cart Toggle Button -->
    <button class="cart-toggle" onclick="toggleCart()" id="cartToggle" style="display: none;">
        <i class="fas fa-shopping-cart"></i>
        <span class="cart-badge" id="cartBadge">0</span>
    </button>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let cart = {};
        let cartCount = 0;
        let cartTotal = 0;
        
        function uploadFile() {
            const fileInput = document.getElementById('pdfFile');
            const file = fileInput.files[0];
            
            if (!file) {
                alert('Please select a PDF file first!');
                return;
            }
            
            const formData = new FormData();
            formData.append('pdf_file', file);
            
            // Show loading
            document.getElementById('uploadSection').style.display = 'none';
            document.getElementById('loadingSection').style.display = 'block';
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('loadingSection').style.display = 'none';
                
                if (data.success) {
                    displayMenu(data.menu);
                } else {
                    document.getElementById('uploadSection').style.display = 'block';
                    alert('Error: ' + data.error);
                }
            })
            .catch(error => {
                document.getElementById('loadingSection').style.display = 'none';
                document.getElementById('uploadSection').style.display = 'block';
                alert('Error uploading file: ' + error);
            });
        }
        
        function displayMenu(menu) {
            const menuContent = document.getElementById('menuContent');
            let html = '<h2 class="text-center mb-4"><i class="fas fa-utensils"></i> Menu</h2>';
            
            for (const [category, items] of Object.entries(menu)) {
                html += `<div class="category-header">
                    <i class="fas fa-list"></i> ${category}
                </div>`;
                
                items.forEach((item, index) => {
                    const itemId = `${category}_${index}`;
                    html += `
                        <div class="menu-item">
                            <div class="row">
                                <div class="col-md-8">
                                    <div class="item-name">${item.name}</div>
                                    <div class="item-desc">${item.desc}</div>
                                    <div class="item-price">₹${item.price}</div>
                                </div>
                                <div class="col-md-4">
                                    <div class="quantity-controls">
                                        <button class="qty-btn" onclick="changeQuantity('${itemId}', -1)">
                                            <i class="fas fa-minus"></i>
                                        </button>
                                        <div class="qty-display" id="qty_${itemId}">0</div>
                                        <button class="qty-btn" onclick="changeQuantity('${itemId}', 1)">
                                            <i class="fas fa-plus"></i>
                                        </button>
                                    </div>
                                    <button class="add-to-cart" onclick="addToCart('${itemId}', '${item.name}', ${item.price})">
                                        <i class="fas fa-cart-plus"></i> Add to Cart
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                });
            }
            
            menuContent.innerHTML = html;
            document.getElementById('menuSection').style.display = 'block';
            document.getElementById('cartToggle').style.display = 'flex';
        }
        
        function changeQuantity(itemId, change) {
            const qtyElement = document.getElementById(`qty_${itemId}`);
            let currentQty = parseInt(qtyElement.textContent);
            currentQty = Math.max(0, currentQty + change);
            qtyElement.textContent = currentQty;
        }
        
        function addToCart(itemId, itemName, itemPrice) {
            const qtyElement = document.getElementById(`qty_${itemId}`);
            const quantity = parseInt(qtyElement.textContent);
            
            if (quantity === 0) {
                alert('Please select quantity first!');
                return;
            }
            
            if (cart[itemId]) {
                cart[itemId].quantity += quantity;
            } else {
                cart[itemId] = {
                    name: itemName,
                    price: itemPrice,
                    quantity: quantity
                };
            }
            
            // Reset quantity display
            qtyElement.textContent = '0';
            
            updateCartDisplay();
        }
        
        function updateCartDisplay() {
            cartCount = 0;
            cartTotal = 0;
            let cartHtml = '';
            
            for (const [itemId, item] of Object.entries(cart)) {
                cartCount += item.quantity;
                cartTotal += item.price * item.quantity;
                
                cartHtml += `
                    <div class="cart-item">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <div class="fw-bold">${item.name}</div>
                                <div class="text-muted">₹${item.price} × ${item.quantity}</div>
                            </div>
                            <div>
                                <button class="btn btn-sm btn-outline-danger" onclick="removeFromCart('${itemId}')">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            if (cartCount === 0) {
                cartHtml = '<div class="cart-item text-center text-muted">Your cart is empty</div>';
            }
            
            document.getElementById('cartItems').innerHTML = cartHtml;
            document.getElementById('cartTotal').innerHTML = `Total: ₹${cartTotal}`;
            document.getElementById('cartBadge').textContent = cartCount;
        }
        
        function removeFromCart(itemId) {
            delete cart[itemId];
            updateCartDisplay();
        }
        
        function toggleCart() {
            const cartSidebar = document.getElementById('cartSidebar');
            cartSidebar.classList.toggle('open');
        }
        
        // File input change handler
        document.getElementById('pdfFile').addEventListener('change', function(e) {
            const fileName = e.target.files[0]?.name;
            if (fileName) {
                document.querySelector('.upload-area h4').textContent = fileName;
            }
        });
        
        // Drag and drop functionality
        const uploadArea = document.querySelector('.upload-area');
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.style.background = 'rgba(255,255,255,0.2)';
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.style.background = 'transparent';
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.style.background = 'transparent';
            
            const files = e.dataTransfer.files;
            if (files.length > 0 && files[0].type === 'application/pdf') {
                document.getElementById('pdfFile').files = files;
                document.querySelector('.upload-area h4').textContent = files[0].name;
            }
        });
    </script>
</body>
</html>'''
    
    # Write the HTML template
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(html_template)
    
    print("Flask app created! To run:")
    print("1. Install dependencies: pip install flask pdfplumber google-generativeai")
    print("2. Set your Gemini API key: export GEMINI_API_KEY='your-key-here'")
    print("3. Run: python app.py")
    print("4. Open http://localhost:5000")
    
    app.run(debug=True)