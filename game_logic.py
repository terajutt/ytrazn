import random
import time
import threading
import logging
from datetime import datetime

from app import app, db
from models import GameRound, Bet, User, Transaction, SystemConfig
from config import (
    GAME_DURATION, 
    RED_PAYOUT_MULTIPLIER, 
    GREEN_PAYOUT_MULTIPLIER, 
    VIOLET_PAYOUT_MULTIPLIER, 
    PLATFORM_FEE_PERCENTAGE,
    MAX_CONSECUTIVE_LOSSES,
    WIN_BOOST_PERCENTAGE
)

# Global variable to store the current game state
current_game = {
    'round_id': None,
    'start_time': None,
    'end_time': None,
    'status': 'waiting',  # waiting, active, ended
    'bets': {},
    'result': None,
    'result_color': None,
    'total_bets': 0,
    'total_payout': 0
}

# Lock for thread safety
game_lock = threading.Lock()

def get_user_consecutive_losses(user_id):
    """Get the number of consecutive losses for a user"""
    consecutive_losses = 0
    bets = Bet.query.filter_by(user_id=user_id).order_by(Bet.timestamp.desc()).limit(MAX_CONSECUTIVE_LOSSES).all()
    
    for bet in bets:
        if not bet.is_win:
            consecutive_losses += 1
        else:
            break
    
    return consecutive_losses

def get_win_probability_boost(user_id):
    """Calculate probability boost based on consecutive losses"""
    consecutive_losses = get_user_consecutive_losses(user_id)
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return WIN_BOOST_PERCENTAGE
    return 0

def determine_result(force_result=None, loss_mode=False):
    """Determine the result of the game round"""
    with app.app_context():
        if force_result:
            return force_result
        
        # Check for first-time player bets (guaranteed wins)
        first_win_configs = SystemConfig.query.filter(
            SystemConfig.key.like(f'first_win_{current_game["round_id"]}_%')
        ).all()
        
        if first_win_configs:
            # If there are first-time players, use their bet color to guarantee a win
            # Just use the first one found for simplicity
            return first_win_configs[0].value
        
        # Check if loss mode is enabled
        if loss_mode:
            # Make players more likely to lose (house advantage)
            weights = {
                'most_bet_color': 0.2,  # 20% chance to get the most bet color (players win)
                'other_colors': 0.8  # 80% chance to get other colors (most players lose)
            }
        else:
            # Normal mode (still house advantage but less aggressive)
            weights = {
                'most_bet_color': 0.3,  # 30% chance to get the most bet color
                'other_colors': 0.7  # 70% chance to get other colors
            }
        
        # Calculate total bets per color
        red_bets = sum(bet_data['amount'] for bet_data in current_game['bets'].values() if bet_data['color'] == 'red')
        green_bets = sum(bet_data['amount'] for bet_data in current_game['bets'].values() if bet_data['color'] == 'green')
        violet_bets = sum(bet_data['amount'] for bet_data in current_game['bets'].values() if bet_data['color'] == 'violet')
        
        # Determine most bet color
        color_bets = {
            'red': red_bets,
            'green': green_bets,
            'violet': violet_bets
        }
        
        if not color_bets:
            # No bets, completely random
            return random.choice(['red', 'green', 'violet'])
        
        most_bet_color = max(color_bets, key=color_bets.get)
        other_colors = [color for color in ['red', 'green', 'violet'] if color != most_bet_color]
        
        # Choose between most bet color and other colors based on weights
        if random.random() < weights['most_bet_color']:
            return most_bet_color
        else:
            return random.choice(other_colors)

def start_new_round():
    """Start a new game round"""
    global current_game
    
    with game_lock:
        with app.app_context():
            # Create a new game round in the database
            new_round = GameRound()
            db.session.add(new_round)
            db.session.commit()
            
            current_game = {
                'round_id': new_round.id,
                'start_time': time.time(),
                'end_time': time.time() + GAME_DURATION,
                'status': 'active',
                'bets': {},
                'result': None,
                'result_color': None,
                'total_bets': 0,
                'total_payout': 0
            }
            
            logging.debug(f"New game round started: {new_round.id}")
            
            # Schedule the end of this round
            threading.Timer(GAME_DURATION, end_round).start()
            
    return current_game

