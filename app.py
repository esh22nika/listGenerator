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
        response_text = response.text.strip()
        
        # Clean the response to get just the JSON
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
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
                    if 'name' not in item:
                        item['name'] = 'Unknown Item'
                    if 'price' not in item:
                        item['price'] = 0
                    if 'desc' not in item:
                        item['desc'] = 'Delicious and fresh'
                # Ensure price is a number
                if isinstance(item['price'], str):
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
    
    fallback_menu = {"Menu Items": []}
    price_pattern = r'₹?(\d+)'
    prices = re.findall(price_pattern, menu_text)
    
    lines = menu_text.split('\n')
    items = []
    
    for line in lines:
        line = line.strip()
        if line and not line.isdigit() and '₹' not in line and len(line) > 2:
            skip_words = ['ORDER', 'ONLINE', 'STREET', 'CITY', 'PHONE', '+', 'REALLYGREATSITE', 'COM']
            if not any(word in line.upper() for word in skip_words):
                items.append(line)
    
    for i, item in enumerate(items[:len(prices)]):
        price = int(prices[i]) if i < len(prices) else 50
        fallback_menu["Menu Items"].append({
            "name": item.title(),
            "price": price,
            "desc": "Freshly prepared dish"
        })
    
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
            temp_fd, temp_file_path = tempfile.mkstemp(suffix='.pdf')
            
            with os.fdopen(temp_fd, 'wb') as temp_file:
                file.save(temp_file)
            
            menu_text = extract_text_from_pdf(temp_file_path)
            
            print("=== EXTRACTED TEXT ===")
            print(repr(menu_text))
            print("=== END EXTRACTED TEXT ===")
            
            if not menu_text:
                return jsonify({'error': 'Could not extract text from PDF'}), 400
            
            structured_menu = structure_menu_with_gemini(menu_text)
            
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
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
    
    return jsonify({'error': 'Please upload a valid PDF file'}), 400

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    if not os.path.exists('static/css'):
        os.makedirs('static/css')
    if not os.path.exists('static/js'):
        os.makedirs('static/js')
    
    app.run(debug=True)