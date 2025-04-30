import os
import logging
import threading
from datetime import datetime, timedelta

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes,
    ConversationHandler
)

from app import app, db
from models import User, Transaction, GameRound, Bet, SupportTicket, SupportMessage, SystemConfig
from game_logic import get_game_state
from utils import get_daily_stats, format_currency
from config import TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_IDS

# Conversation states
MENU, USER_ACTION, TRANSACTION_ACTION, GAME_SETTINGS, BROADCAST, SUPPORT = range(6)

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Admin verification
def is_admin(telegram_id):
    telegram_id_str = str(telegram_id)
    if telegram_id_str in ADMIN_TELEGRAM_IDS:
        return True
    
    with app.app_context():
        admin_user = User.query.filter_by(telegram_id=telegram_id_str, is_admin=True).first()
        return admin_user is not None

# Main menu keyboard
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("👥 View Users", callback_data='view_users')],
        [InlineKeyboardButton("💰 Transactions", callback_data='transactions')],
        [InlineKeyboardButton("🎮 Game Settings", callback_data='game_settings')],
        [InlineKeyboardButton("📊 Analytics", callback_data='analytics')],
        [InlineKeyboardButton("📣 Send Broadcast", callback_data='broadcast')],
        [InlineKeyboardButton("🛠️ Support Chats", callback_data='support')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"Welcome to YTRAZN Trading Admin Bot!\n\n"
        f"This bot allows you to manage your trading platform.\n"
        f"Choose an option below:",
        reply_markup=get_main_menu_keyboard()
    )
    
    return MENU

# Help command handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "YTRAZN Trading Admin Bot Commands:\n\n"
        "/start - Start the bot and show main menu\n"
        "/help - Show this help message\n"
        "/users - View all users\n"
        "/transactions - Manage transactions\n"
        "/game - Game settings\n"
        "/analytics - View platform analytics\n"
        "/broadcast - Send message to users\n"
        "/support - View support chats\n"
    )
    
    return MENU

# Menu callback handler
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_menu':
        await query.edit_message_text(
            "Main Menu - Choose an option:",
            reply_markup=get_main_menu_keyboard()
        )
        return MENU
    
    elif query.data == 'view_users':
        return await handle_view_users(query, context)
    
    elif query.data == 'transactions':
        return await handle_transactions(query, context)
    
    elif query.data == 'game_settings':
        return await handle_game_settings(query, context)
    
    elif query.data == 'analytics':
        return await handle_analytics(query, context)
    
    elif query.data == 'broadcast':
        return await handle_broadcast(query, context)
    
    elif query.data == 'support':
        return await handle_support(query, context)
    
    return MENU

