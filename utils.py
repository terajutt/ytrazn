import os
import random
import string
import logging
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

from app import db
from models import User, Transaction, SystemConfig
from config import EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_SERVER, EMAIL_PORT, SMS_API_KEY

# Generate a random avatar seed for new users
def generate_avatar_seed():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

# Generate OTP for verification
def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

# Send email
def send_email(recipient, subject, message):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = recipient
        msg['Subject'] = subject
        
        msg.attach(MIMEText(message, 'html'))
        
        server = smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
        return False

# Send SMS
def send_sms(phone_number, message):
    try:
        url = f"https://2factor.in/API/V1/{SMS_API_KEY}/SMS/{phone_number}/{generate_otp()}"
        response = requests.get(url)
        return response.status_code == 200
    except Exception as e:
        logging.error(f"Failed to send SMS: {str(e)}")
        return False

# Format currency
def format_currency(amount):
    return f"₹{amount:,.2f}"

# Create a new transaction
def create_transaction(user_id, amount, txn_type, status='pending', upi_txn_id=None):
    transaction = Transaction(
        user_id=user_id,
        amount=amount,
        txn_type=txn_type,
        status=status,
        upi_txn_id=upi_txn_id
    )
    
    if status == 'approved':
        transaction.approved_at = datetime.utcnow()
    
    db.session.add(transaction)
    db.session.commit()
    
    return transaction

# Get system configuration
def get_system_config(key, default=None):
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        return config.value
    return default

# Set system configuration
def set_system_config(key, value):
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = value
    else:
        config = SystemConfig(key=key, value=value)
        db.session.add(config)
    
    db.session.commit()
    return config

# Get today's platform statistics
def get_daily_stats():
    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(tomorrow, datetime.min.time())
    
    # Count new users today
    new_users = User.query.filter(
        User.created_at >= today_start,
        User.created_at < today_end
    ).count()
    
    # Calculate deposits today
    deposits = Transaction.query.filter(
        Transaction.txn_type == 'deposit',
        Transaction.status == 'approved',
        Transaction.created_at >= today_start,
        Transaction.created_at < today_end
    ).with_entities(db.func.sum(Transaction.amount)).scalar() or 0
    
    # Calculate withdrawals today
    withdrawals = Transaction.query.filter(
        Transaction.txn_type == 'withdrawal',
        Transaction.status == 'approved',
        Transaction.created_at >= today_start,
        Transaction.created_at < today_end
    ).with_entities(db.func.sum(Transaction.amount)).scalar() or 0
    
    # Calculate game profits today
    from models import GameRound
    profits = GameRound.query.filter(
        GameRound.timestamp >= today_start,
        GameRound.timestamp < today_end
    ).with_entities(db.func.sum(GameRound.platform_profit)).scalar() or 0
    
    return {
        'new_users': new_users,
        'deposits': deposits,
        'withdrawals': withdrawals,
        'profits': profits,
        'net_income': deposits - withdrawals + profits
    }

# Get historical platform statistics
def get_historical_stats(days=30):
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=days)
    
    stats = []
    
    for i in range(days):
        date = start_date + timedelta(days=i)
        next_date = date + timedelta(days=1)
        
        day_start = datetime.combine(date, datetime.min.time())
        day_end = datetime.combine(next_date, datetime.min.time())
        
        # Game profits for the day
        from models import GameRound
        profits = GameRound.query.filter(
            GameRound.timestamp >= day_start,
            GameRound.timestamp < day_end
        ).with_entities(db.func.sum(GameRound.platform_profit)).scalar() or 0
        
        # Active users for the day
        active_users = User.query.filter(
            User.last_active >= day_start,
            User.last_active < day_end
        ).count()
        
        stats.append({
            'date': date.strftime('%Y-%m-%d'),
            'profits': profits,
            'active_users': active_users
        })
    
    return stats
