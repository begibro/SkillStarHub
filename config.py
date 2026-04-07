import os

from dotenv import load_dotenv

load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
REFERRAL_REWARD = 10
VIP_DAILY_BONUS = 5
VIP_PRICE = 500