# Handle view users
async def handle_view_users(query, context):
    with app.app_context():
        # Get user counts
        total_users = User.query.count()
        premium_users = User.query.filter_by(is_premium=True).count()
        banned_users = User.query.filter_by(is_banned=True).count()
        
        # Get recent users
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_users_text = "\n".join([
            f"• {user.username} (ID: {user.id}) - Balance: {format_currency(user.balance)}"
            for user in recent_users
        ])
        
        keyboard = [
            [InlineKeyboardButton("🔍 Search User", callback_data='search_user')],
            [InlineKeyboardButton("🔴 View Banned Users", callback_data='view_banned')],
            [InlineKeyboardButton("⭐ View Premium Users", callback_data='view_premium')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        
        await query.edit_message_text(
            f"👥 *User Management*\n\n"
            f"Total Users: {total_users}\n"
            f"Premium Users: {premium_users}\n"
            f"Banned Users: {banned_users}\n\n"
            f"*Recent Users:*\n{recent_users_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return USER_ACTION

# Handle user actions
async def user_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'search_user':
        await query.edit_message_text(
            "Please enter the username or user ID to search:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data='view_users')
            ]])
        )
        context.user_data['awaiting_user_search'] = True
        return USER_ACTION
    
    elif query.data == 'view_banned':
        with app.app_context():
            banned_users = User.query.filter_by(is_banned=True).limit(10).all()
            
            if not banned_users:
                text = "No banned users found."
            else:
                text = "*Banned Users:*\n" + "\n".join([
                    f"• {user.username} (ID: {user.id})"
                    for user in banned_users
                ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='view_users')
                ]])
            )
        
        return USER_ACTION
    
    elif query.data == 'view_premium':
        with app.app_context():
            premium_users = User.query.filter_by(is_premium=True).limit(10).all()
            
            if not premium_users:
                text = "No premium users found."
            else:
                text = "*Premium Users:*\n" + "\n".join([
                    f"• {user.username} (ID: {user.id}) - Expires: {user.premium_expires.strftime('%Y-%m-%d') if user.premium_expires else 'Never'}"
                    for user in premium_users
                ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='view_users')
                ]])
            )
        
        return USER_ACTION
    
    elif query.data.startswith('user_'):
        user_id = int(query.data.split('_')[1])
        
        with app.app_context():
            user = User.query.get(user_id)
            
            if not user:
                await query.edit_message_text(
                    "User not found.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='view_users')
                    ]])
                )
                return USER_ACTION
            
            # Get user stats
            bet_count = Bet.query.filter_by(user_id=user_id).count()
            win_count = Bet.query.filter_by(user_id=user_id, is_win=True).count()
            
            action_buttons = []
            if user.is_banned:
                action_buttons.append([InlineKeyboardButton("✅ Unban User", callback_data=f'unban_{user_id}')])
            else:
                action_buttons.append([InlineKeyboardButton("⛔ Ban User", callback_data=f'ban_{user_id}')])
            
            if not user.is_premium:
                action_buttons.append([InlineKeyboardButton("⭐ Make Premium", callback_data=f'premium_{user_id}')])
            else:
                action_buttons.append([InlineKeyboardButton("⭐ Remove Premium", callback_data=f'unpremium_{user_id}')])
            
            action_buttons.append([InlineKeyboardButton("💰 Add Funds", callback_data=f'add_funds_{user_id}')])
            action_buttons.append([InlineKeyboardButton("🔙 Back", callback_data='view_users')])
            
            await query.edit_message_text(
                f"*User Profile:*\n\n"
                f"*ID:* {user.id}\n"
                f"*Username:* {user.username}\n"
                f"*Email:* {user.email}\n"
                f"*Balance:* {format_currency(user.balance)}\n"
                f"*Status:* {'Banned ⛔' if user.is_banned else 'Active ✅'}\n"
                f"*Premium:* {'Yes ⭐' if user.is_premium else 'No'}\n"
                f"*Loyalty Level:* {user.loyalty_level} ({user.loyalty_title})\n"
                f"*Betting Volume:* {format_currency(user.betting_volume)}\n"
                f"*Bets Placed:* {bet_count}\n"
                f"*Wins:* {win_count}\n"
                f"*Win Rate:* {(win_count / bet_count * 100) if bet_count > 0 else 0:.1f}%\n"
                f"*Joined:* {user.created_at.strftime('%Y-%m-%d')}\n"
                f"*Last Active:* {user.last_active.strftime('%Y-%m-%d %H:%M') if user.last_active else 'Never'}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(action_buttons)
            )
        
        return USER_ACTION
    
    elif query.data.startswith('ban_'):
        user_id = int(query.data.split('_')[1])
        
        with app.app_context():
            user = User.query.get(user_id)
            
            if user:
                user.is_banned = True
                db.session.commit()
                
                await query.edit_message_text(
                    f"User *{user.username}* has been banned.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to User", callback_data=f'user_{user_id}')
                    ]])
                )
        
        return USER_ACTION
    
    elif query.data.startswith('unban_'):
        user_id = int(query.data.split('_')[1])
        
        with app.app_context():
            user = User.query.get(user_id)
            
            if user:
                user.is_banned = False
                db.session.commit()
                
                await query.edit_message_text(
                    f"User *{user.username}* has been unbanned.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to User", callback_data=f'user_{user_id}')
                    ]])
                )
        
        return USER_ACTION
    
    elif query.data.startswith('premium_'):
        user_id = int(query.data.split('_')[1])
        
        with app.app_context():
            user = User.query.get(user_id)
            
            if user:
                user.is_premium = True
                user.premium_expires = datetime.utcnow() + timedelta(days=30)
                db.session.commit()
                
                await query.edit_message_text(
                    f"User *{user.username}* is now a premium user for 30 days.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to User", callback_data=f'user_{user_id}')
                    ]])
                )
        
        return USER_ACTION
    
    elif query.data.startswith('unpremium_'):
        user_id = int(query.data.split('_')[1])
        
        with app.app_context():
            user = User.query.get(user_id)
            
            if user:
                user.is_premium = False
                user.premium_expires = None
                db.session.commit()
                
                await query.edit_message_text(
                    f"Premium status removed from user *{user.username}*.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to User", callback_data=f'user_{user_id}')
                    ]])
                )
        
        return USER_ACTION
    
    elif query.data.startswith('add_funds_'):
        user_id = int(query.data.split('_')[2])
        
        context.user_data['add_funds_user_id'] = user_id
        
        await query.edit_message_text(
            "Please enter the amount to add to the user's balance:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data=f'user_{user_id}')
            ]])
        )
        
        context.user_data['awaiting_add_funds'] = True
        return USER_ACTION
    
    return USER_ACTION