def end_round():
    """End the current game round and calculate results"""
    global current_game
    
    with game_lock:
        if current_game['status'] == 'ended':
            # Start a new round immediately if we're trying to end a round that's already ended
            threading.Timer(1, start_new_round).start()
            return  # Round already ended
        
        # Set status to ended immediately to avoid race conditions
        current_game['status'] = 'ended'
        
        with app.app_context():
            # Check if loss mode is enabled
            loss_mode_config = SystemConfig.query.filter_by(key='loss_mode').first()
            loss_mode = loss_mode_config and loss_mode_config.value.lower() == 'true'
            
            # Determine the result
            result_color = determine_result(loss_mode=loss_mode)
            current_game['result_color'] = result_color
            
            # Generate a random number for the result
            if result_color == 'red':
                result_number = random.choice([1, 3, 5, 7, 9])
            elif result_color == 'green':
                result_number = random.choice([2, 4, 6, 8, 10])
            else:  # violet
                result_number = random.choice([0])
            
            current_game['result'] = result_number
            
            # Update the game round in the database
            game_round = GameRound.query.get(current_game['round_id'])
            game_round.result_color = result_color
            game_round.result_number = result_number
            
            # Process all bets
            total_bet_amount = 0
            total_payout = 0
            
            for bet_id, bet_data in current_game['bets'].items():
                bet = Bet.query.get(bet_id)
                if not bet:
                    continue
                
                total_bet_amount += bet.amount
                
                # Calculate if the bet is a win
                won = False
                payout = 0
                
                # Apply user retention boost if applicable
                win_boost = get_win_probability_boost(bet.user_id)
                
                if bet.color == result_color:
                    # Standard win
                    won = True
                    if bet.color == 'red':
                        payout = bet.amount * RED_PAYOUT_MULTIPLIER
                    elif bet.color == 'green':
                        payout = bet.amount * GREEN_PAYOUT_MULTIPLIER
                    else:  # violet
                        payout = bet.amount * VIOLET_PAYOUT_MULTIPLIER
                elif win_boost > 0 and random.random() < (win_boost / 100):
                    # User retention boost - give them a win to keep them engaged
                    won = True
                    payout = bet.amount * 1.5  # Reduced payout for retention wins
                
                # Update the bet record
                bet.is_win = won
                bet.payout = payout
                
                # Update user balance
                user = User.query.get(bet.user_id)
                if won:
                    user.balance += payout
                    # Create transaction record for win
                    win_txn = Transaction(
                        user_id=user.id,
                        amount=payout,
                        txn_type='game_win',
                        status='approved',
                        approved_at=datetime.utcnow()
                    )
                    db.session.add(win_txn)
                
                # Update user betting volume for loyalty level
                user.betting_volume += bet.amount
                user.last_active = datetime.utcnow()
                
                # Check if user should level up
                from config import LOYALTY_LEVELS
                for i, level in enumerate(LOYALTY_LEVELS):
                    if user.betting_volume >= level['volume_required'] and user.loyalty_level < i:
                        user.loyalty_level = i
                
                total_payout += payout
            
            # Update the game round with the results
            game_round.total_bet_amount = total_bet_amount
            game_round.total_payout = total_payout
            game_round.platform_profit = total_bet_amount - total_payout
            
            # Update current game state
            current_game['status'] = 'ended'
            current_game['total_bets'] = total_bet_amount
            current_game['total_payout'] = total_payout
            
            # Clean up first win records for this round
            first_win_configs = SystemConfig.query.filter(
                SystemConfig.key.like(f'first_win_{current_game["round_id"]}_%')
            ).all()
            for config in first_win_configs:
                db.session.delete(config)
            
            db.session.commit()
            
            logging.debug(f"Game round ended: {game_round.id}, Result: {result_color} {result_number}, Profit: {game_round.platform_profit}")
            
            # Start a new round after a short delay
            threading.Timer(3, start_new_round).start()
    
    return current_game

def place_bet(user_id, amount, color):
    """Place a bet in the current round"""
    global current_game
    
    with game_lock:
        if current_game['status'] != 'active':
            return {'success': False, 'message': 'No active game round'}
        
        with app.app_context():
            user = User.query.get(user_id)
            if not user:
                return {'success': False, 'message': 'User not found'}
            
            if user.is_banned:
                return {'success': False, 'message': 'Your account is banned'}
            
            if user.balance < amount:
                return {'success': False, 'message': 'Insufficient balance'}
            
            if color not in ['red', 'green', 'violet']:
                return {'success': False, 'message': 'Invalid color selection'}
            
            # Check if this is the user's first bet
            is_first_bet = not user.first_bet_made
            
            # Deduct the bet amount from user balance
            user.balance -= amount
            
            # Create a new bet
            bet = Bet(
                user_id=user_id,
                game_round_id=current_game['round_id'],
                amount=amount,
                color=color
            )
            db.session.add(bet)
            
            # Mark that the user has made their first bet
            if is_first_bet:
                user.first_bet_made = True
                
                # Force a win for first-time players only if bet amount is 100 or less
                if amount <= 100:
                    # Store this in a dedicated field to be used during result calculation
                    sys_config = SystemConfig.query.filter_by(key=f'first_win_{current_game["round_id"]}_{user_id}').first()
                    if not sys_config:
                        sys_config = SystemConfig(
                            key=f'first_win_{current_game["round_id"]}_{user_id}',
                            value=color
                        )
                        db.session.add(sys_config)
            
            db.session.commit()
            
            # Add to current game bets
            current_game['bets'][bet.id] = {
                'user_id': user_id,
                'amount': amount,
                'color': color,
                'is_first_bet': is_first_bet
            }
            
            # Create a transaction record for the bet
            bet_txn = Transaction(
                user_id=user_id,
                amount=-amount,
                txn_type='game_bet',
                status='approved',
                approved_at=datetime.utcnow()
            )
            db.session.add(bet_txn)
            db.session.commit()
            
            return {
                'success': True, 
                'message': f'Bet placed on {color}',
                'bet_id': bet.id,
                'new_balance': user.balance
            }

def get_game_state():
    """Get the current game state"""
    with game_lock:
        return {
            'round_id': current_game['round_id'],
            'status': current_game['status'],
            'start_time': current_game['start_time'],
            'end_time': current_game['end_time'],
            'time_remaining': max(0, current_game['end_time'] - time.time()) if current_game['end_time'] else 0,
            'result': current_game['result'],
            'result_color': current_game['result_color'],
            'total_bets': current_game['total_bets'],
            'total_payout': current_game['total_payout']
        }

# Start the game engine when the module is loaded
def init_game_engine():
    """Initialize the game engine"""
    logging.debug("Initializing game engine...")
    threading.Timer(1, start_new_round).start()

# Initialize the game engine
init_game_engine()
