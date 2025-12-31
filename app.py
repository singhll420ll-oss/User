import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
import io
from database import db, User, Service, Menu, Cart, Order, OrderItem
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_profile_picture(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to make filename unique
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Resize image to save space
        img = Image.open(file)
        img.thumbnail((500, 500))
        img.save(filepath)
        
        return filename
    return None

# Create database tables
with app.app_context():
    db.create_all()

# ========== 1️⃣ USER REGISTRATION SYSTEM ==========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        full_name = request.form.get('full_name')
        mobile = request.form.get('mobile')
        email = request.form.get('email')
        location = request.form.get('location')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))
        
        # Check if mobile or email already exists
        if User.query.filter_by(mobile=mobile).first():
            flash('Mobile number already registered!', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
        
        # Handle profile picture upload
        profile_pic = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file.filename:
                profile_pic = save_profile_picture(file)
        
        # Create new user
        new_user = User(
            full_name=full_name,
            mobile=mobile,
            email=email,
            location=location,
            profile_pic=profile_pic
        )
        new_user.password = password  # This will hash the password
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/get_location')
def get_location():
    # This endpoint would typically get location from browser/phone
    # For demo, we'll return a placeholder
    return jsonify({'location': 'Auto-detected location'})

# ========== 2️⃣ LOGIN SYSTEM ==========
@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        mobile = request.form.get('mobile')
        password = request.form.get('password')
        
        user = User.query.filter_by(mobile=mobile).first()
        
        if user and user.verify_password(password):
            session['user_id'] = user.id
            session['full_name'] = user.full_name
            session['profile_pic'] = user.profile_pic
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid mobile number or password!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ========== 3️⃣ DASHBOARD LAYOUT ==========
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    return render_template('dashboard.html', user=user)

# ========== 4️⃣ SERVICE SECTION ==========
@app.route('/services')
def services():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    active_services = Service.query.filter_by(status='active').all()
    return render_template('service.html', services=active_services)

@app.route('/service/<int:service_id>')
def view_service(service_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    service = Service.query.get_or_404(service_id)
    return render_template('service_detail.html', service=service)

# ========== 5️⃣ MENU SECTION ==========
@app.route('/menu')
def menu():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    active_menu = Menu.query.filter_by(status='active').all()
    return render_template('menu.html', menu_items=active_menu)

@app.route('/menu/<int:menu_id>')
def view_menu(menu_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    menu_item = Menu.query.get_or_404(menu_id)
    return render_template('menu_detail.html', menu_item=menu_item)

# ========== 6️⃣ ADD TO CART SYSTEM ==========
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    item_type = request.form.get('item_type')
    item_id = request.form.get('item_id')
    quantity = request.form.get('quantity', 1, type=int)
    
    # Check if item already in cart
    existing_item = Cart.query.filter_by(
        user_id=session['user_id'],
        item_type=item_type,
        item_id=item_id
    ).first()
    
    if existing_item:
        existing_item.quantity += quantity
    else:
        cart_item = Cart(
            user_id=session['user_id'],
            item_type=item_type,
            item_id=item_id,
            quantity=quantity
        )
        db.session.add(cart_item)
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Item added to cart'})

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    
    # Get item details
    cart_details = []
    total_amount = 0
    
    for item in cart_items:
        if item.item_type == 'service':
            item_detail = Service.query.get(item.item_id)
        else:  # 'menu'
            item_detail = Menu.query.get(item.item_id)
        
        if item_detail:
            cart_details.append({
                'cart_id': item.id,
                'item_type': item.item_type,
                'item_detail': item_detail,
                'quantity': item.quantity,
                'total': item_detail.final_price * item.quantity
            })
            total_amount += item_detail.final_price * item.quantity
    
    return render_template('cart.html', cart_items=cart_details, total_amount=total_amount)

@app.route('/remove_from_cart/<int:cart_id>')
def remove_from_cart(cart_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart_item = Cart.query.get_or_404(cart_id)
    
    # Verify ownership
    if cart_item.user_id != session['user_id']:
        flash('Unauthorized action!', 'danger')
        return redirect(url_for('cart'))
    
    db.session.delete(cart_item)
    db.session.commit()
    
    flash('Item removed from cart!', 'success')
    return redirect(url_for('cart'))

# ========== 7️⃣ CONFIRM ORDER FLOW ==========
@app.route('/order_form')
def order_form():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    # Calculate total from cart
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    total_amount = 0
    
    for item in cart_items:
        if item.item_type == 'service':
            item_detail = Service.query.get(item.item_id)
        else:
            item_detail = Menu.query.get(item.item_id)
        
        if item_detail:
            total_amount += item_detail.final_price * item.quantity
    
    return render_template('order_form.html', user=user, total_amount=total_amount)

@app.route('/place_order', methods=['POST'])
def place_order():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    delivery_location = request.form.get('delivery_location')
    payment_mode = request.form.get('payment_mode')
    
    # Get cart items
    cart_items = Cart.query.filter_by(user_id=user_id).all()
    
    if not cart_items:
        flash('Your cart is empty!', 'warning')
        return redirect(url_for('cart'))
    
    # Calculate total amount
    total_amount = 0
    order_items = []
    
    for item in cart_items:
        if item.item_type == 'service':
            item_detail = Service.query.get(item.item_id)
        else:
            item_detail = Menu.query.get(item.item_id)
        
        if item_detail:
            total_amount += item_detail.final_price * item.quantity
            order_items.append({
                'item_type': item.item_type,
                'item_id': item.item_id,
                'quantity': item.quantity,
                'price': item_detail.final_price
            })
    
    # Create order
    order = Order(
        user_id=user_id,
        total_amount=total_amount,
        payment_mode=payment_mode,
        delivery_location=delivery_location
    )
    db.session.add(order)
    db.session.flush()  # Get order id
    
    # Create order items
    for item in order_items:
        order_item = OrderItem(
            order_id=order.id,
            item_type=item['item_type'],
            item_id=item['item_id'],
            quantity=item['quantity'],
            price=item['price']
        )
        db.session.add(order_item)
    
    # Clear cart
    Cart.query.filter_by(user_id=user_id).delete()
    
    db.session.commit()
    
    flash('Order placed successfully!', 'success')
    return redirect(url_for('order_history'))

# ========== 9️⃣ ORDER HISTORY ==========
@app.route('/order_history')
def order_history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.order_date.desc()).all()
    
    # Get order details with items
    order_details = []
    for order in orders:
        items = []
        for item in order.items:
            if item.item_type == 'service':
                item_detail = Service.query.get(item.item_id)
            else:
                item_detail = Menu.query.get(item.item_id)
            
            items.append({
                'type': item.item_type,
                'detail': item_detail,
                'quantity': item.quantity,
                'price': item.price
            })
        
        order_details.append({
            'order': order,
            'items': items
        })
    
    return render_template('order_history.html', orders=order_details)

# ========== 🔟 PROFILE SECTION ==========
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # Update user data
        user.full_name = request.form.get('full_name')
        user.email = request.form.get('email')
        user.location = request.form.get('location')
        
        # Handle profile picture update
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file.filename:
                new_pic = save_profile_picture(file)
                if new_pic:
                    user.profile_pic = new_pic
        
        # Handle password change if provided
        new_password = request.form.get('new_password')
        if new_password:
            user.password = new_password
        
        db.session.commit()
        
        # Update session
        session['full_name'] = user.full_name
        session['profile_pic'] = user.profile_pic
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user)

# ========== HELPER FUNCTIONS ==========
@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        return dict(current_user=user)
    return dict(current_user=None)

@app.context_processor
def cart_count():
    if 'user_id' in session:
        count = Cart.query.filter_by(user_id=session['user_id']).count()
        return dict(cart_count=count)
    return dict(cart_count=0)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