# Handle text messages (for searches and inputs)
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if context.user_data.get('awaiting_user_search'):
        context.user_data['awaiting_user_search'] = False
        
        with app.app_context():
            # Try to find by ID
            try:
                user_id = int(text)
                user = User.query.get(user_id)
                if user:
                    keyboard = [[InlineKeyboardButton("👤 View User", callback_data=f'user_{user.id}')]]
                    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='view_users')])
                    
                    await update.message.reply_text(
                        f"User found:\n\n"
                        f"ID: {user.id}\n"
                        f"Username: {user.username}\n"
                        f"Balance: {format_currency(user.balance)}",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    return USER_ACTION
            except ValueError:
                pass
            
            # Try to find by username
            user = User.query.filter(User.username.ilike(f"%{text}%")).first()
            if user:
                keyboard = [[InlineKeyboardButton("👤 View User", callback_data=f'user_{user.id}')]]
                keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='view_users')])
                
                await update.message.reply_text(
                    f"User found:\n\n"
                    f"ID: {user.id}\n"
                    f"Username: {user.username}\n"
                    f"Balance: {format_currency(user.balance)}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return USER_ACTION
            
            # Try to find by email
            user = User.query.filter(User.email.ilike(f"%{text}%")).first()
            if user:
                keyboard = [[InlineKeyboardButton("👤 View User", callback_data=f'user_{user.id}')]]
                keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='view_users')])
                
                await update.message.reply_text(
                    f"User found:\n\n"
                    f"ID: {user.id}\n"
                    f"Username: {user.username}\n"
                    f"Balance: {format_currency(user.balance)}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return USER_ACTION
            
            await update.message.reply_text(
                "No user found with that ID, username, or email.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='view_users')
                ]])
            )
        
        return USER_ACTION
    
    elif context.user_data.get('awaiting_add_funds'):
        context.user_data['awaiting_add_funds'] = False
        user_id = context.user_data.get('add_funds_user_id')
        
        try:
            amount = float(text)
            
            if amount <= 0:
                await update.message.reply_text(
                    "Amount must be greater than zero.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data=f'user_{user_id}')
                    ]])
                )
                return USER_ACTION
            
            with app.app_context():
                user = User.query.get(user_id)
                
                if user:
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
                    
                    await update.message.reply_text(
                        f"Added {format_currency(amount)} to {user.username}'s balance.\n"
                        f"New balance: {format_currency(user.balance)}",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back to User", callback_data=f'user_{user_id}')
                        ]])
                    )
                    return USER_ACTION
                else:
                    await update.message.reply_text(
                        "User not found.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='view_users')
                        ]])
                    )
        except ValueError:
            await update.message.reply_text(
                "Invalid amount. Please enter a valid number.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data=f'user_{user_id}')
                ]])
            )
        
        return USER_ACTION
    
    elif context.user_data.get('awaiting_broadcast'):
        context.user_data['awaiting_broadcast'] = False
        target = context.user_data.get('broadcast_target')
        
        with app.app_context():
            if target == 'all':
                users = User.query.filter_by(is_banned=False).all()
                target_name = "all users"
            elif target == 'premium':
                users = User.query.filter_by(is_banned=False, is_premium=True).all()
                target_name = "premium users"
            elif target == 'active':
                yesterday = datetime.utcnow() - timedelta(days=1)
                users = User.query.filter(User.is_banned==False, User.last_active >= yesterday).all()
                target_name = "active users"
            else:
                users = []
                target_name = "unknown target"
            
            user_count = len(users)
            
            await update.message.reply_text(
                f"Your message will be sent to {user_count} {target_name}.\n\n"
                f"Message Preview:\n\n"
                f"{text}\n\n"
                f"Do you want to continue?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Send Message", callback_data=f'confirm_broadcast_{target}_{hash(text)}')],
                    [InlineKeyboardButton("❌ Cancel", callback_data='broadcast')]
                ])
            )
            
            # Store the message text for later use
            context.user_data['broadcast_message'] = text
        
        return BROADCAST
    
    elif context.user_data.get('awaiting_support_reply'):
        context.user_data['awaiting_support_reply'] = False
        ticket_id = context.user_data.get('support_ticket_id')
        
        with app.app_context():
            ticket = SupportTicket.query.get(ticket_id)
            
            if ticket:
                # Create a new support message
                message = SupportMessage(
                    ticket_id=ticket.id,
                    is_admin=True,
                    message=text
                )
                
                db.session.add(message)
                
                # Update ticket status if it was closed
                if ticket.status == 'closed':
                    ticket.status = 'open'
                
                db.session.commit()
                
                await update.message.reply_text(
                    f"Reply sent to ticket #{ticket.id}.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Ticket", callback_data=f'ticket_{ticket.id}')
                    ]])
                )
                return SUPPORT
            else:
                await update.message.reply_text(
                    "Ticket not found.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='support')
                    ]])
                )
        
        return SUPPORT
    
    return MENU

