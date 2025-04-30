import os

# General settings
APP_NAME = "YTRAZN Trading"
APP_VERSION = "1.0.0"

# Email settings
EMAIL_SENDER = "merajija307@gmail.com"
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "petlgoctafgdxmsg")
EMAIL_SERVER = "smtp.gmail.com"
EMAIL_PORT = 587

# SMS settings
SMS_API_KEY = os.environ.get("SMS_API_KEY", "3fbb0050-1aae-11f0-8b17-0200cd936042")

# Telegram bot settings
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7997260719:AAFKEwViZ_JUEQl9KSUEKRfgL7Q93ffkSx0")
ADMIN_TELEGRAM_IDS = ["6652452460"]  # Add your actual Telegram ID here

# Game settings
GAME_DURATION = 60  # seconds
MIN_BET = 10
MAX_BET = 10000
RED_PAYOUT_MULTIPLIER = 1.9  # 90% return
GREEN_PAYOUT_MULTIPLIER = 1.9  # 90% return
VIOLET_PAYOUT_MULTIPLIER = 7.7  # Special (higher odds, higher payout)

# Platform settings
PLATFORM_FEE_PERCENTAGE = 15  # Platform keeps 15% of all bets
WITHDRAWAL_MIN = 100
WITHDRAWAL_MAX = 10000
PREMIUM_SUBSCRIPTION_COST = 299
PREMIUM_DURATION_DAYS = 30

# Loyalty levels configuration
LOYALTY_LEVELS = [
    {"name": "Beginner", "volume_required": 0, "benefits": "Basic access"},
    {"name": "Novice", "volume_required": 1000, "benefits": "1% cashback on bets"},
    {"name": "Intermediate", "volume_required": 5000, "benefits": "2% cashback on bets"},
    {"name": "Advanced", "volume_required": 20000, "benefits": "3% cashback on bets, faster withdrawals"},
    {"name": "Expert", "volume_required": 50000, "benefits": "4% cashback on bets, VIP support"},
    {"name": "Master", "volume_required": 100000, "benefits": "5% cashback on bets, priority withdrawals"},
    {"name": "Legend", "volume_required": 250000, "benefits": "7% cashback on bets, all premium features free"},
]

# User retention settings
MAX_CONSECUTIVE_LOSSES = 10  # After this many losses, increase win chance
WIN_BOOST_PERCENTAGE = 20  # Increase win chance by this percentage for retention
