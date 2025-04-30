import os
import random
import string
import logging
import secrets
import json
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import render_template, redirect, url_for, flash, request, session, jsonify, abort, Response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import app, db
from models import User, Transaction, GameRound, Bet, SupportTicket, SupportMessage, SystemConfig
from forms import (
    LoginForm, RegistrationForm, AddFundsForm, WithdrawFundsForm, 
    SupportForm, SupportReplyForm, ChangePasswordForm, ProfileForm,
    GameBetForm, PremiumSubscriptionForm, ContactForm
)
from game_logic import get_game_state, place_bet
from utils import (
    generate_avatar_seed, send_email, format_currency, create_transaction,
    get_system_config, set_system_config, get_daily_stats, get_historical_stats
)
from config import PREMIUM_SUBSCRIPTION_COST, PREMIUM_DURATION_DAYS, MIN_BET, MAX_BET

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Premium required decorator
def premium_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_premium:
            flash('This feature requires a premium subscription.', 'warning')
            return redirect(url_for('premium'))
        return f(*args, **kwargs)
    return decorated_function

# Home/Landing page
@app.route('/')
def index():
    return render_template('index.html', title='Home')

# Temporary route to make current user admin (for testing)
@app.route('/make_admin')
@login_required
def make_admin():
    if current_user.is_authenticated:
        current_user.is_admin = True
        db.session.commit()
        flash('You are now an admin!', 'success')
    return redirect(url_for('index'))

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('game'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and check_password_hash(user.password_hash, form.password.data):
            if user.is_banned:
                flash('Your account has been banned. Please contact support.', 'danger')
                return redirect(url_for('login'))
            
            login_user(user, remember=form.remember_me.data)
            user.last_active = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('game')
            
            flash('You have successfully logged in!', 'success')
            return redirect(next_page)
        else:
            flash('Login failed. Please check your email and password.', 'danger')
    
    return render_template('login.html', title='Login', form=form)

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('game'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if email already exists
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered. Please use a different email.', 'danger')
            return redirect(url_for('register'))
        
        # Check if username already exists
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already taken. Please choose a different username.', 'danger')
            return redirect(url_for('register'))
        
        # Generate random avatar seed
        avatar_seed = generate_avatar_seed()
        
        # Create new user
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            avatar_seed=avatar_seed,
            balance=0.0,
            phone=form.phone.data if hasattr(form, 'phone') else None
        )
        
        db.session.add(user)
        db.session.commit()
        
        # Log the user in
        login_user(user)
        
        flash('Registration successful! Welcome to YTRAZN Trading.', 'success')
        return redirect(url_for('game'))
    
    return render_template('register.html', title='Register', form=form)

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# User profile
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm()
    password_form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Update user profile
        current_user.phone = form.phone.data
        db.session.commit()
        flash('Your profile has been updated.', 'success')
        return redirect(url_for('profile'))
    elif request.method == 'GET':
        form.phone.data = current_user.phone
    
    # Handle password change form
    if password_form.validate_on_submit():
        if check_password_hash(current_user.password_hash, password_form.current_password.data):
            current_user.password_hash = generate_password_hash(password_form.new_password.data)
            db.session.commit()
            flash('Your password has been updated.', 'success')
            return redirect(url_for('profile'))
        else:
            flash('Current password is incorrect.', 'danger')
    
    # Get user transactions
    transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.created_at.desc()).limit(10).all()
    
    # Get user betting history
    bets = Bet.query.filter_by(user_id=current_user.id).order_by(Bet.timestamp.desc()).limit(10).all()
    
    return render_template(
        'profile.html', 
        title='My Profile', 
        form=form, 
        password_form=password_form,
        transactions=transactions,
        bets=bets
    )

# Game page
@app.route('/game')
@login_required
def game():
    form = GameBetForm()
    
    # Set min/max bet values
    min_bet = float(get_system_config('min_bet', MIN_BET))
    max_bet = float(get_system_config('max_bet', MAX_BET))
    
    # Get game state
    game_state = get_game_state()
    
    # Get recent bets for this user
    user_bets = Bet.query.filter_by(user_id=current_user.id).order_by(Bet.timestamp.desc()).limit(10).all()
    
    # Get recent game results
    recent_results = GameRound.query.filter(
        GameRound.result_color.isnot(None)
    ).order_by(GameRound.timestamp.desc()).limit(10).all()
    
    return render_template(
        'game.html', 
        title='Color Trading',
        form=form,
        game_state=game_state,
        user_bets=user_bets,
        recent_results=recent_results,
        min_bet=min_bet,
        max_bet=max_bet
    )