# Handle transactions
async def handle_transactions(query, context):
    with app.app_context():
        # Get pending transactions
        pending_deposits = Transaction.query.filter_by(txn_type='deposit', status='pending').count()
        pending_withdrawals = Transaction.query.filter_by(txn_type='withdrawal', status='pending').count()
        
        # Get recent transactions
        recent_txns = Transaction.query.filter(
            Transaction.status == 'approved',
            Transaction.txn_type.in_(['deposit', 'withdrawal'])
        ).order_by(Transaction.created_at.desc()).limit(5).all()
        
        recent_txns_text = "\n".join([
            f"• {txn.created_at.strftime('%Y-%m-%d %H:%M')} - "
            f"{txn.user.username} - "
            f"{'➕' if txn.txn_type == 'deposit' else '➖'} "
            f"{format_currency(abs(txn.amount))}"
            for txn in recent_txns
        ]) if recent_txns else "No recent transactions."
        
        keyboard = [
            [InlineKeyboardButton(f"💰 Pending Deposits ({pending_deposits})", callback_data='pending_deposits')],
            [InlineKeyboardButton(f"💸 Pending Withdrawals ({pending_withdrawals})", callback_data='pending_withdrawals')],
            [InlineKeyboardButton("📊 Transaction History", callback_data='txn_history')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        
        await query.edit_message_text(
            f"💰 *Transaction Management*\n\n"
            f"*Pending Actions:*\n"
            f"• Deposits: {pending_deposits}\n"
            f"• Withdrawals: {pending_withdrawals}\n\n"
            f"*Recent Transactions:*\n{recent_txns_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return TRANSACTION_ACTION

# Handle transaction actions
async def transaction_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'pending_deposits':
        with app.app_context():
            deposits = Transaction.query.filter_by(txn_type='deposit', status='pending').order_by(Transaction.created_at.desc()).limit(10).all()
            
            if not deposits:
                text = "No pending deposits."
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='transactions')]]
            else:
                text = "*Pending Deposits:*\n\n" + "\n\n".join([
                    f"ID: {txn.id}\n"
                    f"User: {txn.user.username}\n"
                    f"Amount: {format_currency(txn.amount)}\n"
                    f"UPI TXN ID: {txn.upi_txn_id}\n"
                    f"Date: {txn.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Actions: [Approve](approve_deposit_{txn.id}) | [Reject](reject_deposit_{txn.id})"
                    for txn in deposits
                ])
                
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='transactions')]]
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return TRANSACTION_ACTION
    
    elif query.data == 'pending_withdrawals':
        with app.app_context():
            withdrawals = Transaction.query.filter_by(txn_type='withdrawal', status='pending').order_by(Transaction.created_at.desc()).limit(10).all()
            
            if not withdrawals:
                text = "No pending withdrawals."
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='transactions')]]
            else:
                text = "*Pending Withdrawals:*\n\n" + "\n\n".join([
                    f"ID: {txn.id}\n"
                    f"User: {txn.user.username}\n"
                    f"Amount: {format_currency(abs(txn.amount))}\n"
                    f"UPI: {txn.upi_txn_id}\n"
                    f"Date: {txn.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Actions: [Approve](approve_withdrawal_{txn.id}) | [Reject](reject_withdrawal_{txn.id})"
                    for txn in withdrawals
                ])
                
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='transactions')]]
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return TRANSACTION_ACTION
    
    elif query.data == 'txn_history':
        with app.app_context():
            txns = Transaction.query.filter(
                Transaction.status == 'approved',
                Transaction.txn_type.in_(['deposit', 'withdrawal'])
            ).order_by(Transaction.created_at.desc()).limit(10).all()
            
            if not txns:
                text = "No transaction history found."
            else:
                text = "*Recent Transactions:*\n\n" + "\n".join([
                    f"• {txn.created_at.strftime('%Y-%m-%d %H:%M')} - "
                    f"{txn.user.username} - "
                    f"{'➕' if txn.txn_type == 'deposit' else '➖'} "
                    f"{format_currency(abs(txn.amount))}"
                    for txn in txns
                ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='transactions')
                ]])
            )
        
        return TRANSACTION_ACTION
    
    elif query.data.startswith('approve_deposit_'):
        txn_id = int(query.data.split('_')[2])
        
        with app.app_context():
            txn = Transaction.query.get(txn_id)
            
            if txn and txn.txn_type == 'deposit' and txn.status == 'pending':
                user = User.query.get(txn.user_id)
                
                if user:
                    # Update transaction status
                    txn.status = 'approved'
                    txn.approved_at = datetime.utcnow()
                    
                    # Add funds to user balance
                    user.balance += txn.amount
                    
                    db.session.commit()
                    
                    await query.edit_message_text(
                        f"✅ Deposit of {format_currency(txn.amount)} for user {user.username} has been approved.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='pending_deposits')
                        ]])
                    )
                else:
                    await query.edit_message_text(
                        "User not found.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='pending_deposits')
                        ]])
                    )
            else:
                await query.edit_message_text(
                    "Transaction not found or already processed.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='pending_deposits')
                    ]])
                )
        
        return TRANSACTION_ACTION
    
    elif query.data.startswith('reject_deposit_'):
        txn_id = int(query.data.split('_')[2])
        
        with app.app_context():
            txn = Transaction.query.get(txn_id)
            
            if txn and txn.txn_type == 'deposit' and txn.status == 'pending':
                # Update transaction status
                txn.status = 'rejected'
                
                db.session.commit()
                
                await query.edit_message_text(
                    f"❌ Deposit of {format_currency(txn.amount)} has been rejected.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='pending_deposits')
                    ]])
                )
            else:
                await query.edit_message_text(
                    "Transaction not found or already processed.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='pending_deposits')
                    ]])
                )
        
        return TRANSACTION_ACTION
    
    elif query.data.startswith('approve_withdrawal_'):
        txn_id = int(query.data.split('_')[2])
        
        with app.app_context():
            txn = Transaction.query.get(txn_id)
            
            if txn and txn.txn_type == 'withdrawal' and txn.status == 'pending':
                user = User.query.get(txn.user_id)
                
                if user:
                    # Update transaction status
                    txn.status = 'approved'
                    txn.approved_at = datetime.utcnow()
                    
                    db.session.commit()
                    
                    await query.edit_message_text(
                        f"✅ Withdrawal of {format_currency(abs(txn.amount))} for user {user.username} has been approved.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='pending_withdrawals')
                        ]])
                    )
                else:
                    await query.edit_message_text(
                        "User not found.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='pending_withdrawals')
                        ]])
                    )
            else:
                await query.edit_message_text(
                    "Transaction not found or already processed.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='pending_withdrawals')
                    ]])
                )
        
        return TRANSACTION_ACTION
    
    elif query.data.startswith('reject_withdrawal_'):
        txn_id = int(query.data.split('_')[2])
        
        with app.app_context():
            txn = Transaction.query.get(txn_id)
            
            if txn and txn.txn_type == 'withdrawal' and txn.status == 'pending':
                user = User.query.get(txn.user_id)
                
                if user:
                    # Update transaction status
                    txn.status = 'rejected'
                    
                    # Return funds to user balance
                    user.balance += abs(txn.amount)
                    
                    db.session.commit()
                    
                    await query.edit_message_text(
                        f"❌ Withdrawal of {format_currency(abs(txn.amount))} for user {user.username} has been rejected and funds returned to balance.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='pending_withdrawals')
                        ]])
                    )
                else:
                    await query.edit_message_text(
                        "User not found.",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("🔙 Back", callback_data='pending_withdrawals')
                        ]])
                    )
            else:
                await query.edit_message_text(
                    "Transaction not found or already processed.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='pending_withdrawals')
                    ]])
                )
        
        return TRANSACTION_ACTION
    
    return TRANSACTION_ACTION

