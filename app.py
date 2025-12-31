from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import db, User, Service, Menu, Cart, Order, OrderItem
from datetime import datetime
import os
from PIL import Image
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['UPLOAD_FOLDER'] = 'static/uploads/profile_pics'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Allowed extensions for images
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Initialize extensions
db.init_app(app)
Session(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_profile_pic(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to make filename unique
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        
        # Create directory if not exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Save file
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Resize image if needed
        img = Image.open(filepath)
        img.thumbnail((300, 300))
        img.save(filepath)
        
        return filename
    return None

# Create tables
with app.app_context():
    db.create_all()

# Login required decorator
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== ROUTES ==========

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        full_name = request.form.get('full_name')
        mobile = request.form.get('mobile')
        email = request.form.get('email')
        location = request.form.get('location')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))
        
        # Check if user already exists
        if User.query.filter_by(mobile=mobile).first():
            flash('Mobile number already registered!', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'error')
            return redirect(url_for('register'))
        
        # Handle profile picture upload
        profile_pic = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file.filename != '':
                profile_pic = save_profile_pic(file)
        
        # Hash password
        hashed_password = generate_password_hash(password)
        
        # Create new user
        new_user = User(
            full_name=full_name,
            mobile=mobile,
            email=email,
            location=location,
            latitude=latitude,
            longitude=longitude,
            password=hashed_password,
            profile_pic=profile_pic
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        
        user = User.query.filter_by(mobile=mobile).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            session['profile_pic'] = user.profile_pic
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid mobile number or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    return render_template('dashboard.html', user=user)

@app.route('/services')
@login_required
def services():
    active_services = Service.query.filter_by(status='active').all()
    return render_template('service.html', services=active_services)

@app.route('/menu')
@login_required
def menu():
    active_menu = Menu.query.filter_by(status='active').all()
    return render_template('menu.html', menu_items=active_menu)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    item_type = request.form.get('item_type')
    item_id = request.form.get('item_id')
    quantity = request.form.get('quantity', 1)
    
    # Check if item already in cart
    existing = Cart.query.filter_by(
        user_id=session['user_id'],
        item_type=item_type,
        item_id=item_id
    ).first()
    
    if existing:
        existing.quantity += int(quantity)
    else:
        new_item = Cart(
            user_id=session['user_id'],
            item_type=item_type,
            item_id=item_id,
            quantity=quantity
        )
        db.session.add(new_item)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/cart')
@login_required
def cart():
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    
    items_data = []
    total_amount = 0
    
    for item in cart_items:
        if item.item_type == 'service':
            product = Service.query.get(item.item_id)
        else:
            product = Menu.query.get(item.item_id)
        
        if product:
            item_total = product.final_price * item.quantity
            total_amount += item_total
            
            items_data.append({
                'id': item.id,
                'product': product,
                'type': item.item_type,
                'quantity': item.quantity,
                'total': item_total
            })
    
    return render_template('cart.html', cart_items=items_data, total=total_amount)

@app.route('/remove_from_cart/<int:item_id>')
@login_required
def remove_from_cart(item_id):
    item = Cart.query.get(item_id)
    if item and item.user_id == session['user_id']:
        db.session.delete(item)
        db.session.commit()
        flash('Item removed from cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout')
@login_required
def checkout():
    user = User.query.get(session['user_id'])
    return render_template('order_form.html', user=user)

@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    user_id = session['user_id']
    delivery_location = request.form.get('delivery_location')
    payment_mode = request.form.get('payment_mode')
    
    # Get cart items
    cart_items = Cart.query.filter_by(user_id=user_id).all()
    
    if not cart_items:
        flash('Your cart is empty!', 'error')
        return redirect(url_for('cart'))
    
    # Calculate total amount
    total_amount = 0
    for item in cart_items:
        if item.item_type == 'service':
            product = Service.query.get(item.item_id)
        else:
            product = Menu.query.get(item.item_id)
        
        if product:
            total_amount += product.final_price * item.quantity
    
    # Create order
    new_order = Order(
        user_id=user_id,
        total_amount=total_amount,
        payment_mode=payment_mode,
        delivery_location=delivery_location,
        order_status='Pending'
    )
    db.session.add(new_order)
    db.session.flush()  # Get order ID
    
    # Add order items
    for item in cart_items:
        if item.item_type == 'service':
            product = Service.query.get(item.item_id)
        else:
            product = Menu.query.get(item.item_id)
        
        if product:
            order_item = OrderItem(
                order_id=new_order.id,
                item_type=item.item_type,
                item_id=item.item_id,
                quantity=item.quantity,
                price=product.final_price
            )
            db.session.add(order_item)
    
    # Clear cart
    Cart.query.filter_by(user_id=user_id).delete()
    
    db.session.commit()
    
    flash('Order placed successfully!', 'success')
    return redirect(url_for('order_history'))

@app.route('/order_history')
@login_required
def order_history():
    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.order_date.desc()).all()
    return render_template('order_history.html', orders=orders)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # Update user data
        user.full_name = request.form.get('full_name')
        user.email = request.form.get('email')
        user.location = request.form.get('location')
        
        # Handle password change
        new_password = request.form.get('new_password')
        if new_password:
            user.password = generate_password_hash(new_password)
        
        # Handle profile picture update
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file.filename != '':
                # Delete old picture if exists
                if user.profile_pic:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], user.profile_pic)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new picture
                new_pic = save_profile_pic(file)
                if new_pic:
                    user.profile_pic = new_pic
        
        db.session.commit()
        
        # Update session
        session['user_name'] = user.full_name
        session['profile_pic'] = user.profile_pic
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user)

# API for getting service/menu details
@app.route('/get_item_details/<item_type>/<int:item_id>')
@login_required
def get_item_details(item_type, item_id):
    if item_type == 'service':
        item = Service.query.get(item_id)
    else:
        item = Menu.query.get(item_id)
    
    if item:
        return jsonify({
            'name': item.name,
            'photo': item.photo,
            'original_price': item.original_price,
            'discount': item.discount,
            'final_price': item.final_price,
            'description': item.short_description if hasattr(item, 'short_description') else item.description
        })
    
    return jsonify({'error': 'Item not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)