# Place bet
@app.route('/place_bet', methods=['POST'])
@login_required
def place_bet_route():
    try:
        form = GameBetForm()
        
        response = {
            'success': False,
            'message': '',
            'user_balance': current_user.balance,
            'user_balance_formatted': format_currency(current_user.balance)
        }
        
        if form.validate_on_submit():
            amount = form.amount.data
            color = form.color.data
            
            # Validate bet amount
            min_bet = float(get_system_config('min_bet', MIN_BET))
            max_bet = float(get_system_config('max_bet', MAX_BET))
            
            if amount < min_bet or amount > max_bet:
                response['message'] = f'Bet amount must be between {format_currency(min_bet)} and {format_currency(max_bet)}.'
                return jsonify(response)
            
            # Validate color
            if color not in ['red', 'green', 'violet']:
                response['message'] = 'Invalid color selection.'
                return jsonify(response)
            
            # Get current game state
            game_state = get_game_state()
            if game_state['status'] != 'active':
                response['message'] = 'Cannot place bet - game is not active.'
                return jsonify(response)
            
            # Place the bet
            result = place_bet(current_user.id, amount, color)
            response['success'] = result['success']
            response['message'] = result['message']
            response['user_balance'] = current_user.balance
            response['user_balance_formatted'] = format_currency(current_user.balance)
            
            db.session.commit()
            return jsonify(response)
    except Exception as e:
        print(f"Error placing bet: {str(e)}")
        response['message'] = 'An error occurred while placing your bet. Please try again.'
        return jsonify(response), 500
    
    # If form validation fails
    errors = []
    for field, field_errors in form.errors.items():
        for error in field_errors:
            errors.append(f"{field}: {error}")
    
    response['message'] = ", ".join(errors)
    return jsonify(response)

# Get game state via AJAX
@app.route('/game_state')
@login_required
def game_state_route():
    game_state = get_game_state()
    
    # Add user's current balance for real-time updates
    if current_user.is_authenticated:
        game_state['user_balance'] = current_user.balance
        game_state['user_balance_formatted'] = format_currency(current_user.balance)
    
    return jsonify(game_state)