# Handle game settings
async def handle_game_settings(query, context):
    with app.app_context():
        # Get current game status
        game_state = get_game_state()
        
        # Get game settings
        loss_mode = SystemConfig.query.filter_by(key='loss_mode').first()
        loss_mode_status = loss_mode.value if loss_mode else 'false'
        
        min_bet = SystemConfig.query.filter_by(key='min_bet').first()
        min_bet_value = min_bet.value if min_bet else '10'
        
        max_bet = SystemConfig.query.filter_by(key='max_bet').first()
        max_bet_value = max_bet.value if max_bet else '10000'
        
        keyboard = [
            [InlineKeyboardButton(f"{'🔴' if loss_mode_status.lower() == 'true' else '🟢'} Loss Mode: {'ON' if loss_mode_status.lower() == 'true' else 'OFF'}", callback_data='toggle_loss_mode')],
            [InlineKeyboardButton(f"⬇️ Min Bet: {min_bet_value}", callback_data='set_min_bet')],
            [InlineKeyboardButton(f"⬆️ Max Bet: {max_bet_value}", callback_data='set_max_bet')],
            [InlineKeyboardButton("🎮 Current Game Stats", callback_data='game_stats')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        
        await query.edit_message_text(
            f"🎮 *Game Settings*\n\n"
            f"Current Round: #{game_state['round_id']}\n"
            f"Status: {game_state['status'].capitalize()}\n"
            f"Time Remaining: {int(game_state['time_remaining'])} seconds\n\n"
            f"*Last Result:*\n"
            f"Color: {game_state['result_color'].capitalize() if game_state['result_color'] else 'N/A'}\n"
            f"Number: {game_state['result'] if game_state['result'] else 'N/A'}\n\n"
            f"*Total Platform Profit Today:*\n"
            f"{format_currency(get_daily_stats()['profits'])}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return GAME_SETTINGS

# Handle game settings actions
async def game_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'toggle_loss_mode':
        with app.app_context():
            loss_mode = SystemConfig.query.filter_by(key='loss_mode').first()
            
            if loss_mode:
                loss_mode.value = 'false' if loss_mode.value.lower() == 'true' else 'true'
            else:
                loss_mode = SystemConfig(key='loss_mode', value='true')
                db.session.add(loss_mode)
            
            db.session.commit()
            
            new_status = 'ON' if loss_mode.value.lower() == 'true' else 'OFF'
            
            await query.edit_message_text(
                f"Loss Mode has been turned {new_status}.\n\n"
                f"In Loss Mode, players will lose more often, increasing platform profits.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='game_settings')
                ]])
            )
        
        return GAME_SETTINGS
    
    elif query.data == 'set_min_bet':
        context.user_data['setting_min_bet'] = True
        
        await query.edit_message_text(
            "Please enter the new minimum bet amount:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data='game_settings')
            ]])
        )
        
        return GAME_SETTINGS
    
    elif query.data == 'set_max_bet':
        context.user_data['setting_max_bet'] = True
        
        await query.edit_message_text(
            "Please enter the new maximum bet amount:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data='game_settings')
            ]])
        )
        
        return GAME_SETTINGS
    
    elif query.data == 'game_stats':
        with app.app_context():
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
            
            # Get current game state
            game_state = get_game_state()
            
            await query.edit_message_text(
                f"🎮 *Game Statistics*\n\n"
                f"*Current Round:*\n"
                f"Round ID: #{game_state['round_id']}\n"
                f"Status: {game_state['status'].capitalize()}\n"
                f"Time Remaining: {int(game_state['time_remaining'])} seconds\n\n"
                f"*Today's Stats:*\n"
                f"Rounds Played: {rounds_today}\n"
                f"Total Bets: {total_bets_today}\n"
                f"Bet Volume: {format_currency(total_bet_amount_today)}\n"
                f"Total Payouts: {format_currency(total_payout_today)}\n"
                f"Platform Profit: {format_currency(profit_today)} ({(profit_today / total_bet_amount_today * 100) if total_bet_amount_today > 0 else 0:.1f}%)",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='game_settings')
                ]])
            )
        
        return GAME_SETTINGS
    
    return GAME_SETTINGS

