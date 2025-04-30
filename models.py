from datetime import datetime
from app import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    balance = db.Column(db.Float, default=10.0)  # Starting with ₹10 bonus
    phone = db.Column(db.String(20))
    avatar_seed = db.Column(db.String(50))
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    premium_expires = db.Column(db.DateTime)
    loyalty_level = db.Column(db.Integer, default=0)
    betting_volume = db.Column(db.Float, default=0.0)
    first_bet_made = db.Column(db.Boolean, default=False)  # Track if user made their first bet
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    telegram_id = db.Column(db.String(50))
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def loyalty_title(self):
        titles = ['Beginner', 'Novice', 'Intermediate', 'Advanced', 'Expert', 'Master', 'Legend']
        return titles[min(self.loyalty_level, len(titles)-1)]

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    txn_type = db.Column(db.String(20), nullable=False)  # 'deposit', 'withdrawal', 'game_win', 'game_loss'
    status = db.Column(db.String(20), default='pending')  # 'pending', 'approved', 'rejected'
    upi_txn_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))
    
    def __repr__(self):
        return f'<Transaction {self.id} - {self.txn_type} - {self.amount}>'

class GameRound(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    result_color = db.Column(db.String(10))  # 'red', 'green', 'violet'
    result_number = db.Column(db.Integer)
    total_bet_amount = db.Column(db.Float, default=0.0)
    total_payout = db.Column(db.Float, default=0.0)
    platform_profit = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_rigged = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<GameRound {self.id} - {self.result_color}>'

class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_round_id = db.Column(db.Integer, db.ForeignKey('game_round.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(10), nullable=False)  # 'red', 'green', 'violet'
    is_win = db.Column(db.Boolean, default=False)
    payout = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('bets', lazy=True))
    game_round = db.relationship('GameRound', backref=db.backref('bets', lazy=True))
    
    def __repr__(self):
        return f'<Bet {self.id} - User: {self.user_id} - {self.color} - {self.amount}>'

class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')  # 'open', 'closed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('support_tickets', lazy=True))
    
    def __repr__(self):
        return f'<SupportTicket {self.id} - {self.subject}>'

class SupportMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_admin = db.Column(db.Boolean, default=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    ticket = db.relationship('SupportTicket', backref=db.backref('messages', lazy=True))
    user = db.relationship('User', backref=db.backref('support_messages', lazy=True))
    
    def __repr__(self):
        return f'<SupportMessage {self.id} - Ticket: {self.ticket_id}>'

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemConfig {self.key}>'