@app.route('/game_state_stream')
@login_required
def game_state_stream():
    def generate():
        try:
            while True:
                # Check if user is still authenticated
                if not current_user or not current_user.is_authenticated:
                    yield f"data: {json.dumps({'error': 'Authentication required'})}\n\n"
                    break
                
                try:
                    game_state = get_game_state()
                    game_state['user_balance'] = current_user.balance
                    game_state['user_balance_formatted'] = format_currency(current_user.balance)
                    
                    # Get recent bets for real-time updates
                    recent_bets = Bet.query.filter_by(user_id=current_user.id).order_by(Bet.timestamp.desc()).limit(10).all()
                    game_state['recent_bets'] = [{
                        'game_round_id': bet.game_round_id,
                        'color': bet.color,
                        'amount': bet.amount,
                        'is_win': bet.is_win,
                        'payout': bet.payout
                    } for bet in recent_bets]
                    
                    yield f"data: {json.dumps(game_state)}\n\n"
                except Exception as e:
                    print(f"Error in game state stream: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                
                time.sleep(0.5)
        except GeneratorExit:
            pass
    
    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

# Add funds page
@app.route('/add_funds', methods=['GET', 'POST'])
@login_required
def add_funds():
    form = AddFundsForm()
    
    if form.validate_on_submit():
        amount = form.amount.data
        upi_txn_id = form.upi_txn_id.data
        
        # Create a new transaction
        transaction = create_transaction(
            user_id=current_user.id,
            amount=amount,
            txn_type='deposit',
            status='pending',
            upi_txn_id=upi_txn_id
        )
        
        flash('Your deposit request has been submitted and is pending approval.', 'info')
        return redirect(url_for('profile'))
    
    # Get pending deposits
    pending_deposits = Transaction.query.filter_by(
        user_id=current_user.id,
        txn_type='deposit',
        status='pending'
    ).order_by(Transaction.created_at.desc()).all()
    
    return render_template(
        'add_funds.html', 
        title='Add Funds', 
        form=form,
        pending_deposits=pending_deposits
    )

# Withdraw funds page
@app.route('/withdraw_funds', methods=['GET', 'POST'])
@login_required
def withdraw_funds():
    form = WithdrawFundsForm()
    
    if form.validate_on_submit():
        amount = form.amount.data
        upi_id = form.upi_id.data
        
        # Check if user has sufficient balance
        if current_user.balance < amount:
            flash('Insufficient balance.', 'danger')
            return redirect(url_for('withdraw_funds'))
        
        # Deduct amount from user balance
        current_user.balance -= amount
        
        # Create a new transaction
        transaction = create_transaction(
            user_id=current_user.id,
            amount=-amount,  # Negative amount for withdrawals
            txn_type='withdrawal',
            status='pending',
            upi_txn_id=upi_id  # Store UPI ID for payment
        )
        
        db.session.commit()
        
        flash('Your withdrawal request has been submitted and is pending approval.', 'info')
        return redirect(url_for('profile'))
    
    # Get pending withdrawals
    pending_withdrawals = Transaction.query.filter_by(
        user_id=current_user.id,
        txn_type='withdrawal',
        status='pending'
    ).order_by(Transaction.created_at.desc()).all()
    
    return render_template(
        'withdraw_funds.html', 
        title='Withdraw Funds', 
        form=form,
        pending_withdrawals=pending_withdrawals
    )

# Premium subscription page
@app.route('/premium', methods=['GET', 'POST'])
@login_required
def premium():
    # If user is already premium
    if current_user.is_premium:
        premium_expires = current_user.premium_expires or datetime.utcnow() + timedelta(days=30)
        return render_template(
            'premium.html', 
            title='Premium Membership', 
            is_premium=True,
            premium_expires=premium_expires
        )
    
    form = PremiumSubscriptionForm()
    
    if form.validate_on_submit():
        # Check if user has sufficient balance
        if current_user.balance < PREMIUM_SUBSCRIPTION_COST:
            flash(f'Insufficient balance. You need {format_currency(PREMIUM_SUBSCRIPTION_COST)} for a premium subscription.', 'danger')
            return redirect(url_for('premium'))
        
        # Deduct amount from user balance
        current_user.balance -= PREMIUM_SUBSCRIPTION_COST
        
        # Update user to premium
        current_user.is_premium = True
        current_user.premium_expires = datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)
        
        # Create a transaction record
        create_transaction(
            user_id=current_user.id,
            amount=-PREMIUM_SUBSCRIPTION_COST,
            txn_type='premium_subscription',
            status='approved'
        )
        
        db.session.commit()
        
        flash('Congratulations! You are now a premium member.', 'success')
        return redirect(url_for('premium'))
    
    return render_template(
        'premium.html', 
        title='Premium Membership', 
        is_premium=False,
        form=form,
        premium_cost=PREMIUM_SUBSCRIPTION_COST
    )

# Support page
@app.route('/support', methods=['GET', 'POST'])
@login_required
def support():
    form = SupportForm()
    
    if form.validate_on_submit():
        ticket = SupportTicket(
            user_id=current_user.id,
            subject=form.subject.data,
            message=form.message.data,
            status='open'
        )
        
        db.session.add(ticket)
        db.session.commit()
        
        # Add the message to the ticket
        message = SupportMessage(
            ticket_id=ticket.id,
            user_id=current_user.id,
            is_admin=False,
            message=form.message.data
        )
        
        db.session.add(message)
        db.session.commit()
        
        flash('Your support ticket has been submitted. We will get back to you soon.', 'success')
        return redirect(url_for('support'))
    
    # Get user's support tickets
    tickets = SupportTicket.query.filter_by(user_id=current_user.id).order_by(SupportTicket.created_at.desc()).all()
    
    return render_template(
        'contact.html',  # Reusing contact template for support
        title='Support',
        form=form,
        tickets=tickets
    )