# Handle analytics
async def handle_analytics(query, context):
    with app.app_context():
        # Get daily stats
        stats = get_daily_stats()
        
        # Get total platform stats
        total_users = User.query.count()
        active_users_24h = User.query.filter(
            User.last_active >= datetime.utcnow() - timedelta(days=1)
        ).count()
        
        total_bets = Bet.query.count()
        total_bet_volume = Bet.query.with_entities(db.func.sum(Bet.amount)).scalar() or 0
        
        keyboard = [
            [InlineKeyboardButton("📊 Detailed Reports", callback_data='detailed_reports')],
            [InlineKeyboardButton("📈 User Growth", callback_data='user_growth')],
            [InlineKeyboardButton("💰 Revenue Stats", callback_data='revenue_stats')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        
        await query.edit_message_text(
            f"📊 *Analytics Dashboard*\n\n"
            f"*Today's Overview:*\n"
            f"• New Users: {stats['new_users']}\n"
            f"• Deposits: {format_currency(stats['deposits'])}\n"
            f"• Withdrawals: {format_currency(stats['withdrawals'])}\n"
            f"• Game Profits: {format_currency(stats['profits'])}\n"
            f"• Net Income: {format_currency(stats['net_income'])}\n\n"
            f"*Platform Stats:*\n"
            f"• Total Users: {total_users}\n"
            f"• Active Users (24h): {active_users_24h}\n"
            f"• Total Bets: {total_bets}\n"
            f"• Total Betting Volume: {format_currency(total_bet_volume)}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MENU

# Handle broadcasts
async def handle_broadcast(query, context):
    keyboard = [
        [InlineKeyboardButton("📣 All Users", callback_data='broadcast_all')],
        [InlineKeyboardButton("⭐ Premium Users", callback_data='broadcast_premium')],
        [InlineKeyboardButton("🔵 Active Users (24h)", callback_data='broadcast_active')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    
    await query.edit_message_text(
        "📣 *Broadcast Messages*\n\n"
        "Send announcements or notifications to users. Choose your target audience:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return BROADCAST

# Handle broadcast actions
async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('broadcast_'):
        target = query.data.split('_')[1]
        
        if target in ['all', 'premium', 'active']:
            context.user_data['broadcast_target'] = target
            context.user_data['awaiting_broadcast'] = True
            
            target_name = {
                'all': 'all users',
                'premium': 'premium users',
                'active': 'active users in the last 24 hours'
            }[target]
            
            await query.edit_message_text(
                f"You are about to send a message to {target_name}.\n\n"
                f"Please enter your message text below:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Cancel", callback_data='broadcast')
                ]])
            )
            
            return BROADCAST
    
    elif query.data.startswith('confirm_broadcast_'):
        parts = query.data.split('_')
        target = parts[2]
        
        message = context.user_data.get('broadcast_message', '')
        
        with app.app_context():
            if target == 'all':
                users = User.query.filter_by(is_banned=False).all()
            elif target == 'premium':
                users = User.query.filter_by(is_banned=False, is_premium=True).all()
            elif target == 'active':
                yesterday = datetime.utcnow() - timedelta(days=1)
                users = User.query.filter(User.is_banned==False, User.last_active >= yesterday).all()
            else:
                users = []
            
            # For demonstration, we'll just count the users
            user_count = len(users)
            
            await query.edit_message_text(
                f"✅ Your message was sent to {user_count} users.\n\n"
                f"In a real implementation, this would go through actual channels (email, in-app, etc.).",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='broadcast')
                ]])
            )
        
        return BROADCAST
    
    return BROADCAST

# Handle support
async def handle_support(query, context):
    with app.app_context():
        # Get open support tickets
        open_tickets = SupportTicket.query.filter_by(status='open').count()
        
        # Get premium support tickets
        premium_tickets = SupportTicket.query.join(User).filter(
            SupportTicket.status == 'open',
            User.is_premium == True
        ).count()
        
        # Get recent tickets
        recent_tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).limit(5).all()
        
        keyboard = [
            [InlineKeyboardButton(f"📩 Open Tickets ({open_tickets})", callback_data='open_tickets')],
            [InlineKeyboardButton(f"⭐ Premium Support ({premium_tickets})", callback_data='premium_tickets')],
            [InlineKeyboardButton("📜 All Tickets", callback_data='all_tickets')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        
        recent_tickets_text = "\n".join([
            f"• #{ticket.id} - {ticket.user.username} - {ticket.subject[:20]}" + ("..." if len(ticket.subject) > 20 else "")
            for ticket in recent_tickets
        ]) if recent_tickets else "No recent tickets."
        
        await query.edit_message_text(
            f"🛠️ *Support Management*\n\n"
            f"*Pending Support:*\n"
            f"• Open Tickets: {open_tickets}\n"
            f"• Premium Support: {premium_tickets}\n\n"
            f"*Recent Tickets:*\n{recent_tickets_text}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SUPPORT

# Handle support actions
async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'open_tickets':
        with app.app_context():
            tickets = SupportTicket.query.filter_by(status='open').order_by(SupportTicket.created_at.desc()).limit(10).all()
            
            if not tickets:
                text = "No open tickets found."
            else:
                text = "*Open Support Tickets:*\n\n" + "\n".join([
                    f"• #{ticket.id} - {ticket.user.username} - "
                    f"{'⭐ ' if ticket.user.is_premium else ''}"
                    f"{ticket.subject[:30]}" + ("..." if len(ticket.subject) > 30 else "") + 
                    f" - [View](ticket_{ticket.id})"
                    for ticket in tickets
                ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='support')
                ]])
            )
        
        return SUPPORT
    
    elif query.data == 'premium_tickets':
        with app.app_context():
            tickets = SupportTicket.query.join(User).filter(
                SupportTicket.status == 'open',
                User.is_premium == True
            ).order_by(SupportTicket.created_at.desc()).limit(10).all()
            
            if not tickets:
                text = "No premium support tickets found."
            else:
                text = "*Premium Support Tickets:*\n\n" + "\n".join([
                    f"• #{ticket.id} - {ticket.user.username} - "
                    f"{ticket.subject[:30]}" + ("..." if len(ticket.subject) > 30 else "") + 
                    f" - [View](ticket_{ticket.id})"
                    for ticket in tickets
                ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='support')
                ]])
            )
        
        return SUPPORT
    
    elif query.data == 'all_tickets':
        with app.app_context():
            tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).limit(10).all()
            
            if not tickets:
                text = "No tickets found."
            else:
                text = "*Recent Support Tickets:*\n\n" + "\n".join([
                    f"• #{ticket.id} - {ticket.user.username} - "
                    f"{'⭐ ' if ticket.user.is_premium else ''}"
                    f"{'🟢 ' if ticket.status == 'open' else '🔴 '}"
                    f"{ticket.subject[:25]}" + ("..." if len(ticket.subject) > 25 else "") + 
                    f" - [View](ticket_{ticket.id})"
                    for ticket in tickets
                ])
            
            await query.edit_message_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back", callback_data='support')
                ]])
            )
        
        return SUPPORT
    
    elif query.data.startswith('ticket_'):
        ticket_id = int(query.data.split('_')[1])
        
        with app.app_context():
            ticket = SupportTicket.query.get(ticket_id)
            
            if not ticket:
                await query.edit_message_text(
                    "Ticket not found.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back", callback_data='support')
                    ]])
                )
                return SUPPORT
            
            # Get messages for this ticket
            messages = SupportMessage.query.filter_by(ticket_id=ticket.id).order_by(SupportMessage.created_at).all()
            
            messages_text = "\n\n".join([
                f"{'👤 ' + (message.user.username if message.user else 'User') if not message.is_admin else '👨‍💼 Admin'}:\n"
                f"{message.message}\n"
                f"({message.created_at.strftime('%Y-%m-%d %H:%M')})"
                for message in messages
            ]) if messages else "No messages in this ticket yet."
            
            # Create keyboard
            keyboard = []
            
            if ticket.status == 'open':
                keyboard.append([InlineKeyboardButton("✉️ Reply", callback_data=f'reply_{ticket.id}')])
                keyboard.append([InlineKeyboardButton("🔴 Close Ticket", callback_data=f'close_{ticket.id}')])
            else:
                keyboard.append([InlineKeyboardButton("✉️ Reply & Reopen", callback_data=f'reply_{ticket.id}')])
            
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='support')])
            
            # Format response
            user_info = f"{'⭐ Premium User' if ticket.user.is_premium else 'Regular User'}"
            
            await query.edit_message_text(
                f"*Support Ticket #{ticket.id}*\n\n"
                f"*Subject:* {ticket.subject}\n"
                f"*From:* {ticket.user.username} ({user_info})\n"
                f"*Status:* {'Open' if ticket.status == 'open' else 'Closed'}\n"
                f"*Date:* {ticket.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"*Messages:*\n{messages_text}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return SUPPORT
    
    elif query.data.startswith('reply_'):
        ticket_id = int(query.data.split('_')[1])
        
        context.user_data['awaiting_support_reply'] = True
        context.user_data['support_ticket_id'] = ticket_id
        
        await query.edit_message_text(
            f"Please enter your reply to ticket #{ticket_id}:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data=f'ticket_{ticket_id}')
            ]])
        )
        
        return SUPPORT
    
    elif query.data.startswith('close_'):
        ticket_id = int(query.data.split('_')[1])
        
        with app.app_context():
            ticket = SupportTicket.query.get(ticket_id)
            
            if ticket:
                ticket.status = 'closed'
                db.session.commit()
                
                await query.edit_message_text(
                    f"Ticket #{ticket.id} has been closed.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Ticket", callback_data=f'ticket_{ticket.id}')
                    ]])
                )
        
        return SUPPORT
    
    return SUPPORT

# Error handler
async def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}")

# Main function to start the bot
def init_telegram_bot():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [CallbackQueryHandler(menu_callback)],
            USER_ACTION: [
                CallbackQueryHandler(user_action_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message),
            ],
            TRANSACTION_ACTION: [CallbackQueryHandler(transaction_action_callback)],
            GAME_SETTINGS: [CallbackQueryHandler(game_settings_callback)],
            BROADCAST: [CallbackQueryHandler(broadcast_callback)],
            SUPPORT: [CallbackQueryHandler(support_callback)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    application.run_polling()

# Start the bot in a separate thread
def start_telegram_bot():
    threading.Thread(target=init_telegram_bot, daemon=True).start()
    logging.info("Telegram bot started")

# Initialize the telegram bot
try:
    start_telegram_bot()
except Exception as e:
    logging.error(f"Failed to start Telegram bot: {str(e)}")