# Support ticket detail page
@app.route('/support/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def support_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    
    # Ensure user is the owner of the ticket or an admin
    if ticket.user_id != current_user.id and not current_user.is_admin:
        flash('You do not have permission to view this ticket.', 'danger')
        return redirect(url_for('support'))
    
    form = SupportReplyForm()
    
    if form.validate_on_submit():
        # Add reply to the ticket
        message = SupportMessage(
            ticket_id=ticket.id,
            user_id=current_user.id,
            is_admin=current_user.is_admin,
            message=form.message.data
        )
        
        # If ticket was closed, reopen it
        if ticket.status == 'closed':
            ticket.status = 'open'
        
        db.session.add(message)
        db.session.commit()
        
        flash('Your reply has been added.', 'success')
        return redirect(url_for('support_ticket', ticket_id=ticket.id))
    
    # Get messages for this ticket
    messages = SupportMessage.query.filter_by(ticket_id=ticket.id).order_by(SupportMessage.created_at).all()
    
    return render_template(
        'support_ticket.html',
        title=f'Support Ticket #{ticket.id}',
        ticket=ticket,
        messages=messages,
        form=form
    )

# Close support ticket
@app.route('/support/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    
    # Ensure user is the owner of the ticket or an admin
    if ticket.user_id != current_user.id and not current_user.is_admin:
        flash('You do not have permission to close this ticket.', 'danger')
        return redirect(url_for('support'))
    
    ticket.status = 'closed'
    db.session.commit()
    
    flash('Ticket has been closed.', 'success')
    return redirect(url_for('support_ticket', ticket_id=ticket.id))

# About page
@app.route('/about')
def about():
    return render_template('about.html', title='About Us')

# Terms of Service page
@app.route('/terms')
def terms():
    return render_template('terms.html', title='Terms of Service')

# Privacy Policy page
@app.route('/privacy')
def privacy():
    return render_template('privacy.html', title='Privacy Policy')

# Contact page
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    
    if form.validate_on_submit():
        # If user is logged in, associate message with user
        if current_user.is_authenticated:
            ticket = SupportTicket(
                user_id=current_user.id,
                subject=form.subject.data,
                message=form.message.data,
                status='open'
            )
            
            db.session.add(ticket)
            db.session.commit()
            
            # Add the message to the ticket
            message = SupportMessage(
                ticket_id=ticket.id,
                user_id=current_user.id,
                is_admin=False,
                message=form.message.data
            )
            
            db.session.add(message)
            db.session.commit()
        else:
            # For non-logged in users, just send an email notification
            message_body = f"Name: {form.name.data}\nEmail: {form.email.data}\nSubject: {form.subject.data}\n\n{form.message.data}"
            send_email('admin@ytrazn.com', f"Contact Form: {form.subject.data}", message_body)
        
        flash('Your message has been sent. We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html', title='Contact Us', form=form)

# Support ticket template (used for both support and contact pages)
@app.route('/support_ticket')
def support_ticket_template():
    return render_template('support_ticket.html', title='Support Ticket')

# ----- ADMIN ROUTES -----

# Admin dashboard
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    # Get daily stats (with defaults in case of None)
    stats = get_daily_stats() or {
        'platform_profit': 0.0,
        'today_profit': 0.0,
        'total_bets': 0,
        'total_volume': 0.0
    }
    
    # Get historical stats for charts
    historical_stats = get_historical_stats(days=30) or []
    
    # Total users count
    total_users = User.query.count()
    premium_users = User.query.filter_by(is_premium=True).count()
    
    # Recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Pending transactions
    pending_deposits = Transaction.query.filter_by(txn_type='deposit', status='pending').count()
    pending_withdrawals = Transaction.query.filter_by(txn_type='withdrawal', status='pending').count()
    
    # Open support tickets
    open_tickets = SupportTicket.query.filter_by(status='open').count()
    
    return render_template(
        'admin/dashboard.html',
        title='Admin Dashboard',
        stats=stats,
        historical_stats=json.dumps(historical_stats),
        total_users=total_users,
        premium_users=premium_users,
        recent_users=recent_users,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        open_tickets=open_tickets
    )

# Admin users management
@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    # Get all users
    users = User.query.order_by(User.created_at.desc()).all()
    
    # Get today's date for template filtering
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    return render_template(
        'admin/users.html',
        title='User Management',
        users=users,
        today=today
    )

# Admin view user
@app.route('/admin/users/<int:user_id>')
@login_required
@admin_required
def admin_view_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Get user transactions
    transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.desc()).limit(10).all()
    
    # Get user bets
    bets = Bet.query.filter_by(user_id=user.id).order_by(Bet.timestamp.desc()).limit(10).all()
    
    return render_template(
        'admin/view_user.html',
        title=f'User: {user.username}',
        user=user,
        transactions=transactions,
        bets=bets
    )

# Admin ban/unban user
@app.route('/admin/users/<int:user_id>/toggle_ban', methods=['POST'])
@login_required
@admin_required
def admin_toggle_ban(user_id):
    user = User.query.get_or_404(user_id)
    
    user.is_banned = not user.is_banned
    db.session.commit()
    
    message = f"User {user.username} has been {'banned' if user.is_banned else 'unbanned'}."
    flash(message, 'success')
    
    return redirect(url_for('admin_view_user', user_id=user.id))

# Admin give/revoke premium
@app.route('/admin/users/<int:user_id>/toggle_premium', methods=['POST'])
@login_required
@admin_required
def admin_toggle_premium(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.is_premium:
        user.is_premium = False
        user.premium_expires = None
        message = f"Premium status removed from user {user.username}."
    else:
        user.is_premium = True
        user.premium_expires = datetime.utcnow() + timedelta(days=PREMIUM_DURATION_DAYS)
        message = f"User {user.username} has been given premium status for {PREMIUM_DURATION_DAYS} days."
    
    db.session.commit()
    flash(message, 'success')
    
    return redirect(url_for('admin_view_user', user_id=user.id))

# Admin add funds to user
@app.route('/admin/users/<int:user_id>/add_funds', methods=['POST'])
@login_required
@admin_required
def admin_add_funds(user_id):
    user = User.query.get_or_404(user_id)
    
    amount = float(request.form.get('amount', 0))
    
    if amount <= 0:
        flash('Amount must be greater than zero.', 'danger')
        return redirect(url_for('admin_view_user', user_id=user.id))
    
    # Add funds to user balance
    user.balance += amount
    
    # Create transaction record
    transaction = Transaction(
        user_id=user.id,
        amount=amount,
        txn_type='admin_deposit',
        status='approved',
        approved_at=datetime.utcnow()
    )
    
    db.session.add(transaction)
    db.session.commit()
    
    flash(f'Added {format_currency(amount)} to {user.username}\'s balance.', 'success')
    return redirect(url_for('admin_view_user', user_id=user.id))

# Admin toggle admin status
@app.route('/admin/users/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
@admin_required
def admin_toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    
    user.is_admin = not user.is_admin
    db.session.commit()
    
    message = f"User {user.username} has been {'made an admin' if user.is_admin else 'removed from admin role'}."
    flash(message, 'success')
    
    return redirect(url_for('admin_view_user', user_id=user.id))

# Admin transactions
@app.route('/admin/transactions')
@login_required
@admin_required
def admin_transactions():
    # Get all transactions
    all_transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    
    # Get counts for different types
    pending_deposits = Transaction.query.filter_by(txn_type='deposit', status='pending').count()
    pending_withdrawals = Transaction.query.filter_by(txn_type='withdrawal', status='pending').count()
    
    return render_template(
        'admin/transactions.html',
        title='Transaction Management',
        transactions=all_transactions,
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals
    )

# Admin approve/reject transaction
@app.route('/admin/transactions/<int:transaction_id>/<action>', methods=['POST'])
@login_required
@admin_required
def admin_transaction_action(transaction_id, action):
    transaction = Transaction.query.get_or_404(transaction_id)
    
    if action == 'approve':
        transaction.status = 'approved'
        transaction.approved_at = datetime.utcnow()
        
        # For deposits, add funds to user balance
        if transaction.txn_type == 'deposit':
            user = User.query.get(transaction.user_id)
            user.balance += transaction.amount
            
            message = f'Deposit of {format_currency(transaction.amount)} for user {user.username} has been approved.'
        else:
            message = f'Transaction {transaction_id} has been approved.'
        
        flash(message, 'success')
    
    elif action == 'reject':
        transaction.status = 'rejected'
        
        # For withdrawals, return funds to user balance
        if transaction.txn_type == 'withdrawal':
            user = User.query.get(transaction.user_id)
            user.balance += abs(transaction.amount)
            
            message = f'Withdrawal has been rejected and {format_currency(abs(transaction.amount))} has been returned to the user\'s balance.'
        else:
            message = f'Transaction {transaction_id} has been rejected.'
        
        flash(message, 'success')
    
    db.session.commit()
    return redirect(url_for('admin_transactions'))

# Admin game settings
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    if request.method == 'POST':
        # Update min bet
        if 'min_bet' in request.form:
            min_bet = request.form.get('min_bet')
            set_system_config('min_bet', min_bet)
            flash(f'Minimum bet updated to {format_currency(float(min_bet))}.', 'success')
        
        # Update max bet
        if 'max_bet' in request.form:
            max_bet = request.form.get('max_bet')
            set_system_config('max_bet', max_bet)
            flash(f'Maximum bet updated to {format_currency(float(max_bet))}.', 'success')
        
        # Toggle loss mode
        if 'toggle_loss_mode' in request.form:
            current_mode = get_system_config('loss_mode', 'false')
            new_mode = 'true' if current_mode.lower() == 'false' else 'false'
            set_system_config('loss_mode', new_mode)
            
            mode_status = 'enabled' if new_mode == 'true' else 'disabled'
            flash(f'Loss mode has been {mode_status}.', 'success')
        
        return redirect(url_for('admin_settings'))
    
    # Get current settings
    min_bet = get_system_config('min_bet', MIN_BET)
    max_bet = get_system_config('max_bet', MAX_BET)
    loss_mode = get_system_config('loss_mode', 'false')
    
    # Get current game state
    game_state = get_game_state()
    
    # Get today's game stats
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(tomorrow, datetime.min.time())
    
    rounds_today = GameRound.query.filter(
        GameRound.timestamp >= today_start,
        GameRound.timestamp < today_end
    ).count()
    
    total_bets_today = Bet.query.join(GameRound).filter(
        GameRound.timestamp >= today_start,
        GameRound.timestamp < today_end
    ).count()
    
    total_bet_amount_today = Bet.query.join(GameRound).filter(
        GameRound.timestamp >= today_start,
        GameRound.timestamp < today_end
    ).with_entities(db.func.sum(Bet.amount)).scalar() or 0
    
    total_payout_today = Bet.query.join(GameRound).filter(
        GameRound.timestamp >= today_start,
        GameRound.timestamp < today_end,
        Bet.is_win == True
    ).with_entities(db.func.sum(Bet.payout)).scalar() or 0
    
    profit_today = total_bet_amount_today - total_payout_today
    profit_percentage = (profit_today / total_bet_amount_today * 100) if total_bet_amount_today > 0 else 0
    
    return render_template(
        'admin/settings.html',
        title='Game Settings',
        min_bet=min_bet,
        max_bet=max_bet,
        loss_mode=loss_mode.lower() == 'true',
        game_state=game_state,
        rounds_today=rounds_today,
        total_bets_today=total_bets_today,
        total_bet_amount_today=total_bet_amount_today,
        total_payout_today=total_payout_today,
        profit_today=profit_today,
        profit_percentage=profit_percentage
    )

# Admin support tickets
@app.route('/admin/support')
@login_required
@admin_required
def admin_support():
    # Get open tickets
    open_tickets = SupportTicket.query.filter_by(status='open').order_by(SupportTicket.created_at.desc()).all()
    
    # Get premium tickets
    premium_tickets = SupportTicket.query.join(User).filter(
        SupportTicket.status == 'open',
        User.is_premium == True
    ).order_by(SupportTicket.created_at.desc()).all()
    
    # Get recently closed tickets
    closed_tickets = SupportTicket.query.filter_by(status='closed').order_by(SupportTicket.created_at.desc()).limit(10).all()
    
    return render_template(
        'admin/support.html',
        title='Support Management',
        open_tickets=open_tickets,
        premium_tickets=premium_tickets,
        closed_tickets=closed_tickets
    )

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# Create error templates if they don't exist
@app.route('/404')
def error_404():
    return render_template('404.html', title='Page Not Found')

@app.route('/500')
def error_500():
    return render_template('500.html', title='Server Error')

# Template for support ticket (needed for admin)
@app.route('/admin/support/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_support_ticket(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    form = SupportReplyForm()
    
    if form.validate_on_submit():
        # Add admin reply to the ticket
        message = SupportMessage(
            ticket_id=ticket.id,
            is_admin=True,
            message=form.message.data
        )
        
        db.session.add(message)
        db.session.commit()
        
        flash('Your reply has been sent.', 'success')
        return redirect(url_for('admin_support_ticket', ticket_id=ticket.id))
    
    # Get messages for this ticket
    messages = SupportMessage.query.filter_by(ticket_id=ticket.id).order_by(SupportMessage.created_at).all()
    
    return render_template(
        'admin/support_ticket.html',
        title=f'Support Ticket #{ticket.id}',
        ticket=ticket,
        messages=messages,
        form=form
    )

# Admin toggle ticket status
@app.route('/admin/support/<int:ticket_id>/toggle_status', methods=['POST'])
@login_required
@admin_required
def admin_toggle_ticket_status(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    
    ticket.status = 'closed' if ticket.status == 'open' else 'open'
    db.session.commit()
    
    status = 'closed' if ticket.status == 'closed' else 'reopened'
    flash(f'Ticket #{ticket.id} has been {status}.', 'success')
    
    return redirect(url_for('admin_support_ticket', ticket_id=ticket.id))
