 
import os
import logging
import sys
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import Conflict
from gtts import gTTS
import io
import asyncio
from datetime import datetime
import re
import math
import requests
from urllib.parse import quote
from yt_dlp import YoutubeDL
import random
import string
import platform
import tempfile
import hashlib

# Fix for httpcore asyncio detection on Windows (only for Windows)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Try to import moviepy for video to audio conversion
MOVIEPY_AVAILABLE = False
VideoFileClip = None
try:
    # Try standard import first (moviepy 2.0+)
    from moviepy import VideoFileClip
    MOVIEPY_AVAILABLE = True
    logger.info("MoviePy is available for video to audio conversion!")
except (ImportError, ModuleNotFoundError):
    # Try alternative import for older versions (moviepy 1.x)
    try:
        from moviepy.editor import VideoFileClip  # pyright: ignore
        MOVIEPY_AVAILABLE = True
        logger.info("MoviePy is available (using alternative import)!")
    except (ImportError, ModuleNotFoundError) as e:
        MOVIEPY_AVAILABLE = False
        VideoFileClip = None
        logger.warning(f"MoviePy not available. Install with: pip install moviepy. Error: {e}")
except Exception as e:
    MOVIEPY_AVAILABLE = False
    VideoFileClip = None
    logger.warning(f"MoviePy import error: {e}")

# Try to import PIL for image processing
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont
    PIL_AVAILABLE = True
    IMAGEDRAW_AVAILABLE = True
    IMAGEFONT_AVAILABLE = True
    try:
        import importlib
        np = importlib.import_module("numpy")
        NUMPY_AVAILABLE = True
    except Exception:
        NUMPY_AVAILABLE = False
        logger.info("NumPy not available. Background blur will use basic blending.")
except ImportError as e:
    PIL_AVAILABLE = False
    NUMPY_AVAILABLE = False
    IMAGEDRAW_AVAILABLE = False
    IMAGEFONT_AVAILABLE = False
    ImageDraw = None
    ImageFont = None
    logger.warning(f"PIL/Pillow not available: {e}. Image editing features will be disabled.")

# Try to import PyMuPDF (fitz) for PDF processing
PDF_AVAILABLE = False
PDF_ERROR = None
try:
    import fitz  # PyMuPDF
    # Test if it actually works (not just imports)
    try:
        # Try to create a simple test to verify it works
        test_doc = fitz.open()
        test_doc.close()
        PDF_AVAILABLE = True
        logger.info("PyMuPDF is available and working!")
    except Exception as e:
        PDF_AVAILABLE = False
        PDF_ERROR = str(e)
        logger.warning(f"PyMuPDF imported but not functional: {e}. PDF to image conversion will be disabled.")
except ImportError as e:
    PDF_AVAILABLE = False
    error_str = str(e)
    PDF_ERROR = error_str
    if "DLL" in error_str or "load failed" in error_str.lower():
        logger.warning(f"PyMuPDF DLL load error: {e}. This usually means Visual C++ Redistributables are missing or Python version incompatibility.")
    else:
        logger.info(f"PyMuPDF not available: {e}. PDF to image conversion will be disabled. Install: pip install PyMuPDF")
except Exception as e:
    PDF_AVAILABLE = False
    PDF_ERROR = str(e)
    logger.warning(f"PyMuPDF error: {e}. PDF to image conversion will be disabled.")

# Bot token - Get from environment variable or use default for local testing
BOT_TOKEN = os.getenv("BOT_TOKEN", "8443653460:AAH2e35lpAHdyaXKFwq-6--zxEEzTr176-k")
# OCR.space API key: set environment variable OCR_SPACE_API_KEY to override the free demo key
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "helloworld").strip() or "helloworld"

# Bot name - Change this to customize bot name in messages
BOT_NAME = os.getenv("BOT_NAME", "All Smart Tool Bot")  # Default bot name

# Required channel for users to join
REQUIRED_CHANNEL = "@devoloper_rakibhasan"  # Channel username
REQUIRED_CHANNEL_LINK = "https://t.me/devoloper_rakibhasan"

# Admin IDs - Set via environment variable ADMIN_IDS (comma-separated) or use default
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()] if admin_ids_str else []
# Add bot owner as default admin if ADMIN_IDS is empty
# You can add your Telegram user ID here directly in code:
# ADMIN_IDS = [YOUR_USER_ID]  # Replace YOUR_USER_ID with your actual Telegram user ID
# To find your user ID, use @userinfobot on Telegram

# Add default admin if ADMIN_IDS is empty
if not ADMIN_IDS:
    ADMIN_IDS = [6393419765]  # Default admin user ID

# User data storage
USER_DATA_FILE = "users.json"
user_data = {}

# Blocked users storage
BLOCKED_USERS_FILE = "blocked_users.json"
blocked_users = set()

# Alarm storage
ALARMS_FILE = "alarms.json"
alarms = {}  # {user_id: [{alarm_id, time, message, created_at}]}

def load_alarms():
    """Load alarms from JSON file."""
    global alarms
    if os.path.exists(ALARMS_FILE):
        try:
            with open(ALARMS_FILE, 'r', encoding='utf-8') as f:
                alarms = json.load(f)
                # Convert string keys to int for user_id
                alarms = {int(k): v for k, v in alarms.items()}
        except Exception as e:
            logger.error(f"Error loading alarms: {e}")
            alarms = {}
    else:
        alarms = {}

def save_alarms():
    """Save alarms to JSON file."""
    try:
        with open(ALARMS_FILE, 'w', encoding='utf-8') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving alarms: {e}")

async def check_alarms_loop(bot):
    """Background task loop to check and trigger alarms."""
    while True:
        try:
            current_time = datetime.now()
            current_time_str = current_time.strftime("%H:%M")
            
            # Check all alarms
            alarms_to_remove = []
            for user_id, user_alarms in list(alarms.items()):
                for alarm in user_alarms[:]:  # Create a copy to iterate
                    alarm_time = alarm.get('time', '')
                    alarm_id = alarm.get('alarm_id', '')
                    
                    # Check if alarm time matches current time (HH:MM format)
                    if alarm_time == current_time_str:
                        try:
                            message = alarm.get('message', '⏰ Alarm!')
                            
                            # Send notification messages with sound/alert effect
                            # Send multiple quick messages to ensure phone notification sound
                            notification_messages = [
                                "🔔🔔🔔",
                                "🔔",
                                f"⏰ **ALARM!** ⏰\n\n{message}\n\n🔔 Wake Up! 🔔"
                            ]
                            
                            for i, notif_text in enumerate(notification_messages):
                                await bot.send_message(
                                    chat_id=user_id,
                                    text=notif_text,
                                    parse_mode='Markdown' if i == 2 else None,
                                    disable_notification=False  # Ensure notification sound plays
                                )
                                if i < len(notification_messages) - 1:
                                    await asyncio.sleep(0.5)  # Delay between notifications
                            
                            alarms_to_remove.append((user_id, alarm_id))
                            logger.info(f"Alarm triggered for user {user_id}: {message}")
                        except Exception as e:
                            logger.error(f"Error sending alarm to user {user_id}: {e}")
                            # Remove alarm if user blocked bot or chat not found
                            if "chat not found" in str(e).lower() or "blocked" in str(e).lower():
                                alarms_to_remove.append((user_id, alarm_id))
            
            # Remove triggered alarms
            for user_id, alarm_id in alarms_to_remove:
                if user_id in alarms:
                    alarms[user_id] = [a for a in alarms[user_id] if a.get('alarm_id') != alarm_id]
                    if not alarms[user_id]:
                        del alarms[user_id]
                    save_alarms()
            
            # Wait 60 seconds before next check
            await asyncio.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in alarm check task: {e}")
            await asyncio.sleep(60)

async def ocrsetup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diagnose OCR setup and provide actionable guidance."""
    lines = []
    # API key status
    if 'helloworld' in OCR_SPACE_API_KEY:
        lines.append("🔑 OCR.space API key: using demo key (set OCR_SPACE_API_KEY)\n")
    else:
        key_mask = OCR_SPACE_API_KEY[:4] + "***"
        lines.append(f"🔑 OCR.space API key: set ({key_mask})\n")
    # pytesseract and tesseract status
    try:
        import pytesseract  # noqa: F401
        has_pyt = True
    except Exception:
        has_pyt = False
    import shutil
    tesseract_path = shutil.which('tesseract')
    default_win_path = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    if not tesseract_path and os.path.exists(default_win_path):
        tesseract_path = default_win_path
    if has_pyt and tesseract_path:
        lines.append(f"🧩 Local OCR: ready ({tesseract_path})\n")
    elif has_pyt and not tesseract_path:
        lines.append("🧩 Local OCR: pytesseract installed, tesseract.exe not found\n")
    elif not has_pyt and tesseract_path:
        lines.append("🧩 Local OCR: tesseract.exe found, install pytesseract (pip install pytesseract)\n")
    else:
        lines.append("🧩 Local OCR: not installed\n")
    lines.append("\n👉 For Bangla OCR, ensure Tesseract + ben.traineddata is installed.\n")
    await update.message.reply_text(''.join(lines))

# User data management functions
def load_user_data():
    """Load user data from JSON file."""
    global user_data
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading user data: {e}")
            user_data = {}
    else:
        user_data = {}

def save_user_data():
    """Save user data to JSON file."""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving user data: {e}")

def track_user(user_id, username=None, first_name=None, last_name=None):
    """Track user when they interact with bot."""
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            'id': user_id,
            'username': username,
            'first_name': first_name,
            'last_name': last_name,
            'first_seen': datetime.now().isoformat(),
            'last_seen': datetime.now().isoformat(),
            'command_count': 0
        }
    else:
        user_data[user_id_str]['last_seen'] = datetime.now().isoformat()
        if username:
            user_data[user_id_str]['username'] = username
        if first_name:
            user_data[user_id_str]['first_name'] = first_name
        if last_name:
            user_data[user_id_str]['last_name'] = last_name
    save_user_data()

def increment_command_count(user_id):
    """Increment command usage count for user."""
    user_id_str = str(user_id)
    if user_id_str in user_data:
        user_data[user_id_str]['command_count'] = user_data[user_id_str].get('command_count', 0) + 1
        save_user_data()

def escape_markdown(text):
    """Escape special Markdown characters for Telegram."""
    if not text:
        return text
    # Escape special Markdown characters
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text

def get_admin_contacts():
    """Get admin usernames for contact information."""
    admin_contacts = []
    for admin_id in ADMIN_IDS:
        admin_info = user_data.get(str(admin_id), {})
        username = admin_info.get('username', None)
        if username and username != 'N/A':
            admin_contacts.append(f"@{username}")
        else:
            # If no username, use user ID
            admin_contacts.append(f"User ID: `{admin_id}`")
    return admin_contacts

async def get_admin_contacts_async(context):
    """Get admin usernames for contact information (async version with bot context)."""
    admin_contacts = []
    for admin_id in ADMIN_IDS:
        try:
            # Try to get user info from Telegram API
            user_chat = await context.bot.get_chat(admin_id)
            if user_chat.username:
                admin_contacts.append(f"@{user_chat.username}")
            else:
                # If no username, try to get from user_data or show name
                admin_info = user_data.get(str(admin_id), {})
                username = admin_info.get('username', None)
                if username and username != 'N/A' and username:
                    admin_contacts.append(f"@{username}")
                else:
                    name = user_chat.first_name or "Admin"
                    admin_contacts.append(f"{name} (ID: `{admin_id}`)")
        except Exception as e:
            # If API call fails, fall back to user_data
            logger.warning(f"Could not fetch admin info for {admin_id}: {e}")
            admin_info = user_data.get(str(admin_id), {})
            username = admin_info.get('username', None)
            if username and username != 'N/A' and username:
                admin_contacts.append(f"@{username}")
            else:
                admin_contacts.append(f"User ID: `{admin_id}`")
    return admin_contacts

# Admin check function
def is_admin(user_id):
    """Check if user is admin."""
    return user_id in ADMIN_IDS

async def admin_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is admin."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        await update.message.reply_text(
            "❌ **Access Denied**\n\n"
            "🔒 This command is only available for administrators.",
            parse_mode='Markdown'
        )
        return False
    return True

async def check_user_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is blocked and return True if blocked, False if not."""
    user = update.effective_user
    if not user:
        return False
    
    user_id = user.id
    if is_user_blocked(user_id):
        try:
            admin_contacts = await get_admin_contacts_async(context)
            contact_text = ""
            if admin_contacts:
                contact_text = "\n\n**Contact Admin:**\n"
                for contact in admin_contacts:
                    contact_text += f"• {contact}\n"
            else:
                contact_text = "\n\nIf you believe this is an error, please contact the bot administrator."
        except Exception as e:
            logger.warning(f"Error getting admin contacts: {e}")
            admin_contacts = get_admin_contacts()
            contact_text = ""
            if admin_contacts:
                contact_text = "\n\n**Contact Admin:**\n"
                for contact in admin_contacts:
                    contact_text += f"• {contact}\n"
            else:
                contact_text = "\n\nIf you believe this is an error, please contact the bot administrator."
        
        try:
            await update.message.reply_text(
                f"🚫 **Access Denied**\n\n"
                f"❌ You have been blocked from using this bot.{contact_text}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not send block message: {e}")
        
        return True
    return False

def block_check_decorator(func):
    """Decorator to add block check to command functions."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await check_user_blocked(update, context):
            return
        return await func(update, context)
    return wrapper

# Blocked users management functions
def load_blocked_users():
    """Load blocked users from JSON file."""
    global blocked_users
    if os.path.exists(BLOCKED_USERS_FILE):
        try:
            with open(BLOCKED_USERS_FILE, 'r', encoding='utf-8') as f:
                blocked_list = json.load(f)
                blocked_users = set(blocked_list)
        except Exception as e:
            logger.error(f"Error loading blocked users: {e}")
            blocked_users = set()
    else:
        blocked_users = set()

def save_blocked_users():
    """Save blocked users to JSON file."""
    try:
        with open(BLOCKED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(blocked_users), f, indent=2)
    except Exception as e:
        logger.error(f"Error saving blocked users: {e}")

def is_user_blocked(user_id):
    """Check if user is blocked."""
    return str(user_id) in blocked_users

def block_user(user_id):
    """Block a user."""
    blocked_users.add(str(user_id))
    save_blocked_users()

def unblock_user(user_id):
    """Unblock a user."""
    blocked_users.discard(str(user_id))
    save_blocked_users()

# Load user data and blocked users on startup
load_user_data()
load_blocked_users()
load_alarms()

# Referral system storage
REFERRAL_DATA_FILE = "referrals.json"
referral_data = {}

def load_referral_data():
    """Load referral data from file."""
    global referral_data
    try:
        if os.path.exists(REFERRAL_DATA_FILE):
            with open(REFERRAL_DATA_FILE, 'r', encoding='utf-8') as f:
                referral_data = json.load(f)
        else:
            referral_data = {}
    except Exception as e:
        logger.warning(f"Error loading referral data: {e}")
        referral_data = {}

def save_referral_data():
    """Save referral data to file."""
    try:
        with open(REFERRAL_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(referral_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving referral data: {e}")

def generate_referral_code(user_id, user_name=None):
    """Generate or get referral code for user."""
    if str(user_id) not in referral_data:
        # Generate uppercase code
        code = f"REF{user_id % 10000:04d}".upper()
        referral_data[str(user_id)] = {
            'code': code,
            'referrals': [],
            'total_referrals': 0,
            'joined_at': datetime.now().isoformat(),
            'name': user_name or f"User{user_id % 10000}"
        }
        save_referral_data()
        logger.info(f"Generated referral code {code} for user {user_id}")
    elif user_name and referral_data[str(user_id)].get('name') != user_name:
        # Update name if provided and different
        referral_data[str(user_id)]['name'] = user_name
        save_referral_data()
    
    # Ensure code is uppercase
    code = referral_data[str(user_id)]['code'].upper()
    if referral_data[str(user_id)]['code'] != code:
        referral_data[str(user_id)]['code'] = code
        save_referral_data()
    
    return code

async def add_referral(context, referrer_code, new_user_id, new_user_name):
    """Add a referral when someone uses a code and notify referrer."""
    try:
        # Normalize referral code to uppercase
        referrer_code = referrer_code.upper().strip()
        
        logger.info(f"Looking for referral code: {referrer_code} for user {new_user_id}")
        
        # Find referrer by code (case-insensitive comparison)
        referrer_id = None
        for uid, data in referral_data.items():
            stored_code = data.get('code', '').upper().strip()
            if stored_code == referrer_code:
                referrer_id = uid
                logger.info(f"Found referrer {referrer_id} for code {referrer_code}")
                break
        
        if not referrer_id:
            logger.warning(f"Referral code '{referrer_code}' not found in referral_data. Available codes: {[data.get('code') for data in referral_data.values()]}")
            return False
        
        if str(new_user_id) == referrer_id:
            logger.info(f"User {new_user_id} tried to use their own referral code")
            return False
        
        # Get or create referrals list
        if referrer_id not in referral_data:
            logger.warning(f"Referrer {referrer_id} not found in referral_data")
            return False
        
        # Ensure referrals list exists
        if 'referrals' not in referral_data[referrer_id]:
            referral_data[referrer_id]['referrals'] = []
        
        referrals_list = referral_data[referrer_id].get('referrals', [])
        
        # Check if user is already in list
        if str(new_user_id) in referrals_list:
            logger.info(f"User {new_user_id} already in referrer {referrer_id}'s referral list")
            # Still update and save to ensure count is correct
            actual_count = len(referrals_list)
            if referral_data[referrer_id].get('total_referrals', 0) != actual_count:
                referral_data[referrer_id]['total_referrals'] = actual_count
                save_referral_data()
            return False
        
        # Add to referrer's list
        referrals_list.append(str(new_user_id))
        referral_data[referrer_id]['referrals'] = referrals_list
        
        # Update total_referrals based on actual list length (always sync)
        new_total = len(referrals_list)
        referral_data[referrer_id]['total_referrals'] = new_total
        
        # Force save immediately
        save_referral_data()
        
        # Verify the save was successful
        if referral_data[referrer_id]['total_referrals'] != new_total:
            logger.error(f"Count mismatch after save! Expected {new_total}, got {referral_data[referrer_id]['total_referrals']}")
            # Force correct it
            referral_data[referrer_id]['total_referrals'] = new_total
            save_referral_data()
        
        logger.info(f"Added referral: User {new_user_id} added to referrer {referrer_id}'s list. Total referrals: {new_total} (List length: {len(referrals_list)})")
        
        # Notify the referrer
        try:
            referrer_name = referral_data[referrer_id].get('name', 'Someone')
            # Get the actual count again to ensure accuracy
            actual_count = len(referral_data[referrer_id].get('referrals', []))
            notification_text = (
                f"🎉 **New Referral!**\n\n"
                f"✅ Someone joined using your referral code: **{referrer_code}**\n\n"
                f"👤 **New User:** {new_user_name}\n"
                f"📊 **Your Total Referrals:** {actual_count}\n\n"
                f"💡 Keep sharing your referral link to get more referrals!\n"
                f"🔗 Use `/refer` to see your referral code and stats"
            )
            
            # Send notification to referrer
            await context.bot.send_message(
                chat_id=int(referrer_id),
                text=notification_text,
                parse_mode='Markdown'
            )
            logger.info(f"Notification sent to referrer {referrer_id}")
        except Exception as e:
            logger.warning(f"Could not notify referrer {referrer_id}: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in add_referral: {e}", exc_info=True)
        return False

# Load referral data on startup
load_referral_data()

async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is a member of the required channel."""
    user = update.effective_user
    if not user:
        return False
    
    try:
        # Check if user is member of the channel
        member = await context.bot.get_chat_member(REQUIRED_CHANNEL, user.id)
        # Member status can be: member, administrator, creator, left, kicked, restricted
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        # If bot is not admin or channel doesn't exist, we can't check
        # For now, we'll allow access but log the error
        logger.warning(f"Could not check channel membership: {e}")
        # In production, you might want to return False here
        # For now, return True to allow access if check fails
        return True
    
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    user_id = user.id if user else None
    
    # Check if user is blocked
    if user_id and is_user_blocked(user_id):
        try:
            admin_contacts = await get_admin_contacts_async(context)
            contact_text = ""
            if admin_contacts:
                contact_text = "\n\n**Contact Admin:**\n"
                for contact in admin_contacts:
                    contact_text += f"• {contact}\n"
            else:
                contact_text = "\n\nIf you believe this is an error, please contact the bot administrator."
        except Exception as e:
            logger.warning(f"Error getting admin contacts: {e}")
            # Fallback to simple function
            admin_contacts = get_admin_contacts()
            contact_text = ""
            if admin_contacts:
                contact_text = "\n\n**Contact Admin:**\n"
                for contact in admin_contacts:
                    contact_text += f"• {contact}\n"
            else:
                contact_text = "\n\nIf you believe this is an error, please contact the bot administrator."
        
        await update.message.reply_text(
            f"🚫 **Access Denied**\n\n"
            f"❌ You have been blocked from using this bot.{contact_text}",
            parse_mode='Markdown'
        )
        return
    
    # Track user
    if user_id:
        track_user(
            user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
    
    # Check if user has joined the required channel
    is_member = await check_channel_membership(update, context)
    
    if not is_member:
        join_message = (
            f"⚠️ **Channel Membership Required**\n\n"
            f"🔗 Please join our channel to use this bot:\n\n"
            f"📢 **Channel:** {REQUIRED_CHANNEL}\n"
            f"🔗 **Link:** {REQUIRED_CHANNEL_LINK}\n\n"
            f"**Steps:**\n"
            f"1. Click the link above to join the channel\n"
            f"2. Make sure you've joined the channel\n"
            f"3. Come back and use `/start` again\n\n"
            f"✅ After joining, you'll get access to all bot features!"
        )
        
        # Create inline keyboard with join button
        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            join_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    
    # Check for referral code
    referral_processed = False
    if context.args and len(context.args) > 0:
        ref_code = context.args[0].upper()
        user_name = user.first_name if user else "User"
        
        logger.info(f"Processing referral code: {ref_code} for user {user_id} ({user_name})")
        
        if user_id:
            referral_result = await add_referral(context, ref_code, user_id, user_name)
            if referral_result:
                referral_processed = True
                logger.info(f"Referral successfully processed for user {user_id} with code {ref_code}")
                await update.message.reply_text(
                    f"🎉 **Welcome!**\n\n"
                    f"✅ You joined using referral code: **{ref_code}**\n"
                    f"🙏 Thank you for using our bot!\n\n"
                    f"💡 Get your own referral code: `/refer`",
                    parse_mode='Markdown'
                )
                # Continue to show welcome message after referral confirmation
                await asyncio.sleep(0.5)
            else:
                logger.warning(f"Referral processing failed for user {user_id} with code {ref_code}")
        else:
            logger.warning(f"No user_id available for referral processing")
    
    pillow_status = "✅ Available" if PIL_AVAILABLE else "❌ Not Available"
    
    # Create custom keyboard with command buttons
    keyboard = [
        [KeyboardButton("🌐 Web Clone"), KeyboardButton("🎨 Generate")],
        [KeyboardButton("🏗️ Build"), KeyboardButton("🔐 Password")],
        [KeyboardButton("📱 QR Code"), KeyboardButton("📊 Calculator")],
        [KeyboardButton("📺 YouTube"), KeyboardButton("🎵 TikTok")],
        [KeyboardButton("📷 Instagram"), KeyboardButton("📘 Facebook")],
        [KeyboardButton("🖼️ Blur"), KeyboardButton("💧 Watermark")],
        [KeyboardButton("🎨 Filters"), KeyboardButton("🔄 Resize")],
        [KeyboardButton("🌐 Translate"), KeyboardButton("📱 Device Info")],
        [KeyboardButton("📄 OCR"), KeyboardButton("✨ Enhance")],
        [KeyboardButton("🔗 URL Shortener"), KeyboardButton("📸 Screenshot")],
        [KeyboardButton("🌐 IP Lookup"), KeyboardButton("💰 Crypto Price")],
        [KeyboardButton("📅 Calendar")],
        [KeyboardButton("🎤 Audio to Text")],
        [KeyboardButton("ℹ️ Help")],
        [KeyboardButton("🎂 Birthday"), KeyboardButton("🔍 Wikipedia")],
        [KeyboardButton("📝 Fancy Font"), KeyboardButton("🖼️ Text Image")],
        [KeyboardButton("📅 Leap Year"), KeyboardButton("🔄 Referral")],
        [KeyboardButton("⏰ Time"), KeyboardButton("📆 Date")],
        [KeyboardButton("⏰ Alarm"), KeyboardButton("📋 Repeat")],
        [KeyboardButton("🎭 Emoji")],
        [KeyboardButton("📄 PDF Tools"), KeyboardButton("🎵 MP3")],
        [KeyboardButton("🖼️ Image to PDF"), KeyboardButton("📄 PDF to Image")],
        [KeyboardButton("🔄 Background Blur"), KeyboardButton("📸 Image to JPG")],
        [KeyboardButton("🎨 Sticker"), KeyboardButton("🔀 Remove Duplicates")],
        [KeyboardButton("🔐 Hash Generator")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_text = (
        f'╔═══════════════════════════════════╗\n'
        f'║   🤖 {BOT_NAME}   ║\n'
        f'╚═══════════════════════════════════╝\n\n'
        
        '👋 **Welcome!** I\'m here to help you with various tasks.\n\n'
        
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        '📋 **Available Features:**\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        
        '🔢 **Advanced Math & Calculator**\n'
        '   └─ Send math expressions directly\n'
        '   └─ `/calc <expr>` - Advanced calculations\n'
        '   └─ `/solve <equation>` - Solve equations\n'
        '   └─ `/convert <value> <from> <to>` - Unit conversion\n'
        '   └─ `/percent <op> <values>` - Percentage calculations\n'
        '   └─ `/stats <numbers>` - Statistical analysis\n'
        '   └─ `/bin <num>` - Binary conversion\n'
        '   └─ Example: `25 + 17`, `sin(pi/2)`, `factorial(5)`\n\n'
        
        '⏰ **Time & Date**\n'
        '   └─ `/time` - Get current time\n'
        '   └─ `/date` - Get current date\n'
        '   └─ `/calendar` - Show calendar (current month)\n'
        '   └─ `/calendar <month> <year>` - Show specific month\n\n'
        
        '⏰ **Alarm System**\n'
        '   └─ `/alarm <time> [message]` - Set an alarm\n'
        '   └─ `/alarms` - List all your alarms\n'
        '   └─ `/deletealarm <id>` - Delete an alarm\n'
        '   └─ Example: `/alarm 14:30 Meeting reminder`\n\n'
        
        '🗓️ **Leap Year Checker**\n'
        '   └─ `/leapyear <year>` - Check if year is leap year\n'
        '   └─ Shows next/previous leap years\n'
        '   └─ Example: `/leapyear 2024`\n\n'
        
        '🎯 **Referral System**\n'
        '   └─ `/refer` - Get your referral code\n'
        '   └─ Share link to refer friends\n'
        '   └─ Track your referrals and stats\n\n'
        
        '🔍 **Wikipedia Search**\n'
        '   └─ `/wiki <topic>` - Search Wikipedia\n'
        '   └─ Supports multiple languages\n\n'
        
        '📱 **QR Code Generator**\n'
        '   └─ `/qr <text/URL>` - Create QR codes\n'
        '   └─ Perfect for sharing links\n\n'
        
        '🔄 **Text Repeater**\n'
        '   └─ `/repeat <number> <text>`\n'
        '   └─ Repeat text multiple times\n\n'
        '🔀 **Remove Duplicates**\n'
        '   └─ `/removeduplicates <text>` - Remove duplicate lines from text\n'
        '   └─ Preserves order and removes duplicates\n\n'
        '🔐 **Hash Generator**\n'
        '   └─ `/hash <type> <text>` - Generate MD5, SHA1, SHA256, SHA512 hashes\n'
        '   └─ Types: md5, sha1, sha256, sha512, all\n'
        '   └─ Example: `/hash md5 Hello World` or `/hash all MyPassword`\n\n'
        '🔗 **URL Shortener**\n'
        '   └─ `/shorturl <URL>` - Shorten long URLs\n'
        '   └─ Reply to message with URL or send directly\n'
        '   └─ Example: `/shorturl https://www.google.com`\n\n'
        '📸 **Website Screenshot**\n'
        '   └─ `/screenshot <URL>` - Take screenshot of website\n'
        '   └─ Reply to message with URL or send directly\n'
        '   └─ Example: `/screenshot https://www.google.com`\n\n'
        '🌐 **IP Lookup**\n'
        '   └─ `/iplookup <IP>` - Get IP address information\n'
        '   └─ Shows location, ISP, timezone, and more\n'
        '   └─ Example: `/iplookup 8.8.8.8`\n\n'
        '💰 **Crypto Price Checker**\n'
        '   └─ `/crypto <coin>` - Get cryptocurrency price\n'
        '   └─ `/crypto <coin> <currency>` - Price in specific currency\n'
        '   └─ Example: `/crypto bitcoin` or `/crypto btc inr`\n'
        '   └─ Shows price, 24h change, market cap, volume\n\n'
        '✨ **Image Enhancement**\n'
        '   └─ `/enhance` - Professional AI-style enhancement\n'
        '   └─ Remini-style quality boost\n\n'
        
        '🎨 **Image Editing**\n'
        '   └─ `/blur` - Blur entire image\n'
        '   └─ `/bgblur` - Blur background only\n'
        '   └─ `/watermark <text> [position]` - Add watermark\n'
        '   └─ `/filter <type>` - Apply filters (grayscale, sepia, vintage, bright, dark, contrast, saturate, invert, warm, cool, vibrant, faded, sharp)\n'
        '   └─ `/resize` - Resize images\n'
        '   └─ `/sticker` - Convert image to Telegram sticker\n\n'
        
        '🖼️ **AI Image Generation**\n'
        '   └─ `/generate <prompt>` or `/t2i <prompt>`\n'
        '   └─ Create images from text descriptions\n\n'
        
        '📝 **Text on Image**\n'
        '   └─ `/textonimage <text>`\n'
        '   └─ Create beautiful text images\n\n'
        
        '🌐 **Translation**\n'
        '   └─ `/translate <lang> <text>`\n'
        '   └─ Supports 100+ languages\n\n'
        
        '📸 **Image to Text (OCR)**\n'
        '   └─ `/ocr` - Extract text from images\n'
        '   └─ Reply to image with /ocr\n\n'
        '📄 **Image to PDF**\n'
        '   └─ `/imagetopdf` - Convert images to PDF\n'
        '   └─ Supports multiple images (multi-page PDF)\n\n'
        '🖼️ **PDF to Image**\n'
        '   └─ `/pdftoimage` - Convert PDF pages to images\n'
        '   └─ Extracts all pages as separate images\n\n'
        
        '🎙️ **Text to Speech**\n'
        '   └─ Send any text message\n'
        '   └─ Automatic voice conversion\n\n'
        
        '🎵 **TikTok Downloader**\n'
        '   └─ `/tiktok <URL>` or `/tt <URL>`\n'
        '   └─ Download videos in HD quality\n\n'
        
        '📺 **YouTube Downloader**\n'
        '   └─ `/yt <URL>` or `/youtube <URL>`\n'
        '   └─ Download videos & shorts\n\n'
        '📘 **Facebook Downloader**\n'
        '   └─ `/fb <URL>` or `/facebook <URL>`\n'
        '   └─ Download Facebook videos\n\n'
        '📷 **Instagram Downloader**\n'
        '   └─ `/ig <URL>` or `/instagram <URL>`\n'
        '   └─ Download Instagram videos & photos\n\n'
        
        '🌐 **Website Cloning**\n'
        '   └─ `/clone <URL>` - Clone/download website\n'
        '   └─ Downloads HTML, CSS, JS separately\n'
        '   └─ Sends 3 files: HTML, CSS, JS\n\n'
        
        '🏗️ **Build Website** (AI Generator)\n'
        '   └─ `/build <description>` - Create website from prompt\n'
        '   └─ AI generates ready-made HTML, CSS, JS\n'
        '   └─ Perfect for quick website creation\n\n'
        
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
        f'📦 **Status:** {pillow_status}\n'
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
        
        '💡 **Tip:** Type `/help` for detailed command list\n'
        '💬 **Need help?** Send `/help` anytime!'
    )
    
    # Check message length and split if needed (Telegram limit: 4096 characters)
    if len(welcome_text) > 4096:
        # Split into parts
        welcome_part1 = (
            f'╔═══════════════════════════════════╗\n'
            f'║   🤖 {BOT_NAME}   ║\n'
            f'╚═══════════════════════════════════╝\n\n'
            
            '👋 **Welcome!** I\'m here to help you with various tasks.\n\n'
            
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            '📋 **Main Features:**\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            
            '🔢 Calculator • ⏰ Time/Date/Alarm • 🗓️ Leap Year\n'
            '🎯 Referral • 🔍 Wikipedia • 📱 QR Code\n'
            '🔐 Password • 🔗 URL Shortener • 📸 Screenshot\n'
            '🌐 IP Lookup • 💰 Crypto Price\n\n'
            
            '✨ **Image Tools:** `/enhance`, `/blur`, `/filter`, `/resize`, `/sticker`\n'
            '🖼️ **AI Generation:** `/generate <prompt>`\n'
            '📸 **OCR:** `/ocr` - Extract text from images\n'
            '📄 **PDF:** `/imagetopdf`, `/pdftoimage`\n\n'
            
            '📥 **Video Downloaders:**\n'
            '• `/yt <URL>` - YouTube\n'
            '• `/tiktok <URL>` - TikTok\n'
            '• `/fb <URL>` - Facebook\n'
            '• `/ig <URL>` - Instagram\n\n'
            
            '🌐 **Website:** `/clone <URL>`, `/build <description>`\n'
            '🎙️ **Text to Speech** - Send any text\n'
            '🌐 **Translation** - `/translate <lang> <text>`\n\n'
            
            f'📦 **Status:** {pillow_status}\n\n'
            '💡 Type `/help` for detailed commands!'
        )
        await update.message.reply_text(welcome_part1, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback when user clicks 'I've Joined' button."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_id = user.id if user else None
    
    # Check if user has joined the channel
    is_member = await check_channel_membership(update, context)
    
    if is_member:
        # User has joined, show welcome message
        await query.edit_message_text(
            "✅ **Great! You've joined the channel!**\n\n"
            "🎉 Welcome to the bot! You now have access to all features.\n\n"
            "💡 Use `/help` to see all available commands.",
            parse_mode='Markdown'
        )
        
        # Wait a moment then show full welcome
        await asyncio.sleep(1)
        
        # Show full welcome message
        pillow_status = "✅ Available" if PIL_AVAILABLE else "❌ Not Available"
        
        # Create custom keyboard with command buttons
        keyboard = [
            [KeyboardButton("🌐 Web Clone"), KeyboardButton("🎨 Generate")],
            [KeyboardButton("🏗️ Build"), KeyboardButton("🔐 Password")],
            [KeyboardButton("📱 QR Code"), KeyboardButton("📊 Calculator")],
            [KeyboardButton("📺 YouTube"), KeyboardButton("🎵 TikTok")],
            [KeyboardButton("📷 Instagram"), KeyboardButton("📘 Facebook")],
            [KeyboardButton("🖼️ Blur"), KeyboardButton("💧 Watermark")],
        [KeyboardButton("🎨 Filters"), KeyboardButton("🔄 Resize")],
            [KeyboardButton("🌐 Translate"), KeyboardButton("📱 Device Info")],
            [KeyboardButton("📄 OCR"), KeyboardButton("✨ Enhance")],
            [KeyboardButton("🔗 URL Shortener"), KeyboardButton("📸 Screenshot")],
            [KeyboardButton("🌐 IP Lookup"), KeyboardButton("💰 Crypto Price")],
            [KeyboardButton("📅 Calendar")],
            [KeyboardButton("🎤 Audio to Text")],
            [KeyboardButton("ℹ️ Help")],
            [KeyboardButton("🎂 Birthday"), KeyboardButton("🔍 Wikipedia")],
            [KeyboardButton("📝 Fancy Font"), KeyboardButton("🖼️ Text Image")],
            [KeyboardButton("📅 Leap Year"), KeyboardButton("🔄 Referral")],
            [KeyboardButton("⏰ Time"), KeyboardButton("📆 Date")],
            [KeyboardButton("⏰ Alarm"), KeyboardButton("📋 Repeat")],
            [KeyboardButton("🎭 Emoji")],
            [KeyboardButton("📄 PDF Tools"), KeyboardButton("🎵 MP3")],
            [KeyboardButton("🖼️ Image to PDF"), KeyboardButton("📄 PDF to Image")],
            [KeyboardButton("🔄 Background Blur"), KeyboardButton("📸 Image to JPG")],
            [KeyboardButton("🎨 Sticker"), KeyboardButton("🔀 Remove Duplicates")],
            [KeyboardButton("🔐 Hash Generator")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        welcome_text = (
            f'╔═══════════════════════════════════╗\n'
            f'║   🤖 {BOT_NAME}   ║\n'
            f'╚═══════════════════════════════════╝\n\n'
            
            '👋 **Welcome!** I\'m here to help you with various tasks.\n\n'
            
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            '📋 **Available Features:**\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            
            '🔢 **Calculator**\n'
            '   └─ Send math expressions directly\n'
            '   └─ Example: `25 + 17` or `sqrt(16)`\n\n'
            
            '⏰ **Time & Date**\n'
            '   └─ `/time` - Get current time\n'
            '   └─ `/date` - Get current date\n'
            '   └─ `/calendar` - Show calendar (current month)\n'
            '   └─ `/calendar <month> <year>` - Show specific month\n\n'
            
            '⏰ **Alarm System**\n'
            '   └─ `/alarm <time> [message]` - Set an alarm\n'
            '   └─ `/alarms` - List all your alarms\n'
            '   └─ `/deletealarm <id>` - Delete an alarm\n'
            '   └─ Example: `/alarm 14:30 Meeting reminder`\n\n'
            
            '🗓️ **Leap Year Checker**\n'
            '   └─ `/leapyear <year>` - Check if year is leap year\n'
            '   └─ Shows next/previous leap years\n'
            '   └─ Example: `/leapyear 2024`\n\n'
            
            '🎯 **Referral System**\n'
            '   └─ `/refer` - Get your referral code\n'
            '   └─ Share link to refer friends\n'
            '   └─ Track your referrals and stats\n\n'
            
            '🔍 **Wikipedia Search**\n'
            '   └─ `/wiki <topic>` - Search Wikipedia\n'
            '   └─ Supports multiple languages\n\n'
            
            '📱 **QR Code Generator**\n'
            '   └─ `/qr <text/URL>` - Create QR codes\n'
            '   └─ Perfect for sharing links\n\n'
            
            '🔄 **Text Repeater**\n'
            '   └─ `/repeat <number> <text>`\n'
            '   └─ Repeat text multiple times\n\n'
            
            '✨ **Image Enhancement**\n'
            '   └─ `/enhance` - Professional AI-style enhancement\n'
            '   └─ Remini-style quality boost\n\n'
            
            '🎨 **Image Editing**\n'
            '   └─ `/blur` - Blur entire image\n'
            '   └─ `/bgblur` - Blur background only\n'
            '   └─ `/resize` - Resize images\n'
            '   └─ `/sticker` - Convert image to Telegram sticker\n\n'
            
            '🖼️ **AI Image Generation**\n'
            '   └─ `/generate <prompt>` or `/t2i <prompt>`\n'
            '   └─ Create images from text descriptions\n\n'
            
            '📝 **Text on Image**\n'
            '   └─ `/textonimage <text>`\n'
            '   └─ Create beautiful text images\n\n'
            
            '🌐 **Translation**\n'
            '   └─ `/translate <lang> <text>`\n'
            '   └─ Supports 100+ languages\n\n'
            
            '📸 **Image to Text (OCR)**\n'
            '   └─ `/ocr` - Extract text from images\n'
            '   └─ Reply to image with /ocr\n\n'
            
            '📄 **Image to PDF**\n'
            '   └─ `/imagetopdf` - Convert images to PDF\n'
            '   └─ Supports multiple images (multi-page PDF)\n\n'
            
            '🖼️ **PDF to Image**\n'
            '   └─ `/pdftoimage` - Convert PDF pages to images\n'
            '   └─ Extracts all pages as separate images\n\n'
            
            '🎙️ **Text to Speech**\n'
            '   └─ Send any text message\n'
            '   └─ Automatic voice conversion\n\n'
            
            '🎵 **TikTok Downloader**\n'
            '   └─ `/tiktok <URL>` or `/tt <URL>`\n'
            '   └─ Download videos in HD quality\n\n'
            
            '📺 **YouTube Downloader**\n'
            '   └─ `/yt <URL>` or `/youtube <URL>`\n'
            '   └─ Download videos & shorts\n\n'
            
            '📘 **Facebook Downloader**\n'
            '   └─ `/fb <URL>` or `/facebook <URL>`\n'
            '   └─ Download Facebook videos\n\n'
            
            '📷 **Instagram Downloader**\n'
            '   └─ `/ig <URL>` or `/instagram <URL>`\n'
            '   └─ Download Instagram videos & photos\n\n'
            
            '🌐 **Website Cloning**\n'
            '   └─ `/clone <URL>` - Clone/download website\n'
            '   └─ Downloads HTML, CSS, JS separately\n'
            '   └─ Sends 3 files: HTML, CSS, JS\n\n'
            
            '🏗️ **Build Website** (AI Generator)\n'
            '   └─ `/build <description>` - Create website from prompt\n'
            '   └─ AI generates ready-made HTML, CSS, JS\n'
            '   └─ Perfect for quick website creation\n\n'
            
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
            f'📦 **Status:** {pillow_status}\n'
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
            
            '💡 **Tip:** Type `/help` for detailed command list\n'
            '💬 **Need help?** Send `/help` anytime!'
        )
        # Check message length and split if needed (Telegram limit: 4096 characters)
        if len(welcome_text) > 4096:
            # Use shortened version
            welcome_part1 = (
                f'╔═══════════════════════════════════╗\n'
                f'║   🤖 {BOT_NAME}   ║\n'
                f'╚═══════════════════════════════════╝\n\n'
                
                '👋 **Welcome!** I\'m here to help you with various tasks.\n\n'
                
                '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n'
                '📋 **Main Features:**\n'
                '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n'
                
                '🔢 Calculator • ⏰ Time/Date/Alarm • 🗓️ Leap Year\n'
                '🎯 Referral • 🔍 Wikipedia • 📱 QR Code\n'
                '🔐 Password • 🔗 URL Shortener • 📸 Screenshot\n'
                '🌐 IP Lookup • 💰 Crypto Price\n\n'
                
                '✨ **Image Tools:** `/enhance`, `/blur`, `/filter`, `/resize`, `/sticker`\n'
                '🖼️ **AI Generation:** `/generate <prompt>`\n'
                '📸 **OCR:** `/ocr` - Extract text from images\n'
                '📄 **PDF:** `/imagetopdf`, `/pdftoimage`\n\n'
                
                '📥 **Video Downloaders:**\n'
                '• `/yt <URL>` - YouTube\n'
                '• `/tiktok <URL>` - TikTok\n'
                '• `/fb <URL>` - Facebook\n'
                '• `/ig <URL>` - Instagram\n\n'
                
                '🌐 **Website:** `/clone <URL>`, `/build <description>`\n'
                '🎙️ **Text to Speech** - Send any text\n'
                '🌐 **Translation** - `/translate <lang> <text>`\n\n'
                
                f'📦 **Status:** {pillow_status}\n\n'
                '💡 Type `/help` for detailed commands!'
            )
            await query.message.reply_text(welcome_part1, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await query.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        # User hasn't joined yet
        await query.answer(
            "❌ Please join the channel first! Click the 'Join Channel' button above.",
            show_alert=True
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Split help into multiple shorter messages to avoid Telegram's 4096 char limit
    help_part1 = (
        '🤖 *Bot Commands & Features*\n\n'
        '📊 *Basic Commands:*\n'
        '• /start - Start the bot\n'
        '• /time - Get current time\n'
        '• /date - Get current date\n'
        '• /calendar [month] [year] - Show calendar\n'
        '• /alarm <time> [message] - Set an alarm\n'
        '• /alarms - List all your alarms\n'
        '• /deletealarm <id> - Delete an alarm\n'
        '• /calc <expr> - Calculate math (advanced functions)\n'
        '• /solve <equation> - Solve linear/quadratic equations\n'
        '• /convert <value> <from> <to> - Unit conversion\n'
        '• /percent <op> <values> - Percentage calculations\n'
        '• /stats <numbers> - Statistical analysis\n'
        '• /bin <number> - Convert to binary\n'
        '• /hex <number> - Convert to hexadecimal\n'
        '• /oct <number> - Convert to octal\n'
        '• /birthday <day> <month> [year] - Birthday calculator\n'
        '• /leapyear <year> - Check if year is leap year\n\n'
        '📱 *Utilities:*\n'
        '• /wiki <topic> - Search Wikipedia\n'
        '• /qr <text> - Generate QR code\n'
        '• /password [length] - Generate secure password\n'
        '• /deviceinfo [user_agent] - Device/system info\n'
        '• /fancyfont <style> <text> - Fancy font generator\n'
        '• /texttoemoji <text> - Convert text to emojis\n'
        '• /repeat <n> <text> - Repeat text\n'
        '• /removeduplicates <text> - Remove duplicate lines\n'
        '• /hash <type> <text> - Generate MD5/SHA hashes (md5, sha1, sha256, sha512, all)\n'
        '• /shorturl <URL> - Shorten URLs\n'
        '• /screenshot <URL> - Take website screenshot\n'
        '• /iplookup <IP> - Get IP address information\n'
        '• /crypto <coin> [currency] - Get cryptocurrency price\n'
        '   └─ Example: /crypto bitcoin or /crypto btc inr\n'
        '• /audiototext - Convert voice/audio to text\n'
        '• /translate <lang> <text> - Translate\n\n'
        '🎨 *Image & Media:*\n'
        '• /generate <prompt> - AI image generation\n'
        '• /textonimage <text> - Text on image\n'
        '• /enhance - Enhance image quality\n'
        '• /blur - Blur image\n'
        '• /bgblur - Blur background only\n'
        '• /watermark <text> [position] - Add watermark to image\n'
        '• /filter <type> - Apply filters (grayscale, sepia, vintage, bright, dark, contrast, saturate, invert, warm, cool, vibrant, faded, sharp)\n'
        '• /resize <W>x<H> - Resize image\n'
        '• /tojpg - Convert image to JPG\n'
        '• /sticker - Convert image to Telegram sticker\n'
        '• /ocr - Extract text from image\n'
        '   └─ Tip: /ocr bn for Bangla (set OCR_SPACE_API_KEY or install Tesseract)\n'
        '• /imagetopdf - Convert image to PDF\n'
        '• /pdftoimage - Convert PDF to images\n'
        '• /mp4tomp3 - Convert MP4 video to MP3 audio\n\n'
    )
    
    help_part2 = (
        '📥 *Video Downloaders:*\n'
        '• /yt <URL> - Download YouTube video\n'
        '• /youtube <URL> - Same as /yt\n'
        '• /tiktok <URL> - Download TikTok video\n'
        '• /tt <URL> - Same as /tiktok\n'
        '• /fb <URL> - Download Facebook video\n'
        '• /facebook <URL> - Same as /fb\n'
        '• /ig <URL> - Download Instagram video/photo\n'
        '• /instagram <URL> - Same as /ig\n\n'
        '🌐 *Website Tools:*\n'
        '• /clone <URL> - Clone/download website\n'
        '• /website <URL> - Same as /clone\n'
        '• /build <description> - AI website generator\n'
        '• /buildwebsite <description> - Same as /build\n'
        '• Creates ready-made HTML, CSS, JS files\n\n'
        '🎯 *Referral System:*\n'
        '• /refer - Get your referral code\n'
        '• Share link to refer friends\n'
        '• Track your referrals and stats\n\n'
        '💡 *Smart Features:*\n'
        '• Send math → Auto calculate\n'
        '• Send text → Auto text-to-speech\n\n'
        '✨ *All features are free!*\n'
        '💬 Use /start for detailed info'
    )
    
    try:
        await update.message.reply_text(help_part1, parse_mode='Markdown')
        await asyncio.sleep(0.5)  # Small delay between messages
        await update.message.reply_text(help_part2, parse_mode='Markdown')
    except Exception as e:
        # If Markdown parsing fails, send without parse_mode
        logger.warning(f"Markdown parsing failed in help command: {e}")
        plain_part1 = help_part1.replace('*', '')
        plain_part2 = help_part2.replace('*', '')
        await update.message.reply_text(plain_part1)
        await asyncio.sleep(0.5)
        await update.message.reply_text(plain_part2)

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show calendar for current month or specified month/year."""
    from calendar import monthcalendar, month_name, month_abbr
    
    current_date = datetime.now()
    year = current_date.year
    month = current_date.month
    
    # Parse arguments if provided
    if context.args:
        try:
            if len(context.args) == 1:
                # Just month provided
                month = int(context.args[0])
                if month < 1 or month > 12:
                    raise ValueError("Month must be between 1 and 12")
            elif len(context.args) == 2:
                # Month and year provided
                month = int(context.args[0])
                year = int(context.args[1])
                if month < 1 or month > 12:
                    raise ValueError("Month must be between 1 and 12")
                if year < 1900 or year > 2100:
                    raise ValueError("Year must be between 1900 and 2100")
        except ValueError as e:
            await update.message.reply_text(
                f"❌ **Invalid input:** {str(e)}\n\n"
                "**Usage:**\n"
                "• `/calendar` - Current month\n"
                "• `/calendar <month>` - Specific month (1-12) of current year\n"
                "• `/calendar <month> <year>` - Specific month and year\n\n"
                "**Examples:**\n"
                "• `/calendar`\n"
                "• `/calendar 12` (December of current year)\n"
                "• `/calendar 12 2024` (December 2024)"
            )
            return
    
    # Get calendar data
    cal = monthcalendar(year, month)
    month_name_str = month_name[month]
    
    # Build clean and beautiful calendar display
    today = datetime.now()
    is_current_month = (year == today.year and month == today.month)
    
    # Header - clean and simple
    calendar_text = f"📅 **{month_name_str} {year}**\n"
    calendar_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Day headers - clean spacing
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    header_line = "  ".join([f"{day:^5}" for day in day_names])
    calendar_text += header_line + "\n"
    calendar_text += "─" * 40 + "\n"
    
    # Calendar weeks - clean formatting with proper alignment
    for week in cal:
        week_line = ""
        for day in week:
            if day == 0:
                # Empty cell - match width with other cells
                week_line += "     "
            else:
                # Highlight today with bold and proper spacing
                if is_current_month and day == today.day:
                    # Use bold markdown with proper spacing
                    day_str = f"**{day:>2}**"
                    week_line += f"{day_str:^7}"
                else:
                    # Regular date - match width
                    day_str = f"{day:>2}"
                    week_line += f"{day_str:^5}"
        calendar_text += week_line.rstrip() + "\n"
    
    calendar_text += "\n"
    calendar_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    
    # Footer info - clean and organized
    calendar_text += f"📆 **Today:** {today.strftime('%A, %B %d, %Y')}\n"
    calendar_text += f"🕐 **Time:** {today.strftime('%I:%M %p')}\n"
    
    if is_current_month:
        calendar_text += f"✨ Today's date is **bold** in the calendar above\n"
    else:
        calendar_text += f"📅 **Current Month:** {month_name[today.month]} {today.year}\n"
    
    calendar_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    await update.message.reply_text(calendar_text, parse_mode='Markdown')

async def time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send current time."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    now = datetime.now()
    current_time = now.strftime("%I:%M:%S %p")  # 12-hour format with AM/PM
    current_time_24 = now.strftime("%H:%M:%S")  # 24-hour format
    
    time_text = (
        f'🕐 **Current Time:**\n\n'
        f'12-hour format: {current_time}\n'
        f'24-hour format: {current_time_24}\n'
        f'Timezone: {now.strftime("%Z") or "UTC"}'
    )
    await update.message.reply_text(time_text, parse_mode='Markdown')

async def date_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send current date."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    now = datetime.now()
    date_text = (
        f'📅 **Current Date:**\n\n'
        f'Date: {now.strftime("%B %d, %Y")}\n'
        f'Day: {now.strftime("%A")}\n'
        f'Full: {now.strftime("%A, %B %d, %Y")}'
    )
    await update.message.reply_text(date_text, parse_mode='Markdown')

async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set an alarm for a specific time."""
    if await check_user_blocked(update, context):
        return
    
    user_id = update.message.from_user.id
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "⏰ **Alarm Setter**\n\n"
            "**Usage:**\n"
            "• `/alarm <time> [message]`\n\n"
            "**Time Formats:**\n"
            "• `HH:MM` - 24-hour format (e.g., `14:30`)\n"
            "• `HH:MM AM/PM` - 12-hour format (e.g., `2:30 PM`)\n\n"
            "**Examples:**\n"
            "• `/alarm 14:30 Meeting at 2:30 PM`\n"
            "• `/alarm 09:00 Wake up!`\n"
            "• `/alarm 11:30 PM Good night reminder`\n\n"
            "**Other Commands:**\n"
            "• `/alarms` - List your alarms\n"
            "• `/deletealarm <id>` - Delete an alarm",
            parse_mode='Markdown'
        )
        return
    
    time_input = context.args[0].upper()
    message = ' '.join(context.args[1:]) if len(context.args) > 1 else '⏰ Alarm!'
    
    # Parse time
    alarm_time = None
    try:
        # Try 24-hour format (HH:MM)
        if ':' in time_input and ('AM' not in time_input and 'PM' not in time_input):
            parts = time_input.split(':')
            if len(parts) == 2:
                hour = int(parts[0])
                minute = int(parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    alarm_time = f"{hour:02d}:{minute:02d}"
        # Try 12-hour format (HH:MM AM/PM)
        elif 'AM' in time_input or 'PM' in time_input:
            time_part = time_input.replace('AM', '').replace('PM', '').strip()
            if ':' in time_part:
                parts = time_part.split(':')
                if len(parts) == 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    if 'PM' in time_input and hour != 12:
                        hour += 12
                    elif 'AM' in time_input and hour == 12:
                        hour = 0
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        alarm_time = f"{hour:02d}:{minute:02d}"
    except (ValueError, IndexError):
        pass
    
    if not alarm_time:
        await update.message.reply_text(
            "❌ **Invalid time format!**\n\n"
            "**Valid formats:**\n"
            "• `14:30` (24-hour)\n"
            "• `2:30 PM` (12-hour)\n\n"
            "**Example:** `/alarm 14:30 Meeting reminder`",
            parse_mode='Markdown'
        )
        return
    
    # Generate unique alarm ID
    alarm_id = f"{user_id}_{datetime.now().timestamp()}"
    
    # Add alarm
    if user_id not in alarms:
        alarms[user_id] = []
    
    alarm_data = {
        'alarm_id': alarm_id,
        'time': alarm_time,
        'message': message,
        'created_at': datetime.now().isoformat()
    }
    alarms[user_id].append(alarm_data)
    save_alarms()
    
    # Format time for display
    hour, minute = map(int, alarm_time.split(':'))
    display_time_12 = datetime.strptime(alarm_time, "%H:%M").strftime("%I:%M %p")
    display_time_24 = alarm_time
    
    await update.message.reply_text(
        f"✅ **Alarm Set Successfully!**\n\n"
        f"⏰ **Time:** {display_time_24} ({display_time_12})\n"
        f"📝 **Message:** {message}\n"
        f"🆔 **Alarm ID:** `{alarm_id}`\n\n"
        f"💡 Use `/alarms` to see all your alarms\n"
        f"🗑️ Use `/deletealarm {alarm_id}` to delete",
        parse_mode='Markdown'
    )

async def alarms_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all alarms for the user."""
    if await check_user_blocked(update, context):
        return
    
    user_id = update.message.from_user.id
    
    if user_id not in alarms or not alarms[user_id]:
        await update.message.reply_text(
            "📭 **No Alarms Set**\n\n"
            "You don't have any alarms set.\n\n"
            "**Set an alarm:**\n"
            "`/alarm <time> [message]`\n\n"
            "**Example:**\n"
            "`/alarm 14:30 Meeting reminder`",
            parse_mode='Markdown'
        )
        return
    
    user_alarms = alarms[user_id]
    alarm_text = f"⏰ **Your Alarms ({len(user_alarms)})**\n\n"
    
    for idx, alarm in enumerate(user_alarms, 1):
        alarm_time = alarm.get('time', '')
        message = alarm.get('message', '⏰ Alarm!')
        alarm_id = alarm.get('alarm_id', '')
        created_at = alarm.get('created_at', '')
        
        # Format time
        try:
            hour, minute = map(int, alarm_time.split(':'))
            display_time_12 = datetime.strptime(alarm_time, "%H:%M").strftime("%I:%M %p")
            display_time_24 = alarm_time
        except:
            display_time_12 = alarm_time
            display_time_24 = alarm_time
        
        alarm_text += f"**{idx}.** ⏰ {display_time_24} ({display_time_12})\n"
        alarm_text += f"   📝 {message}\n"
        alarm_text += f"   🆔 `{alarm_id}`\n\n"
    
    alarm_text += "**Commands:**\n"
    alarm_text += "• `/deletealarm <id>` - Delete an alarm\n"
    alarm_text += "• `/alarm <time> [message]` - Set new alarm"
    
    await update.message.reply_text(alarm_text, parse_mode='Markdown')

async def deletealarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete an alarm by ID."""
    if await check_user_blocked(update, context):
        return
    
    user_id = update.message.from_user.id
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "🗑️ **Delete Alarm**\n\n"
            "**Usage:**\n"
            "• `/deletealarm <alarm_id>`\n\n"
            "**Get alarm ID:**\n"
            "• Use `/alarms` to see all your alarms with IDs\n\n"
            "**Example:**\n"
            "`/deletealarm 1234567890_1234567890.123456`",
            parse_mode='Markdown'
        )
        return
    
    alarm_id = context.args[0]
    
    if user_id not in alarms or not alarms[user_id]:
        await update.message.reply_text("❌ You don't have any alarms set.")
        return
    
    # Find and remove alarm
    original_count = len(alarms[user_id])
    alarms[user_id] = [a for a in alarms[user_id] if a.get('alarm_id') != alarm_id]
    
    if len(alarms[user_id]) < original_count:
        if not alarms[user_id]:
            del alarms[user_id]
        save_alarms()
        await update.message.reply_text(
            f"✅ **Alarm Deleted!**\n\n"
            f"Alarm ID: `{alarm_id}`\n\n"
            f"Use `/alarms` to see remaining alarms.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ **Alarm Not Found**\n\n"
            f"Alarm ID `{alarm_id}` not found.\n\n"
            f"Use `/alarms` to see your alarms.",
            parse_mode='Markdown'
        )

async def test_pillow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test Pillow installation status."""
    import sys
    status_text = (
        f'🔍 **Pillow Diagnostic:**\n\n'
        f'PIL_AVAILABLE: `{PIL_AVAILABLE}`\n'
        f'IMAGEDRAW_AVAILABLE: `{IMAGEDRAW_AVAILABLE}`\n'
        f'IMAGEFONT_AVAILABLE: `{IMAGEFONT_AVAILABLE}`\n\n'
        f'Python: `{sys.executable}`\n'
        f'Python Version: `{sys.version}`\n'
    )
    
    if PIL_AVAILABLE:
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (10, 10))
            draw = ImageDraw.Draw(img)
            status_text += '\n✅ **Pillow is working correctly!**\n'
            status_text += 'You can use /textonimage command.'
        except Exception as e:
            status_text += f'\n❌ **Error testing Pillow:** `{str(e)}`'
    else:
        status_text += '\n❌ **Pillow is not available!**\n'
        status_text += 'Install: `pip install Pillow`'
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def birthday_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate birthday information - days until birthday, age, etc."""
    if not context.args:
        help_text = (
            "🎂 **Happy Birthday Calculator**\n\n"
            "**Usage:** `/birthday <day> <month> [year]`\n\n"
            "**Examples:**\n"
            "• `/birthday 15 12` - Birthday on December 15 (current year)\n"
            "• `/birthday 15 12 2000` - Birthday on December 15, 2000 (with age)\n"
            "• `/birthday 25 3` - Birthday on March 25\n\n"
            "**Features:**\n"
            "• Days until next birthday\n"
            "• Current age (if year provided)\n"
            "• Days since last birthday\n"
            "• Birthday countdown\n"
            "• Next birthday date"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    try:
        args = context.args
        if len(args) < 2:
            raise ValueError("Please provide at least day and month")
        
        day = int(args[0])
        month = int(args[1])
        year = None
        if len(args) >= 3:
            year = int(args[2])
        
        # Validate inputs
        if month < 1 or month > 12:
            raise ValueError("Month must be between 1 and 12")
        if day < 1 or day > 31:
            raise ValueError("Day must be between 1 and 31")
        if year and (year < 1900 or year > datetime.now().year):
            raise ValueError(f"Year must be between 1900 and {datetime.now().year}")
        
        today = datetime.now()
        current_year = today.year
        
        # Check if date is valid (handle leap year for Feb 29)
        try:
            test_date = datetime(current_year, month, day)
        except ValueError:
            # Check if it's Feb 29 in a non-leap year
            if month == 2 and day == 29:
                # Check if current year is leap year
                is_leap = (current_year % 4 == 0 and (current_year % 100 != 0 or current_year % 400 == 0))
                if not is_leap:
                    raise ValueError(f"February 29 does not exist in {current_year} (not a leap year). Please use February 28 or March 1.")
                else:
                    test_date = datetime(current_year, month, day)
            else:
                raise ValueError(f"Invalid date: {day}/{month} is not a valid date")
        
        # Calculate next birthday
        next_birthday = datetime(current_year, month, day)
        if next_birthday < today:
            # Birthday already passed this year, next is next year
            next_birthday = datetime(current_year + 1, month, day)
        
        days_until = (next_birthday - today).days
        
        # Calculate age if year provided
        age_info = ""
        if year:
            birthday_this_year = datetime(current_year, month, day)
            if birthday_this_year <= today:
                age = current_year - year
            else:
                age = current_year - year - 1
            
            # Calculate days since last birthday
            if birthday_this_year <= today:
                last_birthday = birthday_this_year
            else:
                last_birthday = datetime(current_year - 1, month, day)
            
            days_since = (today - last_birthday).days
            
            age_info = (
                f"🎂 **Age:** {age} years old\n"
                f"📅 **Days since last birthday:** {days_since} days\n"
            )
        
        # Build response
        from calendar import month_name
        birthday_text = f"🎂 **Birthday Calculator**\n"
        birthday_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        birthday_text += f"📅 **Birthday:** {day} {month_name[month]}\n"
        if year:
            birthday_text += f"📆 **Birth Year:** {year}\n"
        birthday_text += "\n"
        birthday_text += age_info
        birthday_text += f"⏳ **Days until next birthday:** {days_until} days\n"
        birthday_text += f"📆 **Next birthday:** {next_birthday.strftime('%A, %B %d, %Y')}\n"
        
        # Add countdown message
        if days_until == 0:
            birthday_text += "\n🎉 **🎂 HAPPY BIRTHDAY TODAY! 🎂** 🎉\n"
            birthday_text += "✨ Wishing you a wonderful day! ✨"
        elif days_until == 1:
            birthday_text += "\n🎊 **Birthday is tomorrow!** 🎊\n"
            birthday_text += "Get ready to celebrate! 🎉"
        elif days_until <= 7:
            birthday_text += f"\n⏰ **Only {days_until} days left!** ⏰\n"
            birthday_text += "The countdown is on! 🎈"
        else:
            weeks = days_until // 7
            remaining_days = days_until % 7
            if weeks > 0:
                birthday_text += f"\n📆 **That's {weeks} week"
                if weeks > 1:
                    birthday_text += "s"
                if remaining_days > 0:
                    birthday_text += f" and {remaining_days} day"
                    if remaining_days > 1:
                        birthday_text += "s"
                birthday_text += " away!** 📆"
        
        birthday_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await update.message.reply_text(birthday_text, parse_mode='Markdown')
        
    except ValueError as e:
        await update.message.reply_text(
            f"❌ **Invalid input:** {str(e)}\n\n"
            "**Usage:** `/birthday <day> <month> [year]`\n\n"
            "**Examples:**\n"
            "• `/birthday 15 12` - December 15\n"
            "• `/birthday 15 12 2000` - December 15, 2000"
        )
    except Exception as e:
        logger.error(f"Birthday calculation error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ **Error:** {str(e)}\n\n"
            "Please check your input and try again."
        )

async def leapyear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if a year is a leap year and show leap year information."""
    if not context.args:
        help_text = (
            "🗓️ **Leap Year Checker**\n\n"
            "**Usage:** `/leapyear <year>`\n\n"
            "**Examples:**\n"
            "• `/leapyear 2024` - Check if 2024 is a leap year\n"
            "• `/leapyear 2000` - Check if 2000 is a leap year\n"
            "• `/leapyear 2025` - Check if 2025 is a leap year\n\n"
            "**Features:**\n"
            "• Check if a year is a leap year\n"
            "• Show next and previous leap years\n"
            "• Explain leap year rules\n"
            "• Days in February for that year"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    try:
        year = int(context.args[0])
        
        if year < 1 or year > 10000:
            await update.message.reply_text(
                "❌ **Invalid year!**\n\n"
                "Please provide a year between 1 and 10000."
            )
            return
        
        # Check if leap year
        def is_leap_year(y):
            """Check if a year is a leap year."""
            if y % 4 != 0:
                return False
            elif y % 100 != 0:
                return True
            elif y % 400 != 0:
                return False
            else:
                return True
        
        is_leap = is_leap_year(year)
        
        # Build response
        leap_text = f"🗓️ **Leap Year Checker**\n"
        leap_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        if is_leap:
            leap_text += f"✅ **{year} IS a leap year!** 🎉\n\n"
            leap_text += f"📅 **February has 29 days** in {year}\n"
            leap_text += f"📆 **Total days in {year}:** 366 days\n"
        else:
            leap_text += f"❌ **{year} is NOT a leap year**\n\n"
            leap_text += f"📅 **February has 28 days** in {year}\n"
            leap_text += f"📆 **Total days in {year}:** 365 days\n"
        
        leap_text += "\n"
        leap_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        leap_text += "📚 **Leap Year Rules:**\n\n"
        leap_text += "A year is a leap year if:\n"
        leap_text += "1. It is divisible by 4, AND\n"
        leap_text += "2. It is NOT divisible by 100, OR\n"
        leap_text += "3. It IS divisible by 400\n\n"
        leap_text += "**Examples:**\n"
        leap_text += "• 2024 → ✅ (divisible by 4, not by 100)\n"
        leap_text += "• 2000 → ✅ (divisible by 400)\n"
        leap_text += "• 1900 → ❌ (divisible by 100, not by 400)\n"
        leap_text += "• 2025 → ❌ (not divisible by 4)\n"
        
        # Check this year
        check_year = year
        if check_year % 4 == 0:
            if check_year % 100 == 0:
                if check_year % 400 == 0:
                    leap_text += f"\n**{year} analysis:** Divisible by 400 → ✅ Leap year"
                else:
                    leap_text += f"\n**{year} analysis:** Divisible by 100 but not 400 → ❌ Not leap year"
            else:
                leap_text += f"\n**{year} analysis:** Divisible by 4 but not 100 → ✅ Leap year"
        else:
            leap_text += f"\n**{year} analysis:** Not divisible by 4 → ❌ Not leap year"
        
        # Find next and previous leap years
        next_leap = year + 1
        while not is_leap_year(next_leap):
            next_leap += 1
        
        prev_leap = year - 1
        while not is_leap_year(prev_leap):
            prev_leap -= 1
            if prev_leap < 1:
                prev_leap = None
                break
        
        leap_text += "\n\n"
        leap_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        leap_text += "📅 **Nearby Leap Years:**\n\n"
        leap_text += f"➡️ **Next leap year:** {next_leap} ({next_leap - year} years from {year})\n"
        if prev_leap:
            leap_text += f"⬅️ **Previous leap year:** {prev_leap} ({year - prev_leap} years before {year})\n"
        else:
            leap_text += f"⬅️ **Previous leap year:** None (before year 1)\n"
        
        # Special message for February 29
        if is_leap:
            leap_text += "\n"
            leap_text += "🎂 **Birthday Note:**\n"
            leap_text += f"People born on February 29, {year} can celebrate on:\n"
            leap_text += f"• February 28 in non-leap years\n"
            leap_text += f"• February 29 in leap years\n"
            leap_text += f"• March 1 in some countries\n"
        
        leap_text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await update.message.reply_text(leap_text, parse_mode='Markdown')
        
    except ValueError:
        await update.message.reply_text(
            "❌ **Invalid input!**\n\n"
            "Please provide a valid year number.\n\n"
            "**Usage:** `/leapyear <year>`\n"
            "**Example:** `/leapyear 2024`"
        )
    except Exception as e:
        logger.error(f"Leap year check error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ **Error:** {str(e)}\n\n"
            "Please check your input and try again."
        )

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral code and statistics."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ Could not get user information.")
        return
    
    user_id = user.id
    user_name = user.first_name or f"User{user_id}"
    
    # Generate or get referral code
    ref_code = generate_referral_code(user_id, user_name)
    
    # Get referral stats - ensure user exists in referral_data
    if str(user_id) not in referral_data:
        # Should not happen as generate_referral_code creates entry, but just in case
        referral_data[str(user_id)] = {
            'code': ref_code,
            'referrals': [],
            'total_referrals': 0,
            'joined_at': datetime.now().isoformat(),
            'name': user_name
        }
        save_referral_data()
    
    user_data = referral_data.get(str(user_id), {})
    
    # Ensure referrals list exists
    if 'referrals' not in user_data:
        referral_data[str(user_id)]['referrals'] = []
        user_data = referral_data[str(user_id)]
    
    referrals = user_data.get('referrals', [])
    
    # Calculate total referrals from actual list length (real-time) - always use actual count
    total_refs = len(referrals)
    
    # Always update total_referrals to match actual list length (fix any inconsistencies)
    if user_data.get('total_referrals', 0) != total_refs:
        referral_data[str(user_id)]['total_referrals'] = total_refs
        save_referral_data()
        logger.info(f"Fixed referral count for user {user_id}: was {user_data.get('total_referrals', 0)}, now {total_refs}")
    
    # Double-check: use actual count from list
    actual_count = len(referral_data[str(user_id)].get('referrals', []))
    total_refs = actual_count
    
    # Build response
    refer_text = "🎯 **Referral System**\n"
    refer_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    refer_text += f"📋 **Your Referral Code:**\n"
    refer_text += f"`{ref_code}`\n\n"
    
    refer_text += f"🔗 **Share this link:**\n"
    bot_username = context.bot.username if context.bot.username else "your_bot"
    refer_link = f"https://t.me/{bot_username}?start={ref_code}"
    refer_text += f"`{refer_link}`\n\n"
    
    refer_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    refer_text += "📊 **Your Statistics:**\n\n"
    refer_text += f"👥 **Total Referrals:** {total_refs}\n"
    
    if total_refs > 0:
        refer_text += f"✅ **Active Referrals:** {actual_count}\n"
        refer_text += f"📝 **Referral List:** {actual_count} users\n"
    
    refer_text += "\n"
    refer_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    refer_text += "💡 **How to Refer:**\n\n"
    refer_text += "1. Share your referral link with friends\n"
    refer_text += "2. When they click and start the bot\n"
    refer_text += "3. They'll be counted as your referral\n"
    refer_text += "4. Track your referrals here!\n\n"
    refer_text += "✨ **Keep sharing to grow your referrals!** ✨"
    
    await update.message.reply_text(refer_text, parse_mode='Markdown')

# ==================== ADMIN PANEL COMMANDS ====================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel main command."""
    if not await admin_only(update, context):
        return
    
    # Track admin command usage
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    # Get statistics
    total_users = len(user_data)
    total_referrals = len(referral_data)
    total_referral_count = sum(data.get('total_referrals', 0) for data in referral_data.values())
    
    # Calculate active users (last 7 days)
    active_users = 0
    seven_days_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
    for user_id, data in user_data.items():
        last_seen = data.get('last_seen', '')
        if last_seen:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen)
                if last_seen_dt.timestamp() > seven_days_ago:
                    active_users += 1
            except:
                pass
    
    # Total commands executed
    total_commands = sum(data.get('command_count', 0) for data in user_data.values())
    
    # Count blocked users
    blocked_count = len(blocked_users) if blocked_users else 0
    
    admin_text = (
        "🔐 **Admin Panel**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "📊 **Bot Statistics:**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"🟢 **Active Users (7 days):** {active_users}\n"
        f"📈 **Total Commands:** {total_commands}\n"
        f"🎯 **Referral Users:** {total_referrals}\n"
        f"🔗 **Total Referrals:** {total_referral_count}\n"
        f"🚫 **Blocked Users:** {blocked_count}\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 **Admin Commands:**\n\n"
        "📊 **Statistics & Users:**\n"
        "`/admin_stats` - Detailed statistics\n"
        "`/admin_users` - View all users\n"
        "`/admin_referrals` - Referral statistics\n\n"
        
        "👥 **User Management:**\n"
        "`/admin_block <user_id>` - Block a user\n"
        "`/admin_unblock <user_id>` - Unblock a user\n"
        "`/admin_blocked` - List blocked users\n"
        "`/admin_delete_user <user_id>` - Delete user data\n\n"
        
        "👨‍💼 **Admin Management:**\n"
        "`/admin_add <user_id>` - Add admin\n"
        "`/admin_remove <user_id>` - Remove admin\n"
        "`/admin_list` - List all admins\n\n"
        
        "📢 **Communication:**\n"
        "`/admin_broadcast <message>` - Broadcast to all users\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 **Quick Actions:**\n"
        "• Reply to a user message with `/admin_block` to block them\n"
        "• Use `/admin_users` to see all users with their IDs\n"
        "• Use `/admin_blocked` to see all blocked users\n\n"
        "⚠️ **Note:** Blocked users cannot use the bot. Use `/admin_unblock` to restore access."
    )
    
    # Create inline keyboard for quick actions
    keyboard = [
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("🚫 Blocked", callback_data="admin_blocked")
        ],
        [
            InlineKeyboardButton("👨‍💼 Admins", callback_data="admin_list"),
            InlineKeyboardButton("🎯 Referrals", callback_data="admin_referrals")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(admin_text, parse_mode='Markdown', reply_markup=reply_markup)

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed statistics for admin."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    # Basic stats
    total_users = len(user_data)
    total_referrals = len(referral_data)
    total_referral_count = sum(data.get('total_referrals', 0) for data in referral_data.values())
    total_commands = sum(data.get('command_count', 0) for data in user_data.values())
    
    # Active users (last 7, 30 days)
    active_7d = 0
    active_30d = 0
    seven_days_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
    thirty_days_ago = datetime.now().timestamp() - (30 * 24 * 60 * 60)
    
    for user_id, data in user_data.items():
        last_seen = data.get('last_seen', '')
        if last_seen:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen)
                ts = last_seen_dt.timestamp()
                if ts > seven_days_ago:
                    active_7d += 1
                if ts > thirty_days_ago:
                    active_30d += 1
            except:
                pass
    
    # Top users by commands
    top_users = sorted(
        [(uid, data.get('command_count', 0)) for uid, data in user_data.items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    stats_text = (
        "📊 **Detailed Statistics**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "👥 **User Statistics:**\n"
        f"• Total Users: **{total_users}**\n"
        f"• Active (7 days): **{active_7d}**\n"
        f"• Active (30 days): **{active_30d}**\n\n"
        
        "📈 **Activity Statistics:**\n"
        f"• Total Commands: **{total_commands}**\n"
        f"• Avg Commands/User: **{total_commands / total_users if total_users > 0 else 0:.1f}**\n\n"
        
        "🎯 **Referral Statistics:**\n"
        f"• Users with Referrals: **{total_referrals}**\n"
        f"• Total Referrals: **{total_referral_count}**\n"
        f"• Avg Referrals/User: **{total_referral_count / total_referrals if total_referrals > 0 else 0:.1f}**\n\n"
    )
    
    if top_users:
        stats_text += "🏆 **Top 5 Most Active Users:**\n"
        for i, (uid, count) in enumerate(top_users, 1):
            user_info = user_data.get(uid, {})
            username = user_info.get('username', 'N/A')
            name = user_info.get('first_name', 'Unknown')
            # Escape special characters
            escaped_name = escape_markdown(str(name))
            escaped_username = escape_markdown(str(username))
            stats_text += f"{i}. {escaped_name} (@{escaped_username}) - {count} commands\n"
        stats_text += "\n"
    
    stats_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def admin_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all users for admin."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not user_data:
        await update.message.reply_text("📭 No users found.")
        return
    
    # Get page number from args (default: 1)
    page = 1
    if context.args:
        try:
            page = int(context.args[0])
        except:
            pass
    
    users_per_page = 10
    total_pages = (len(user_data) + users_per_page - 1) // users_per_page
    
    if page < 1 or page > total_pages:
        page = 1
    
    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    
    users_list = list(user_data.items())[start_idx:end_idx]
    
    users_text = (
        f"👥 **All Users** (Page {page}/{total_pages})\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for uid, data in users_list:
        username = data.get('username', 'N/A')
        name = data.get('first_name', 'Unknown')
        commands = data.get('command_count', 0)
        last_seen = data.get('last_seen', 'N/A')
        
        # Escape special characters to avoid Markdown parsing errors
        escaped_name = escape_markdown(str(name))
        escaped_username = escape_markdown(str(username))
        escaped_last_seen = escape_markdown(last_seen[:10] if len(last_seen) > 10 else str(last_seen))
        
        users_text += (
            f"👤 **{escaped_name}**\n"
            f"   ID: `{uid}`\n"
            f"   Username: @{escaped_username}\n"
            f"   Commands: {commands}\n"
            f"   Last Seen: {escaped_last_seen}\n\n"
        )
    
    users_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    users_text += f"💡 Use `/admin_users <page>` to see more pages"
    
    await update.message.reply_text(users_text, parse_mode='Markdown')

async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not context.args:
        await update.message.reply_text(
            "📢 **Broadcast Message**\n\n"
            "**Usage:** `/admin_broadcast <your message>`\n\n"
            "**Example:**\n"
            "`/admin_broadcast Hello everyone! This is an important update.`",
            parse_mode='Markdown'
        )
        return
    
    message = ' '.join(context.args)
    
    if not user_data:
        await update.message.reply_text("❌ No users to broadcast to.")
        return
    
    # Send confirmation
    await update.message.reply_text(
        f"📢 **Broadcasting...**\n\n"
        f"Message: {message}\n\n"
        f"Recipients: {len(user_data)} users\n\n"
        f"⏳ This may take a while..."
    )
    
    # Broadcast to all users
    success_count = 0
    failed_count = 0
    
    for user_id_str in user_data.keys():
        try:
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=f"📢 **Broadcast Message**\n\n{message}",
                parse_mode='Markdown'
            )
            success_count += 1
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.05)
        except Exception as e:
            failed_count += 1
            logger.warning(f"Failed to send broadcast to {user_id_str}: {e}")
    
    # Send summary
    await update.message.reply_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"✅ Success: {success_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"📊 Total: {len(user_data)}"
    )

async def admin_referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View referral statistics for admin."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not referral_data:
        await update.message.reply_text("📭 No referral data found.")
        return
    
    # Calculate real-time referral counts and fix inconsistencies
    referral_counts = []
    for uid, data in referral_data.items():
        # Ensure referrals list exists
        if 'referrals' not in data:
            referral_data[uid]['referrals'] = []
            data = referral_data[uid]
        
        referrals_list = data.get('referrals', [])
        actual_count = len(referrals_list)
        
        # Always fix if total_referrals doesn't match actual list
        if data.get('total_referrals', 0) != actual_count:
            referral_data[uid]['total_referrals'] = actual_count
            save_referral_data()
            logger.info(f"Fixed referral count for user {uid} in admin view: was {data.get('total_referrals', 0)}, now {actual_count}")
        
        referral_counts.append((uid, actual_count))
    
    # Get top referrers based on real counts
    top_referrers = sorted(
        referral_counts,
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    total_refs = sum(count for _, count in referral_counts)
    
    referrals_text = (
        "🎯 **Referral Statistics**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 **Total Referrals:** {total_refs}\n"
        f"👥 **Users with Referrals:** {len(referral_data)}\n\n"
    )
    
    if top_referrers:
        referrals_text += "🏆 **Top 10 Referrers:**\n\n"
        for i, (uid, count) in enumerate(top_referrers, 1):
            ref_data = referral_data.get(uid, {})
            name = ref_data.get('name', 'Unknown')
            code = ref_data.get('code', 'N/A')
            referrals_text += f"{i}. **{name}**\n"
            referrals_text += f"   Code: `{code}`\n"
            referrals_text += f"   Referrals: {count}\n\n"
    
    referrals_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    await update.message.reply_text(referrals_text, parse_mode='Markdown')

async def admin_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a new admin."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not context.args:
        await update.message.reply_text(
            "➕ **Add Admin**\n\n"
            "**Usage:** `/admin_add <user_id>`\n\n"
            "**Example:**\n"
            "`/admin_add 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        new_admin_id = int(context.args[0])
        if new_admin_id in ADMIN_IDS:
            await update.message.reply_text(f"ℹ️ User {new_admin_id} is already an admin.")
        else:
            ADMIN_IDS.append(new_admin_id)
            await update.message.reply_text(
                f"✅ **Admin Added Successfully!**\n\n"
                f"👤 User ID: `{new_admin_id}`\n"
                f"🔐 They now have access to admin commands.",
                parse_mode='Markdown'
            )
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")

async def admin_remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an admin."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not context.args:
        await update.message.reply_text(
            "➖ **Remove Admin**\n\n"
            "**Usage:** `/admin_remove <user_id>`\n\n"
            "**Example:**\n"
            "`/admin_remove 123456789`",
            parse_mode='Markdown'
        )
        return
    
    try:
        admin_id = int(context.args[0])
        if admin_id in ADMIN_IDS:
            ADMIN_IDS.remove(admin_id)
            await update.message.reply_text(
                f"✅ **Admin Removed Successfully!**\n\n"
                f"👤 User ID: `{admin_id}`\n"
                f"🔐 They no longer have admin access.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"ℹ️ User {admin_id} is not an admin.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")

async def admin_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not ADMIN_IDS:
        await update.message.reply_text("📭 No admins configured.")
        return
    
    admins_text = (
        "👥 **Admin List**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for i, admin_id in enumerate(ADMIN_IDS, 1):
        # Try to get user info from user_data
        admin_info = user_data.get(str(admin_id), {})
        name = admin_info.get('first_name', 'Unknown')
        username = admin_info.get('username', 'N/A')
        
        # Escape special characters
        escaped_name = escape_markdown(str(name))
        escaped_username = escape_markdown(str(username))
        
        admins_text += f"{i}. **{escaped_name}** (@{escaped_username})\n"
        admins_text += f"   ID: `{admin_id}`\n\n"
    
    admins_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    await update.message.reply_text(admins_text, parse_mode='Markdown')

async def admin_block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Block a user from using the bot."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    # Check if replying to a message
    target_user_id = None
    if update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user
        if replied_user:
            target_user_id = replied_user.id
    
    # If not replying, check args
    if not target_user_id:
        if not context.args:
            await update.message.reply_text(
                "🚫 **Block User**\n\n"
                "**Usage:** `/admin_block <user_id>`\n\n"
                "**Methods:**\n"
                "1. Reply to a user's message: `/admin_block`\n"
                "2. Use user ID: `/admin_block 123456789`\n\n"
                "**Example:**\n"
                "`/admin_block 123456789`\n\n"
                "⚠️ **Note:** Blocked users will not be able to use the bot.",
                parse_mode='Markdown'
            )
            return
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID or reply to a user's message.")
            return
    
    try:
        target_user_id_str = str(target_user_id)
        
        # Check if user is already blocked
        if is_user_blocked(target_user_id):
            await update.message.reply_text(
                f"ℹ️ User `{target_user_id}` is already blocked.",
                parse_mode='Markdown'
            )
            return
        
        # Check if trying to block an admin
        if target_user_id in ADMIN_IDS:
            await update.message.reply_text(
                "❌ **Cannot Block Admin**\n\n"
                "⚠️ You cannot block an administrator. Remove admin access first using `/admin_remove`.",
                parse_mode='Markdown'
            )
            return
        
        # Block the user
        block_user(target_user_id)
        
        # Get user info if available
        user_info = user_data.get(target_user_id_str, {})
        username = user_info.get('username', 'N/A')
        name = user_info.get('first_name', 'Unknown')
        
        await update.message.reply_text(
            f"✅ **User Blocked Successfully!**\n\n"
            f"👤 **User:** {escape_markdown(name)} (@{escape_markdown(username)})\n"
            f"🆔 **ID:** `{target_user_id}`\n\n"
            f"🚫 This user can no longer use the bot.",
            parse_mode='Markdown'
        )
        
        # Try to notify the blocked user
        try:
            admin_contacts = await get_admin_contacts_async(context)
            contact_text = ""
            if admin_contacts:
                contact_text = "\n\n**Contact Admin:**\n"
                for contact in admin_contacts:
                    contact_text += f"• {contact}\n"
            else:
                contact_text = "\n\nIf you believe this is an error, please contact the bot administrator."
            
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🚫 **You have been blocked**\n\n"
                    f"❌ You have been blocked from using this bot.{contact_text}"
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not notify blocked user {target_user_id}: {e}")
            
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")

async def admin_unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblock a user."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    # Check if replying to a message
    target_user_id = None
    if update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user
        if replied_user:
            target_user_id = replied_user.id
    
    # If not replying, check args
    if not target_user_id:
        if not context.args:
            await update.message.reply_text(
                "✅ **Unblock User**\n\n"
                "**Usage:** `/admin_unblock <user_id>`\n\n"
                "**Methods:**\n"
                "1. Reply to a user's message: `/admin_unblock`\n"
                "2. Use user ID: `/admin_unblock 123456789`\n\n"
                "**Example:**\n"
                "`/admin_unblock 123456789`",
                parse_mode='Markdown'
            )
            return
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID or reply to a user's message.")
            return
    
    try:
        target_user_id_str = str(target_user_id)
        
        # Check if user is blocked
        if not is_user_blocked(target_user_id):
            await update.message.reply_text(
                f"ℹ️ User `{target_user_id}` is not blocked.",
                parse_mode='Markdown'
            )
            return
        
        # Unblock the user
        unblock_user(target_user_id)
        
        # Get user info if available
        user_info = user_data.get(target_user_id_str, {})
        username = user_info.get('username', 'N/A')
        name = user_info.get('first_name', 'Unknown')
        
        await update.message.reply_text(
            f"✅ **User Unblocked Successfully!**\n\n"
            f"👤 **User:** {escape_markdown(name)} (@{escape_markdown(username)})\n"
            f"🆔 **ID:** `{target_user_id}`\n\n"
            f"✅ This user can now use the bot again.",
            parse_mode='Markdown'
        )
        
        # Try to notify the unblocked user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "✅ **You have been unblocked**\n\n"
                    "🎉 You can now use the bot again!\n\n"
                    "Use `/start` to begin."
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not notify unblocked user {target_user_id}: {e}")
            
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")

async def admin_blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all blocked users."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    if not blocked_users:
        await update.message.reply_text("📭 No users are currently blocked.")
        return
    
    blocked_text = (
        "🚫 **Blocked Users**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 **Total Blocked:** {len(blocked_users)}\n\n"
    )
    
    # Get user info for blocked users
    blocked_list = []
    for user_id_str in blocked_users:
        try:
            user_id = int(user_id_str)
            user_info = user_data.get(user_id_str, {})
            username = user_info.get('username', 'N/A')
            name = user_info.get('first_name', 'Unknown')
            blocked_list.append((user_id, name, username))
        except:
            blocked_list.append((user_id_str, 'Unknown', 'N/A'))
    
    # Sort by user ID
    blocked_list.sort(key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
    
    for i, (user_id, name, username) in enumerate(blocked_list, 1):
        escaped_name = escape_markdown(str(name))
        escaped_username = escape_markdown(str(username))
        blocked_text += f"{i}. **{escaped_name}** (@{escaped_username})\n"
        blocked_text += f"   ID: `{user_id}`\n\n"
    
    blocked_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    blocked_text += f"💡 Use `/admin_unblock <user_id>` to unblock a user"
    
    await update.message.reply_text(blocked_text, parse_mode='Markdown')

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel inline keyboard button clicks."""
    query = update.callback_query
    await query.answer()
    
    if not await admin_only(update, context):
        return
    
    callback_data = query.data
    message = query.message
    
    # Create a mock update object for command functions
    # Since callback queries don't have update.message, we need to handle it differently
    if callback_data == "admin_stats":
        # Get statistics directly
        total_users = len(user_data)
        total_referrals = len(referral_data)
        total_referral_count = sum(data.get('total_referrals', 0) for data in referral_data.values())
        blocked_count = len(blocked_users) if blocked_users else 0
        total_commands = sum(data.get('command_count', 0) for data in user_data.values())
        
        # Calculate active users (last 7 days)
        active_users = 0
        seven_days_ago = datetime.now().timestamp() - (7 * 24 * 60 * 60)
        for user_id, data in user_data.items():
            last_seen = data.get('last_seen', '')
            if last_seen:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen)
                    if last_seen_dt.timestamp() > seven_days_ago:
                        active_users += 1
                except:
                    pass
        
        stats_text = (
            "📊 **Detailed Statistics**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 **Total Users:** {total_users}\n"
            f"🟢 **Active Users (7 days):** {active_users}\n"
            f"📈 **Total Commands:** {total_commands}\n"
            f"🎯 **Referral Users:** {total_referrals}\n"
            f"🔗 **Total Referrals:** {total_referral_count}\n"
            f"🚫 **Blocked Users:** {blocked_count}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await message.reply_text(stats_text, parse_mode='Markdown')
        
    elif callback_data == "admin_users":
        # Show users list
        if not user_data:
            await message.reply_text("📭 No users found.")
            return
        
        page = 1
        users_per_page = 10
        total_pages = (len(user_data) + users_per_page - 1) // users_per_page
        
        start_idx = 0
        end_idx = users_per_page
        users_list = list(user_data.items())[start_idx:end_idx]
        
        users_text = (
            f"👥 **All Users** (Page {page}/{total_pages})\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        for uid, data in users_list:
            username = data.get('username', 'N/A')
            name = data.get('first_name', 'Unknown')
            commands = data.get('command_count', 0)
            last_seen = data.get('last_seen', 'N/A')
            
            escaped_name = escape_markdown(str(name))
            escaped_username = escape_markdown(str(username))
            escaped_last_seen = escape_markdown(last_seen[:10] if len(last_seen) > 10 else str(last_seen))
            
            users_text += (
                f"👤 **{escaped_name}**\n"
                f"   ID: `{uid}`\n"
                f"   Username: @{escaped_username}\n"
                f"   Commands: {commands}\n"
                f"   Last Seen: {escaped_last_seen}\n\n"
            )
        
        users_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        users_text += f"💡 Use `/admin_users <page>` to see more pages"
        
        await message.reply_text(users_text, parse_mode='Markdown')
        
    elif callback_data == "admin_blocked":
        # Show blocked users
        if not blocked_users:
            await message.reply_text("📭 No users are currently blocked.")
            return
        
        blocked_text = (
            "🚫 **Blocked Users**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 **Total Blocked:** {len(blocked_users)}\n\n"
        )
        
        blocked_list = []
        for user_id_str in blocked_users:
            try:
                user_id = int(user_id_str)
                user_info = user_data.get(user_id_str, {})
                username = user_info.get('username', 'N/A')
                name = user_info.get('first_name', 'Unknown')
                blocked_list.append((user_id, name, username))
            except:
                blocked_list.append((user_id_str, 'Unknown', 'N/A'))
        
        blocked_list.sort(key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
        
        for i, (user_id, name, username) in enumerate(blocked_list, 1):
            escaped_name = escape_markdown(str(name))
            escaped_username = escape_markdown(str(username))
            blocked_text += f"{i}. **{escaped_name}** (@{escaped_username})\n"
            blocked_text += f"   ID: `{user_id}`\n\n"
        
        blocked_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        blocked_text += f"💡 Use `/admin_unblock <user_id>` to unblock a user"
        
        await message.reply_text(blocked_text, parse_mode='Markdown')
        
    elif callback_data == "admin_list":
        # Show admin list
        if not ADMIN_IDS:
            await message.reply_text("📭 No admins configured.")
            return
        
        admins_text = (
            "👥 **Admin List**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        for i, admin_id in enumerate(ADMIN_IDS, 1):
            admin_info = user_data.get(str(admin_id), {})
            name = admin_info.get('first_name', 'Unknown')
            username = admin_info.get('username', 'N/A')
            
            escaped_name = escape_markdown(str(name))
            escaped_username = escape_markdown(str(username))
            
            admins_text += f"{i}. **{escaped_name}** (@{escaped_username})\n"
            admins_text += f"   ID: `{admin_id}`\n\n"
        
        admins_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await message.reply_text(admins_text, parse_mode='Markdown')
        
    elif callback_data == "admin_referrals":
        # Show referral stats
        if not referral_data:
            await message.reply_text("📭 No referral data found.")
            return
        
        # Calculate real-time total
        total_refs_sum = sum(len(data.get('referrals', [])) for data in referral_data.values())
        
        referrals_text = (
            "🎯 **Referral Statistics**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 **Total Users with Referrals:** {len(referral_data)}\n"
            f"🔗 **Total Referrals:** {total_refs_sum}\n\n"
        )
        
        # Calculate real-time counts and sort
        referral_counts = []
        for user_id, data in referral_data.items():
            # Ensure referrals list exists
            if 'referrals' not in data:
                referral_data[user_id]['referrals'] = []
                data = referral_data[user_id]
            
            referrals_list = data.get('referrals', [])
            actual_count = len(referrals_list)
            
            # Always fix if total_referrals doesn't match actual list
            if data.get('total_referrals', 0) != actual_count:
                referral_data[user_id]['total_referrals'] = actual_count
                save_referral_data()
                logger.info(f"Fixed referral count for user {user_id} in callback: was {data.get('total_referrals', 0)}, now {actual_count}")
            
            referral_counts.append((user_id, data, actual_count))
        
        # Sort by actual count
        sorted_referrals = sorted(
            referral_counts,
            key=lambda x: x[2],  # Sort by actual_count
            reverse=True
        )[:10]  # Top 10
        
        for i, (user_id, data, total_refs) in enumerate(sorted_referrals, 1):
            user_info = user_data.get(user_id, {})
            name = user_info.get('first_name', 'Unknown')
            username = user_info.get('username', 'N/A')
            
            escaped_name = escape_markdown(str(name))
            escaped_username = escape_markdown(str(username))
            
            referrals_text += f"{i}. **{escaped_name}** (@{escaped_username})\n"
            referrals_text += f"   Referrals: {total_refs}\n"
            referrals_text += f"   ID: `{user_id}`\n\n"
        
        referrals_text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await message.reply_text(referrals_text, parse_mode='Markdown')
        
    else:
        await query.answer("Unknown action", show_alert=True)

async def admin_delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete user data from the system."""
    if not await admin_only(update, context):
        return
    
    user = update.effective_user
    if user:
        increment_command_count(user.id)
    
    # Check if replying to a message
    target_user_id = None
    if update.message.reply_to_message:
        replied_user = update.message.reply_to_message.from_user
        if replied_user:
            target_user_id = replied_user.id
    
    # If not replying, check args
    if not target_user_id:
        if not context.args:
            await update.message.reply_text(
                "🗑️ **Delete User Data**\n\n"
                "**Usage:** `/admin_delete_user <user_id>`\n\n"
                "**Methods:**\n"
                "1. Reply to a user's message: `/admin_delete_user`\n"
                "2. Use user ID: `/admin_delete_user 123456789`\n\n"
                "**Example:**\n"
                "`/admin_delete_user 123456789`\n\n"
                "⚠️ **Warning:** This will permanently delete all user data including:\n"
                "• User information\n"
                "• Command history\n"
                "• Last seen data\n\n"
                "User will need to `/start` again to be tracked.",
                parse_mode='Markdown'
            )
            return
        try:
            target_user_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID or reply to a user's message.")
            return
    
    try:
        target_user_id_str = str(target_user_id)
        
        # Check if trying to delete admin
        if target_user_id in ADMIN_IDS:
            await update.message.reply_text(
                "❌ **Cannot Delete Admin**\n\n"
                "⚠️ You cannot delete an administrator's data.",
                parse_mode='Markdown'
            )
            return
        
        # Check if user exists
        if target_user_id_str not in user_data:
            await update.message.reply_text(
                f"ℹ️ User `{target_user_id}` not found in user data.",
                parse_mode='Markdown'
            )
            return
        
        # Get user info before deletion
        user_info = user_data.get(target_user_id_str, {})
        username = user_info.get('username', 'N/A')
        name = user_info.get('first_name', 'Unknown')
        
        # Delete user data
        del user_data[target_user_id_str]
        save_user_data()
        
        # Keep referral data intact so user can rejoin with same referral link
        # Only remove this user from other referrers' referral lists (if they were referred)
        # But keep their own referral code and stats for when they rejoin
        
        # Remove this user from all referrers' referral lists
        # This allows them to be counted again if they rejoin with same referral link
        for referrer_id, ref_data in referral_data.items():
            referrals_list = ref_data.get('referrals', [])
            if target_user_id_str in referrals_list:
                referrals_list.remove(target_user_id_str)
                referral_data[referrer_id]['referrals'] = referrals_list
                # Update total_referrals based on actual list length
                new_total = len(referrals_list)
                referral_data[referrer_id]['total_referrals'] = new_total
                save_referral_data()
                logger.info(f"Removed user {target_user_id_str} from referrer {referrer_id}'s list. New total: {new_total}")
        
        # Note: We keep the user's own referral entry in referral_data
        # so if they rejoin, their referral code remains the same
        # and they can continue getting referrals
        
        await update.message.reply_text(
            f"✅ **User Data Deleted Successfully!**\n\n"
            f"👤 **User:** {escape_markdown(name)} (@{escape_markdown(username)})\n"
            f"🆔 **ID:** `{target_user_id}`\n\n"
            f"🗑️ All user data has been permanently deleted.\n"
            f"📝 User will need to `/start` again to be tracked.",
            parse_mode='Markdown'
        )
            
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a numeric user ID.")

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate math expression from command."""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a math expression!\n"
            "Example: /calc 25 + 17\n"
            "Example: /calc sqrt(16)\n"
            "Example: /calc sin(pi/2)\n"
            "Example: /calc factorial(5)\n\n"
            "**Available Functions:**\n"
            "• Basic: +, -, *, /, ^, sqrt, pow\n"
            "• Trig: sin, cos, tan, asin, acos, atan\n"
            "• Hyperbolic: sinh, cosh, tanh\n"
            "• Log: log, log10, log2, ln, exp\n"
            "• Other: factorial, gcd, lcm, ceil, floor, round\n"
            "• Constants: pi, e, tau"
        )
        return

    expression = ' '.join(context.args)
    result = calculate_math(expression)
    
    if result is None:
        await update.message.reply_text(
            f"❌ Invalid math expression: {expression}\n"
            "Please check your input and try again.\n\n"
            "💡 Use /help for examples"
        )
    else:
        await update.message.reply_text(
            f'📊 **Calculation Result:**\n\n'
            f'Expression: `{expression}`\n'
            f'Result: **{result}**',
            parse_mode='Markdown'
        )

async def solve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solve linear and quadratic equations."""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide an equation!\n\n"
            "**Examples:**\n"
            "• `/solve 2x + 5 = 15`\n"
            "• `/solve x^2 - 5x + 6 = 0`\n"
            "• `/solve 3x - 7 = 2x + 5`"
        )
        return
    
    equation = ' '.join(context.args).replace(' ', '').lower()
    
    try:
        # Linear equation: ax + b = c or ax + b = cx + d
        if 'x^2' not in equation and 'x²' not in equation:
            import re
            
            if '=' not in equation:
                await update.message.reply_text("❌ Equation must contain '='")
                return
            
            left, right = equation.split('=', 1)
            
            # Parse coefficients using better regex
            # Pattern to match: optional sign, optional number, 'x', or just numbers
            def parse_side(side):
                x_coeff = 0
                const = 0
                
                # Find all x terms: pattern like +2x, -3x, x, -x
                x_matches = re.findall(r'([+-]?\d*\.?\d*)x', side)
                for match in x_matches:
                    if match == '' or match == '+':
                        x_coeff += 1
                    elif match == '-':
                        x_coeff -= 1
                    else:
                        x_coeff += float(match)
                
                # Find all constants (numbers not followed by x)
                # Split by + and - to get terms
                parts = re.split(r'([+-])', side)
                current_sign = '+'
                for part in parts:
                    part = part.strip()
                    if part in ['+', '-']:
                        current_sign = part
                        continue
                    if part and 'x' not in part:
                        # Remove x terms that might be in the string
                        clean_part = re.sub(r'[+-]?\d*\.?\d*x', '', part)
                        if clean_part:
                            try:
                                num = float(clean_part)
                                if current_sign == '-':
                                    const -= num
                                else:
                                    const += num
                            except:
                                pass
                
                return x_coeff, const
            
            a, b = parse_side(left)
            c, d = parse_side(right)
            
            # Move everything to left: (a-c)x + (b-d) = 0
            coeff_x = a - c
            const = b - d
            
            if abs(coeff_x) < 1e-10:  # Use small epsilon for comparison
                if abs(const) < 1e-10:
                    result = "✅ Infinite solutions (identity equation)"
                else:
                    result = "❌ No solution (contradiction)"
            else:
                x = -const / coeff_x
                result = f"✅ Solution: x = {round(x, 6)}"
            
            await update.message.reply_text(
                f'🔢 **Equation Solver**\n\n'
                f'Equation: `{" ".join(context.args)}`\n'
                f'{result}',
                parse_mode='Markdown'
            )
        
        # Quadratic equation: ax² + bx + c = 0
        else:
            import re
            equation_clean = equation.replace('x²', 'x^2').replace('x^2', 'x^2')
            
            if '=' not in equation_clean:
                await update.message.reply_text("❌ Equation must contain '='")
                return
            
            left, right = equation_clean.split('=', 1)
            
            # Extract coefficients for ax^2 + bx + c = 0
            # Move everything to left side
            pattern = r'([+-]?\d*\.?\d*)x\^2|([+-]?\d*\.?\d*)x|([+-]?\d+\.?\d*)'
            
            a, b, c = 0, 0, 0
            
            # Parse left side
            for match in re.finditer(pattern, left):
                if match.group(1):  # x^2 term
                    coeff = match.group(1)
                    a += float(coeff) if coeff and coeff not in ['+', '-'] else (1 if not coeff or coeff == '+' else -1)
                elif match.group(2):  # x term
                    coeff = match.group(2)
                    b += float(coeff) if coeff and coeff not in ['+', '-'] else (1 if not coeff or coeff == '+' else -1)
                elif match.group(3):  # constant
                    c += float(match.group(3))
            
            # Parse right side and subtract
            for match in re.finditer(pattern, right):
                if match.group(1):  # x^2 term
                    coeff = match.group(1)
                    a -= float(coeff) if coeff and coeff not in ['+', '-'] else (1 if not coeff or coeff == '+' else -1)
                elif match.group(2):  # x term
                    coeff = match.group(2)
                    b -= float(coeff) if coeff and coeff not in ['+', '-'] else (1 if not coeff or coeff == '+' else -1)
                elif match.group(3):  # constant
                    c -= float(match.group(3))
            
            if a == 0:
                await update.message.reply_text("❌ Not a quadratic equation (a = 0)")
                return
            
            # Solve using quadratic formula
            discriminant = b**2 - 4*a*c
            
            if discriminant < 0:
                real_part = -b / (2*a)
                imag_part = math.sqrt(-discriminant) / (2*a)
                result = (
                    f"✅ Complex solutions:\n"
                    f"x₁ = {round(real_part, 6)} + {round(imag_part, 6)}i\n"
                    f"x₂ = {round(real_part, 6)} - {round(imag_part, 6)}i"
                )
            elif discriminant == 0:
                x = -b / (2*a)
                result = f"✅ One solution (double root):\nx = {round(x, 6)}"
            else:
                x1 = (-b + math.sqrt(discriminant)) / (2*a)
                x2 = (-b - math.sqrt(discriminant)) / (2*a)
                result = (
                    f"✅ Two solutions:\n"
                    f"x₁ = {round(x1, 6)}\n"
                    f"x₂ = {round(x2, 6)}"
                )
            
            await update.message.reply_text(
                f'🔢 **Quadratic Equation Solver**\n\n'
                f'Equation: `{" ".join(context.args)}`\n'
                f'Discriminant: {discriminant}\n\n'
                f'{result}',
                parse_mode='Markdown'
            )
    
    except Exception as e:
        logger.error(f"Equation solving error: {e}")
        await update.message.reply_text(
            f"❌ Error solving equation: {str(e)}\n\n"
            "Please check your equation format."
        )

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert between different units."""
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Usage: /convert <value> <from_unit> <to_unit>\n\n"
            "**Examples:**\n"
            "• `/convert 100 km m` (length)\n"
            "• `/convert 5 feet inch` (length)\n"
            "• `/convert 25 celsius fahrenheit` (temperature)\n"
            "• `/convert 10 kg pound` (weight)\n\n"
            "**Available Conversions:**\n"
            "• Length: m, km, cm, mm, mile, feet, inch, yard\n"
            "• Weight: kg, g, pound, ounce, ton\n"
            "• Temperature: celsius, fahrenheit, kelvin\n"
            "• Volume: liter, ml, gallon, cup, ounce_fluid"
        )
        return
    
    try:
        value = float(context.args[0])
        from_unit = context.args[1].lower()
        to_unit = context.args[2].lower()
        
        # Length conversions (all to meters first)
        length_to_m = {
            'm': 1, 'meter': 1, 'meters': 1,
            'km': 1000, 'kilometer': 1000, 'kilometers': 1000,
            'cm': 0.01, 'centimeter': 0.01, 'centimeters': 0.01,
            'mm': 0.001, 'millimeter': 0.001, 'millimeters': 0.001,
            'mile': 1609.34, 'miles': 1609.34,
            'feet': 0.3048, 'foot': 0.3048, 'ft': 0.3048,
            'inch': 0.0254, 'inches': 0.0254, 'in': 0.0254,
            'yard': 0.9144, 'yards': 0.9144, 'yd': 0.9144
        }
        
        # Weight conversions (all to kg first)
        weight_to_kg = {
            'kg': 1, 'kilogram': 1, 'kilograms': 1,
            'g': 0.001, 'gram': 0.001, 'grams': 0.001,
            'pound': 0.453592, 'pounds': 0.453592, 'lb': 0.453592,
            'ounce': 0.0283495, 'ounces': 0.0283495, 'oz': 0.0283495,
            'ton': 1000, 'tons': 1000
        }
        
        # Temperature conversions
        if from_unit in ['celsius', 'c', 'celcius'] and to_unit in ['fahrenheit', 'f']:
            result = (value * 9/5) + 32
            await update.message.reply_text(
                f'🌡️ **Temperature Conversion**\n\n'
                f'{value}°C = **{round(result, 2)}°F**'
            )
            return
        elif from_unit in ['fahrenheit', 'f'] and to_unit in ['celsius', 'c', 'celcius']:
            result = (value - 32) * 5/9
            await update.message.reply_text(
                f'🌡️ **Temperature Conversion**\n\n'
                f'{value}°F = **{round(result, 2)}°C**'
            )
            return
        elif from_unit in ['celsius', 'c', 'celcius'] and to_unit in ['kelvin', 'k']:
            result = value + 273.15
            await update.message.reply_text(
                f'🌡️ **Temperature Conversion**\n\n'
                f'{value}°C = **{round(result, 2)}K**'
            )
            return
        elif from_unit in ['kelvin', 'k'] and to_unit in ['celsius', 'c', 'celcius']:
            result = value - 273.15
            await update.message.reply_text(
                f'🌡️ **Temperature Conversion**\n\n'
                f'{value}K = **{round(result, 2)}°C**'
            )
            return
        elif from_unit in ['fahrenheit', 'f'] and to_unit in ['kelvin', 'k']:
            result = (value - 32) * 5/9 + 273.15
            await update.message.reply_text(
                f'🌡️ **Temperature Conversion**\n\n'
                f'{value}°F = **{round(result, 2)}K**'
            )
            return
        elif from_unit in ['kelvin', 'k'] and to_unit in ['fahrenheit', 'f']:
            result = (value - 273.15) * 9/5 + 32
            await update.message.reply_text(
                f'🌡️ **Temperature Conversion**\n\n'
                f'{value}K = **{round(result, 2)}°F**'
            )
            return
        
        # Length conversion
        elif from_unit in length_to_m and to_unit in length_to_m:
            meters = value * length_to_m[from_unit]
            result = meters / length_to_m[to_unit]
            await update.message.reply_text(
                f'📏 **Length Conversion**\n\n'
                f'{value} {from_unit} = **{round(result, 6)} {to_unit}**'
            )
            return
        
        # Weight conversion
        elif from_unit in weight_to_kg and to_unit in weight_to_kg:
            kg = value * weight_to_kg[from_unit]
            result = kg / weight_to_kg[to_unit]
            await update.message.reply_text(
                f'⚖️ **Weight Conversion**\n\n'
                f'{value} {from_unit} = **{round(result, 6)} {to_unit}**'
            )
            return
        
        else:
            await update.message.reply_text(
                f"❌ Unsupported conversion: {from_unit} → {to_unit}\n\n"
                "Use /convert for help with available units."
            )
    
    except ValueError:
        await update.message.reply_text("❌ Invalid number format")
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await update.message.reply_text(f"❌ Conversion error: {str(e)}")

async def bin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert number to binary."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /bin <number>\n"
            "Example: /bin 255"
        )
        return
    
    try:
        num = int(context.args[0])
        binary = bin(num)[2:]  # Remove '0b' prefix
        await update.message.reply_text(
            f'🔢 **Binary Conversion**\n\n'
            f'Decimal: {num}\n'
            f'Binary: **{binary}**\n'
            f'Hex: {hex(num)[2:].upper()}\n'
            f'Octal: {oct(num)[2:]}'
        )
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid integer")

async def hex_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert number to hexadecimal."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /hex <number>\n"
            "Example: /hex 255"
        )
        return
    
    try:
        num = int(context.args[0])
        hexadecimal = hex(num)[2:].upper()  # Remove '0x' prefix
        await update.message.reply_text(
            f'🔢 **Hexadecimal Conversion**\n\n'
            f'Decimal: {num}\n'
            f'Binary: {bin(num)[2:]}\n'
            f'Hex: **{hexadecimal}**\n'
            f'Octal: {oct(num)[2:]}'
        )
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid integer")

async def oct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert number to octal."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /oct <number>\n"
            "Example: /oct 255"
        )
        return
    
    try:
        num = int(context.args[0])
        octal = oct(num)[2:]  # Remove '0o' prefix
        await update.message.reply_text(
            f'🔢 **Octal Conversion**\n\n'
            f'Decimal: {num}\n'
            f'Binary: {bin(num)[2:]}\n'
            f'Hex: {hex(num)[2:].upper()}\n'
            f'Octal: **{octal}**'
        )
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid integer")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate statistics from a list of numbers."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /stats <numbers>\n"
            "Example: /stats 1 2 3 4 5 6 7 8 9 10\n"
            "Example: /stats 10,20,30,40,50"
        )
        return
    
    try:
        # Parse numbers (support space or comma separated)
        numbers_str = ' '.join(context.args)
        numbers = []
        for num_str in re.split(r'[,\s]+', numbers_str):
            if num_str.strip():
                numbers.append(float(num_str.strip()))
        
        if len(numbers) < 2:
            await update.message.reply_text("❌ Please provide at least 2 numbers")
            return
        
        # Calculate statistics
        n = len(numbers)
        mean = sum(numbers) / n
        sorted_nums = sorted(numbers)
        
        # Median
        if n % 2 == 0:
            median = (sorted_nums[n//2 - 1] + sorted_nums[n//2]) / 2
        else:
            median = sorted_nums[n//2]
        
        # Mode
        from collections import Counter
        counter = Counter(numbers)
        max_count = max(counter.values())
        modes = [num for num, count in counter.items() if count == max_count]
        mode_str = f"{modes[0]}" if len(modes) == 1 else f"{', '.join(map(str, modes))}"
        
        # Standard deviation
        variance = sum((x - mean)**2 for x in numbers) / n
        std_dev = math.sqrt(variance)
        
        # Min, Max, Range
        min_val = min(numbers)
        max_val = max(numbers)
        range_val = max_val - min_val
        
        # Sum
        total_sum = sum(numbers)
        
        result_text = (
            f'📊 **Statistical Analysis**\n\n'
            f'Numbers: {", ".join(map(str, numbers[:10]))}{"..." if len(numbers) > 10 else ""}\n'
            f'Count: {n}\n\n'
            f'📈 **Measures of Central Tendency:**\n'
            f'• Mean: {round(mean, 4)}\n'
            f'• Median: {round(median, 4)}\n'
            f'• Mode: {mode_str}\n\n'
            f'📊 **Measures of Spread:**\n'
            f'• Standard Deviation: {round(std_dev, 4)}\n'
            f'• Variance: {round(variance, 4)}\n'
            f'• Range: {round(range_val, 4)}\n'
            f'• Min: {min_val}\n'
            f'• Max: {max_val}\n'
            f'• Sum: {round(total_sum, 4)}'
        )
        
        await update.message.reply_text(result_text)
    
    except ValueError as e:
        await update.message.reply_text(f"❌ Invalid number format: {str(e)}")
    except Exception as e:
        logger.error(f"Statistics error: {e}")
        await update.message.reply_text(f"❌ Error calculating statistics: {str(e)}")

async def percent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate percentages."""
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /percent <operation> <values>\n\n"
            "**Operations:**\n"
            "• `/percent of <percent> <number>` - Calculate percentage\n"
            "   Example: /percent of 25 200 → 50\n\n"
            "• `/percent increase <percent> <number>` - Increase by percentage\n"
            "   Example: /percent increase 20 100 → 120\n\n"
            "• `/percent decrease <percent> <number>` - Decrease by percentage\n"
            "   Example: /percent decrease 10 100 → 90\n\n"
            "• `/percent change <old> <new>` - Calculate percentage change\n"
            "   Example: /percent change 50 75 → 50% increase"
        )
        return
    
    try:
        if len(context.args) < 3:
            await update.message.reply_text("❌ Insufficient arguments. Use /percent for help.")
            return
        
        operation = context.args[0].lower()
        
        if operation == 'of':
            percent = float(context.args[1])
            number = float(context.args[2])
            result = (percent / 100) * number
            await update.message.reply_text(
                f'📊 **Percentage Calculation**\n\n'
                f'{percent}% of {number} = **{round(result, 2)}**'
            )
        
        elif operation == 'increase':
            percent = float(context.args[1])
            number = float(context.args[2])
            result = number * (1 + percent / 100)
            await update.message.reply_text(
                f'📊 **Percentage Increase**\n\n'
                f'{number} + {percent}% = **{round(result, 2)}**\n'
                f'Increase: {round(result - number, 2)}'
            )
        
        elif operation == 'decrease':
            percent = float(context.args[1])
            number = float(context.args[2])
            result = number * (1 - percent / 100)
            await update.message.reply_text(
                f'📊 **Percentage Decrease**\n\n'
                f'{number} - {percent}% = **{round(result, 2)}**\n'
                f'Decrease: {round(number - result, 2)}'
            )
        
        elif operation == 'change':
            old_val = float(context.args[1])
            new_val = float(context.args[2])
            change = ((new_val - old_val) / old_val) * 100
            direction = "increase" if change > 0 else "decrease"
            await update.message.reply_text(
                f'📊 **Percentage Change**\n\n'
                f'Old: {old_val}\n'
                f'New: {new_val}\n'
                f'Change: **{round(abs(change), 2)}% {direction}**'
            )
        
        else:
            await update.message.reply_text(
                f"❌ Unknown operation: {operation}\n\n"
                "Use /percent for available operations."
            )
    
    except ValueError:
        await update.message.reply_text("❌ Invalid number format")
    except Exception as e:
        logger.error(f"Percentage calculation error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def password_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a secure random password."""
    try:
        # Default password length
        length = 16
        
        # Check if user provided custom length
        if context.args and len(context.args) > 0:
            try:
                length = int(context.args[0])
                if length < 4:
                    await update.message.reply_text(
                        "❌ Password length must be at least 4 characters.\n"
                        "Usage: `/password [length]`\n"
                        "Example: `/password 20`",
                        parse_mode='Markdown'
                    )
                    return
                if length > 100:
                    await update.message.reply_text(
                        "❌ Password length cannot exceed 100 characters.\n"
                        "Usage: `/password [length]`\n"
                        "Example: `/password 20`",
                        parse_mode='Markdown'
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "❌ Invalid length. Please provide a number.\n"
                    "Usage: `/password [length]`\n"
                    "Example: `/password 20`",
                    parse_mode='Markdown'
                )
                return
        
        # Character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        # Combine all character sets
        all_chars = lowercase + uppercase + digits + special
        
        # Generate password ensuring at least one character from each set
        password_chars = [
            random.choice(lowercase),
            random.choice(uppercase),
            random.choice(digits),
            random.choice(special)
        ]
        
        # Fill the rest randomly
        for _ in range(length - 4):
            password_chars.append(random.choice(all_chars))
        
        # Shuffle to avoid predictable pattern
        random.shuffle(password_chars)
        
        # Join to create final password
        password = ''.join(password_chars)
        
        # Calculate strength
        strength = "Strong"
        if length < 8:
            strength = "Weak"
        elif length < 12:
            strength = "Medium"
        
        # Send password
        response = (
            f"🔐 **Password Generated**\n\n"
            f"**Password:** `{password}`\n"
            f"**Length:** {length} characters\n"
            f"**Strength:** {strength}\n\n"
            f"💡 **Security Tips:**\n"
            f"• Use at least 12 characters for better security\n"
            f"• Don't share your password with anyone\n"
            f"• Use different passwords for different accounts\n"
            f"• Consider using a password manager"
        )
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Password generation error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error generating password. Please try again."
        )

def parse_user_agent(user_agent):
    """Parse user agent string and extract device information."""
    ua = user_agent.lower()
    info = {
        'browser': 'Unknown',
        'browser_version': '',
        'os': 'Unknown',
        'os_version': '',
        'device': 'Unknown',
        'device_type': 'Desktop'
    }
    
    # Browser detection
    if 'chrome' in ua and 'edg' not in ua and 'opr' not in ua:
        info['browser'] = 'Chrome'
        match = re.search(r'chrome/([\d.]+)', ua)
        if match:
            info['browser_version'] = match.group(1)
    elif 'firefox' in ua:
        info['browser'] = 'Firefox'
        match = re.search(r'firefox/([\d.]+)', ua)
        if match:
            info['browser_version'] = match.group(1)
    elif 'safari' in ua and 'chrome' not in ua:
        info['browser'] = 'Safari'
        match = re.search(r'version/([\d.]+)', ua)
        if match:
            info['browser_version'] = match.group(1)
    elif 'edg' in ua:
        info['browser'] = 'Edge'
        match = re.search(r'edg/([\d.]+)', ua)
        if match:
            info['browser_version'] = match.group(1)
    elif 'opr' in ua or 'opera' in ua:
        info['browser'] = 'Opera'
        match = re.search(r'(?:opr|opera)/([\d.]+)', ua)
        if match:
            info['browser_version'] = match.group(1)
    elif 'msie' in ua or 'trident' in ua:
        info['browser'] = 'Internet Explorer'
        match = re.search(r'msie ([\d.]+)', ua) or re.search(r'rv:([\d.]+)', ua)
        if match:
            info['browser_version'] = match.group(1)
    
    # OS detection
    if 'windows' in ua:
        info['os'] = 'Windows'
        if 'windows nt 10.0' in ua or 'windows 10' in ua:
            info['os_version'] = '10'
        elif 'windows nt 6.3' in ua:
            info['os_version'] = '8.1'
        elif 'windows nt 6.2' in ua:
            info['os_version'] = '8'
        elif 'windows nt 6.1' in ua:
            info['os_version'] = '7'
        elif 'windows nt 6.0' in ua:
            info['os_version'] = 'Vista'
        elif 'windows nt 5.1' in ua:
            info['os_version'] = 'XP'
    elif 'mac os x' in ua or 'macintosh' in ua:
        info['os'] = 'macOS'
        match = re.search(r'mac os x ([\d_]+)', ua)
        if match:
            info['os_version'] = match.group(1).replace('_', '.')
    elif 'linux' in ua:
        info['os'] = 'Linux'
        if 'ubuntu' in ua:
            info['os_version'] = 'Ubuntu'
        elif 'debian' in ua:
            info['os_version'] = 'Debian'
        elif 'fedora' in ua:
            info['os_version'] = 'Fedora'
    elif 'android' in ua:
        info['os'] = 'Android'
        match = re.search(r'android ([\d.]+)', ua)
        if match:
            info['os_version'] = match.group(1)
        info['device_type'] = 'Mobile'
    elif 'iphone' in ua or 'ipad' in ua or 'ipod' in ua:
        info['os'] = 'iOS'
        match = re.search(r'os ([\d_]+)', ua)
        if match:
            info['os_version'] = match.group(1).replace('_', '.')
        if 'iphone' in ua:
            info['device'] = 'iPhone'
            info['device_type'] = 'Mobile'
        elif 'ipad' in ua:
            info['device'] = 'iPad'
            info['device_type'] = 'Tablet'
        elif 'ipod' in ua:
            info['device'] = 'iPod'
            info['device_type'] = 'Mobile'
    
    # Device detection for mobile
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        if 'tablet' in ua or 'ipad' in ua:
            info['device_type'] = 'Tablet'
        else:
            info['device_type'] = 'Mobile'
        
        # Android device detection
        if 'android' in ua:
            if 'samsung' in ua:
                info['device'] = 'Samsung'
            elif 'xiaomi' in ua:
                info['device'] = 'Xiaomi'
            elif 'huawei' in ua:
                info['device'] = 'Huawei'
            elif 'oneplus' in ua:
                info['device'] = 'OnePlus'
            elif 'google' in ua and 'pixel' in ua:
                info['device'] = 'Google Pixel'
    
    return info

async def deviceinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get device information from user agent or system info."""
    try:
        # If user provided a user agent string
        if context.args and len(context.args) > 0:
            user_agent = ' '.join(context.args)
            
            # Parse user agent
            device_info = parse_user_agent(user_agent)
            
            # Build response
            response = "📱 **Device Information**\n\n"
            response += f"**Browser:** {device_info['browser']}"
            if device_info['browser_version']:
                response += f" {device_info['browser_version']}"
            response += "\n"
            
            response += f"**OS:** {device_info['os']}"
            if device_info['os_version']:
                response += f" {device_info['os_version']}"
            response += "\n"
            
            if device_info['device'] != 'Unknown':
                response += f"**Device:** {device_info['device']}\n"
            
            response += f"**Device Type:** {device_info['device_type']}\n\n"
            response += f"**User Agent:**\n`{user_agent}`"
            
            await update.message.reply_text(response, parse_mode='Markdown')
            
        else:
            # Show system info and Telegram user info
            user = update.effective_user
            
            # System information
            system_info = {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'python_implementation': platform.python_implementation()
            }
            
            # Build response
            response = "💻 **System Information**\n\n"
            response += f"**OS:** {system_info['system']} {system_info['release']}\n"
            response += f"**Platform:** {system_info['machine']}\n"
            response += f"**Processor:** {system_info['processor']}\n"
            response += f"**Python:** {system_info['python_version']} ({system_info['python_implementation']})\n\n"
            
            # Telegram user info
            if user:
                response += "👤 **Telegram User Info**\n\n"
                response += f"**ID:** `{user.id}`\n"
                response += f"**Username:** @{user.username}\n" if user.username else "**Username:** Not set\n"
                response += f"**First Name:** {user.first_name}\n"
                if user.last_name:
                    response += f"**Last Name:** {user.last_name}\n"
                response += f"**Language Code:** {user.language_code}\n" if user.language_code else ""
                response += f"**Is Bot:** {'Yes' if user.is_bot else 'No'}\n"
            
            response += "\n💡 **Usage:**\n"
            response += "• `/deviceinfo` - Show system info\n"
            response += "• `/deviceinfo <user_agent>` - Parse user agent string\n"
            response += "Example: `/deviceinfo Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0`"
            
            await update.message.reply_text(response, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Device info command error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error getting device information. Please try again.\n\n"
            "Usage: `/deviceinfo [user_agent_string]`\n"
            "Example: `/deviceinfo Mozilla/5.0...`",
            parse_mode='Markdown'
        )

def convert_to_fancy_font(text, style='bold'):
    """Convert text to fancy Unicode font styles."""
    # Character mappings for different font styles
    fonts = {
        'bold': {
            'a': '𝐚', 'b': '𝐛', 'c': '𝐜', 'd': '𝐝', 'e': '𝐞', 'f': '𝐟', 'g': '𝐠', 'h': '𝐡',
            'i': '𝐢', 'j': '𝐣', 'k': '𝐤', 'l': '𝐥', 'm': '𝐦', 'n': '𝐧', 'o': '𝐨', 'p': '𝐩',
            'q': '𝐪', 'r': '𝐫', 's': '𝐬', 't': '𝐭', 'u': '𝐮', 'v': '𝐯', 'w': '𝐰', 'x': '𝐱',
            'y': '𝐲', 'z': '𝐳', 'A': '𝐀', 'B': '𝐁', 'C': '𝐂', 'D': '𝐃', 'E': '𝐄', 'F': '𝐅',
            'G': '𝐆', 'H': '𝐇', 'I': '𝐈', 'J': '𝐉', 'K': '𝐊', 'L': '𝐋', 'M': '𝐌', 'N': '𝐍',
            'O': '𝐎', 'P': '𝐏', 'Q': '𝐐', 'R': '𝐑', 'S': '𝐒', 'T': '𝐓', 'U': '𝐔', 'V': '𝐕',
            'W': '𝐖', 'X': '𝐗', 'Y': '𝐘', 'Z': '𝐙', '0': '𝟎', '1': '𝟏', '2': '𝟐', '3': '𝟑',
            '4': '𝟒', '5': '𝟓', '6': '𝟔', '7': '𝟕', '8': '𝟖', '9': '𝟗'
        },
        'italic': {
            'a': '𝑎', 'b': '𝑏', 'c': '𝑐', 'd': '𝑑', 'e': '𝑒', 'f': '𝑓', 'g': '𝑔', 'h': 'ℎ',
            'i': '𝑖', 'j': '𝑗', 'k': '𝑘', 'l': '𝑙', 'm': '𝑚', 'n': '𝑛', 'o': '𝑜', 'p': '𝑝',
            'q': '𝑞', 'r': '𝑟', 's': '𝑠', 't': '𝑡', 'u': '𝑢', 'v': '𝑣', 'w': '𝑤', 'x': '𝑥',
            'y': '𝑦', 'z': '𝑧', 'A': '𝐴', 'B': '𝐵', 'C': '𝐶', 'D': '𝐷', 'E': '𝐸', 'F': '𝐹',
            'G': '𝐺', 'H': '𝐻', 'I': '𝐼', 'J': '𝐽', 'K': '𝐾', 'L': '𝐿', 'M': '𝑀', 'N': '𝑁',
            'O': '𝑂', 'P': '𝑃', 'Q': '𝑄', 'R': '𝑅', 'S': '𝑆', 'T': '𝑇', 'U': '𝑈', 'V': '𝑉',
            'W': '𝑊', 'X': '𝑋', 'Y': '𝑌', 'Z': '𝑍'
        },
        'bolditalic': {
            'a': '𝒂', 'b': '𝒃', 'c': '𝒄', 'd': '𝒅', 'e': '𝒆', 'f': '𝒇', 'g': '𝒈', 'h': '𝒉',
            'i': '𝒊', 'j': '𝒋', 'k': '𝒌', 'l': '𝒍', 'm': '𝒎', 'n': '𝒏', 'o': '𝒐', 'p': '𝒑',
            'q': '𝒒', 'r': '𝒓', 's': '𝒔', 't': '𝒕', 'u': '𝒖', 'v': '𝒗', 'w': '𝒘', 'x': '𝒙',
            'y': '𝒚', 'z': '𝒛', 'A': '𝑨', 'B': '𝑩', 'C': '𝑪', 'D': '𝑫', 'E': '𝑬', 'F': '𝑭',
            'G': '𝑮', 'H': '𝑯', 'I': '𝑰', 'J': '𝑱', 'K': '𝑲', 'L': '𝑳', 'M': '𝑴', 'N': '𝑵',
            'O': '𝑶', 'P': '𝑷', 'Q': '𝑸', 'R': '𝑹', 'S': '𝑺', 'T': '𝑻', 'U': '𝑼', 'V': '𝑽',
            'W': '𝑾', 'X': '𝑿', 'Y': '𝒀', 'Z': '𝒁'
        },
        'monospace': {
            'a': '𝚊', 'b': '𝚋', 'c': '𝚌', 'd': '𝚍', 'e': '𝚎', 'f': '𝚏', 'g': '𝚐', 'h': '𝚑',
            'i': '𝚒', 'j': '𝚓', 'k': '𝚔', 'l': '𝚕', 'm': '𝚖', 'n': '𝚗', 'o': '𝚘', 'p': '𝚙',
            'q': '𝚚', 'r': '𝚛', 's': '𝚜', 't': '𝚝', 'u': '𝚞', 'v': '𝚟', 'w': '𝚠', 'x': '𝚡',
            'y': '𝚢', 'z': '𝚣', 'A': '𝙰', 'B': '𝙱', 'C': '𝙲', 'D': '𝙳', 'E': '𝙴', 'F': '𝙵',
            'G': '𝙶', 'H': '𝙷', 'I': '𝙸', 'J': '𝙹', 'K': '𝙺', 'L': '𝙻', 'M': '𝙼', 'N': '𝙽',
            'O': '𝙾', 'P': '𝙿', 'Q': '𝚀', 'R': '𝚁', 'S': '𝚂', 'T': '𝚃', 'U': '𝚄', 'V': '𝚅',
            'W': '𝚆', 'X': '𝚇', 'Y': '𝚈', 'Z': '𝚉', '0': '𝟶', '1': '𝟷', '2': '𝟸', '3': '𝟹',
            '4': '𝟺', '5': '𝟻', '6': '𝟼', '7': '𝟽', '8': '𝟾', '9': '𝟿'
        },
        'script': {
            'a': '𝒶', 'b': '𝒷', 'c': '𝒸', 'd': '𝒹', 'e': 'ℯ', 'f': '𝒻', 'g': 'ℊ', 'h': '𝒽',
            'i': '𝒾', 'j': '𝒿', 'k': '𝓀', 'l': '𝓁', 'm': '𝓂', 'n': '𝓃', 'o': 'ℴ', 'p': '𝓅',
            'q': '𝓆', 'r': '𝓇', 's': '𝓈', 't': '𝓉', 'u': '𝓊', 'v': '𝓋', 'w': '𝓌', 'x': '𝓍',
            'y': '𝓎', 'z': '𝓏', 'A': '𝒜', 'B': 'ℬ', 'C': '𝒞', 'D': '𝒟', 'E': 'ℰ', 'F': 'ℱ',
            'G': '𝒢', 'H': 'ℋ', 'I': 'ℐ', 'J': '𝒥', 'K': '𝒦', 'L': 'ℒ', 'M': 'ℳ', 'N': '𝒩',
            'O': '𝒪', 'P': '𝒫', 'Q': '𝒬', 'R': 'ℛ', 'S': '𝒮', 'T': '𝒯', 'U': '𝒰', 'V': '𝒱',
            'W': '𝒲', 'X': '𝒳', 'Y': '𝒴', 'Z': '𝒵'
        },
        'fraktur': {
            'a': '𝔞', 'b': '𝔟', 'c': '𝔠', 'd': '𝔡', 'e': '𝔢', 'f': '𝔣', 'g': '𝔤', 'h': '𝔥',
            'i': '𝔦', 'j': '𝔧', 'k': '𝔨', 'l': '𝔩', 'm': '𝔪', 'n': '𝔫', 'o': '𝔬', 'p': '𝔭',
            'q': '𝔮', 'r': '𝔯', 's': '𝔰', 't': '𝔱', 'u': '𝔲', 'v': '𝔳', 'w': '𝔴', 'x': '𝔵',
            'y': '𝔶', 'z': '𝔷', 'A': '𝔄', 'B': '𝔅', 'C': 'ℭ', 'D': '𝔇', 'E': '𝔈', 'F': '𝔉',
            'G': '𝔊', 'H': 'ℌ', 'I': 'ℑ', 'J': '𝔍', 'K': '𝔎', 'L': '𝔏', 'M': '𝔐', 'N': '𝔑',
            'O': '𝔒', 'P': '𝔓', 'Q': '𝔔', 'R': 'ℜ', 'S': '𝔖', 'T': '𝔗', 'U': '𝔘', 'V': '𝔙',
            'W': '𝔚', 'X': '𝔛', 'Y': '𝔜', 'Z': 'ℨ'
        },
        'doublestruck': {
            'a': '𝕒', 'b': '𝕓', 'c': '𝕔', 'd': '𝕕', 'e': '𝕖', 'f': '𝕗', 'g': '𝕘', 'h': '𝕙',
            'i': '𝕚', 'j': '𝕛', 'k': '𝕜', 'l': '𝕝', 'm': '𝕞', 'n': '𝕟', 'o': '𝕠', 'p': '𝕡',
            'q': '𝕢', 'r': '𝕣', 's': '𝕤', 't': '𝕥', 'u': '𝕦', 'v': '𝕧', 'w': '𝕨', 'x': '𝕩',
            'y': '𝕪', 'z': '𝕫', 'A': '𝔸', 'B': '𝔹', 'C': 'ℂ', 'D': '𝔻', 'E': '𝔼', 'F': '𝔽',
            'G': '𝔾', 'H': 'ℍ', 'I': '𝕀', 'J': '𝕁', 'K': '𝕂', 'L': '𝕃', 'M': '𝕄', 'N': 'ℕ',
            'O': '𝕆', 'P': 'ℙ', 'Q': 'ℚ', 'R': 'ℝ', 'S': '𝕊', 'T': '𝕋', 'U': '𝕌', 'V': '𝕍',
            'W': '𝕎', 'X': '𝕏', 'Y': '𝕐', 'Z': 'ℤ', '0': '𝟘', '1': '𝟙', '2': '𝟚', '3': '𝟛',
            '4': '𝟜', '5': '𝟝', '6': '𝟞', '7': '𝟟', '8': '𝟠', '9': '𝟡'
        },
        'fullwidth': {
            'a': 'ａ', 'b': 'ｂ', 'c': 'ｃ', 'd': 'ｄ', 'e': 'ｅ', 'f': 'ｆ', 'g': 'ｇ', 'h': 'ｈ',
            'i': 'ｉ', 'j': 'ｊ', 'k': 'ｋ', 'l': 'ｌ', 'm': 'ｍ', 'n': 'ｎ', 'o': 'ｏ', 'p': 'ｐ',
            'q': 'ｑ', 'r': 'ｒ', 's': 'ｓ', 't': 'ｔ', 'u': 'ｕ', 'v': 'ｖ', 'w': 'ｗ', 'x': 'ｘ',
            'y': 'ｙ', 'z': 'ｚ', 'A': 'Ａ', 'B': 'Ｂ', 'C': 'Ｃ', 'D': 'Ｄ', 'E': 'Ｅ', 'F': 'Ｆ',
            'G': 'Ｇ', 'H': 'Ｈ', 'I': 'Ｉ', 'J': 'Ｊ', 'K': 'Ｋ', 'L': 'Ｌ', 'M': 'Ｍ', 'N': 'Ｎ',
            'O': 'Ｏ', 'P': 'Ｐ', 'Q': 'Ｑ', 'R': 'Ｒ', 'S': 'Ｓ', 'T': 'Ｔ', 'U': 'Ｕ', 'V': 'Ｖ',
            'W': 'Ｗ', 'X': 'Ｘ', 'Y': 'Ｙ', 'Z': 'Ｚ', '0': '０', '1': '１', '2': '２', '3': '３',
            '4': '４', '5': '５', '6': '６', '7': '７', '8': '８', '9': '９', ' ': '　', '!': '！',
            '.': '．', ',': '，', ':': '：', ';': '；', '?': '？'
        },
        'smallcaps': {
            'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
            'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
            'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
            'y': 'ʏ', 'z': 'ᴢ'
        },
        'circled': {
            'a': 'ⓐ', 'b': 'ⓑ', 'c': 'ⓒ', 'd': 'ⓓ', 'e': 'ⓔ', 'f': 'ⓕ', 'g': 'ⓖ', 'h': 'ⓗ',
            'i': 'ⓘ', 'j': 'ⓙ', 'k': 'ⓚ', 'l': 'ⓛ', 'm': 'ⓜ', 'n': 'ⓝ', 'o': 'ⓞ', 'p': 'ⓟ',
            'q': 'ⓠ', 'r': 'ⓡ', 's': 'ⓢ', 't': 'ⓣ', 'u': 'ⓤ', 'v': 'ⓥ', 'w': 'ⓦ', 'x': 'ⓧ',
            'y': 'ⓨ', 'z': 'ⓩ', 'A': 'Ⓐ', 'B': 'Ⓑ', 'C': 'Ⓒ', 'D': 'Ⓓ', 'E': 'Ⓔ', 'F': 'Ⓕ',
            'G': 'Ⓖ', 'H': 'Ⓗ', 'I': 'Ⓘ', 'J': 'Ⓙ', 'K': 'Ⓚ', 'L': 'Ⓛ', 'M': 'Ⓜ', 'N': 'Ⓝ',
            'O': 'Ⓞ', 'P': 'Ⓟ', 'Q': 'Ⓠ', 'R': 'Ⓡ', 'S': 'Ⓢ', 'T': 'Ⓣ', 'U': 'Ⓤ', 'V': 'Ⓥ',
            'W': 'Ⓦ', 'X': 'Ⓧ', 'Y': 'Ⓨ', 'Z': 'Ⓩ', '0': '⓪', '1': '①', '2': '②', '3': '③',
            '4': '④', '5': '⑤', '6': '⑥', '7': '⑦', '8': '⑧', '9': '⑨'
        },
        'squared': {
            'a': '🅰', 'b': '🅱', 'c': '🅲', 'd': '🅳', 'e': '🅴', 'f': '🅵', 'g': '🅶', 'h': '🅷',
            'i': '🅸', 'j': '🅹', 'k': '🅺', 'l': '🅻', 'm': '🅼', 'n': '🅽', 'o': '🅾', 'p': '🅿',
            'q': '🆀', 'r': '🆁', 's': '🆂', 't': '🆃', 'u': '🆄', 'v': '🆅', 'w': '🆆', 'x': '🆇',
            'y': '🆈', 'z': '🆉', '0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
            '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'
        },
        'upsidedown': {
            'a': 'ɐ', 'b': 'q', 'c': 'ɔ', 'd': 'p', 'e': 'ǝ', 'f': 'ɟ', 'g': 'ƃ', 'h': 'ɥ',
            'i': 'ᴉ', 'j': 'ɾ', 'k': 'ʞ', 'l': 'l', 'm': 'ɯ', 'n': 'u', 'o': 'o', 'p': 'd',
            'q': 'b', 'r': 'ɹ', 's': 's', 't': 'ʇ', 'u': 'n', 'v': 'ʌ', 'w': 'ʍ', 'x': 'x',
            'y': 'ʎ', 'z': 'z', 'A': '∀', 'B': '𐐒', 'C': 'Ɔ', 'D': 'ᗡ', 'E': 'Ǝ', 'F': 'Ⅎ',
            'G': 'פ', 'H': 'H', 'I': 'I', 'J': 'ſ', 'K': 'ʞ', 'L': '˥', 'M': 'W', 'N': 'N',
            'O': 'O', 'P': 'Ԁ', 'Q': 'Q', 'R': 'ᴿ', 'S': 'S', 'T': '┴', 'U': '∩', 'V': 'Λ',
            'W': 'M', 'X': 'X', 'Y': '⅄', 'Z': 'Z', '0': '0', '1': 'Ɩ', '2': 'ᄅ', '3': 'Ɛ',
            '4': 'ㄣ', '5': 'ϛ', '6': '9', '7': 'ㄥ', '8': '8', '9': '6', '.': '˙', ',': '\'',
            '?': '¿', '!': '¡', '(': ')', ')': '(', '[': ']', ']': '[', '{': '}', '}': '{',
            '/': '\\', '\\': '/'
        }
    }
    
    if style not in fonts:
        style = 'bold'
    
    font_map = fonts[style]
    result = []
    
    for char in text:
        if char in font_map:
            result.append(font_map[char])
        else:
            result.append(char)
    
    return ''.join(result)

def text_to_emoji(text):
    """Convert text words to emojis."""
    # Comprehensive emoji mapping dictionary
    emoji_map = {
        # Emotions & Feelings
        'happy': '😊', 'happiness': '😊', 'joy': '😄', 'joyful': '😄',
        'sad': '😢', 'sadness': '😢', 'cry': '😭', 'crying': '😭',
        'angry': '😠', 'anger': '😠', 'mad': '😡', 'furious': '😡',
        'love': '❤️', 'loved': '❤️', 'loving': '❤️', 'heart': '❤️',
        'like': '👍', 'liked': '👍', 'dislike': '👎', 'disliked': '👎',
        'funny': '😂', 'fun': '😆', 'laugh': '😂', 'laughing': '😂',
        'smile': '😊', 'smiling': '😊', 'grin': '😁', 'grinning': '😁',
        'wink': '😉', 'winking': '😉', 'cool': '😎', 'awesome': '😎',
        'surprised': '😮', 'surprise': '😮', 'shocked': '😲', 'shock': '😲',
        'wow': '😮', 'amazing': '🤩', 'wonderful': '🤩',
        'excited': '🤗', 'excitement': '🤗', 'excite': '🤗',
        'tired': '😴', 'sleepy': '😴', 'sleep': '😴', 'sleeping': '😴',
        'sick': '🤒', 'ill': '🤒', 'fever': '🤒',
        'confused': '😕', 'confusion': '😕', 'confuse': '😕',
        'thinking': '🤔', 'think': '🤔', 'thought': '🤔',
        'worried': '😟', 'worry': '😟', 'anxious': '😰', 'anxiety': '😰',
        'scared': '😨', 'scary': '😨', 'fear': '😨', 'afraid': '😨',
        'embarrassed': '😳', 'embarrass': '😳', 'shy': '😳',
        'kiss': '😘', 'kissing': '😘', 'kisses': '😘',
        'hug': '🤗', 'hugging': '🤗', 'hugs': '🤗',
        'fire': '🔥', 'hot': '🔥', 'lit': '🔥',
        'party': '🎉', 'celebration': '🎉', 'celebrate': '🎉',
        'birthday': '🎂', 'cake': '🎂',
        'star': '⭐', 'stars': '⭐', 'favorite': '⭐',
        'thumbsup': '👍', 'thumbs down': '👎',
        
        # Objects & Things
        'phone': '📱', 'mobile': '📱', 'smartphone': '📱',
        'computer': '💻', 'laptop': '💻', 'pc': '💻',
        'car': '🚗', 'auto': '🚗', 'automobile': '🚗',
        'house': '🏠', 'home': '🏠', 'building': '🏢',
        'food': '🍔', 'eat': '🍽️', 'eating': '🍽️', 'meal': '🍽️',
        'pizza': '🍕', 'burger': '🍔', 'fries': '🍟',
        'coffee': '☕', 'tea': '🍵', 'drink': '🥤', 'drinking': '🥤',
        'water': '💧', 'rain': '🌧️', 'raining': '🌧️',
        'sun': '☀️', 'sunny': '☀️', 'sunshine': '☀️',
        'moon': '🌙', 'night': '🌙', 'dark': '🌙',
        'star': '⭐', 'stars': '⭐',
        'cloud': '☁️', 'clouds': '☁️', 'cloudy': '☁️',
        'flower': '🌸', 'flowers': '🌸', 'rose': '🌹',
        'tree': '🌳', 'trees': '🌳', 'nature': '🌳',
        'money': '💰', 'cash': '💰', 'dollar': '💵', 'rich': '💰',
        'gift': '🎁', 'present': '🎁', 'gifts': '🎁',
        'ball': '⚽', 'football': '⚽', 'soccer': '⚽',
        'music': '🎵', 'song': '🎵', 'songs': '🎵', 'musical': '🎵',
        'movie': '🎬', 'film': '🎬', 'cinema': '🎬',
        'book': '📚', 'books': '📚', 'reading': '📖', 'read': '📖',
        'camera': '📷', 'photo': '📷', 'picture': '📷',
        'video': '📹', 'tv': '📺', 'television': '📺',
        'game': '🎮', 'gaming': '🎮', 'games': '🎮',
        'balloon': '🎈', 'balloons': '🎈',
        'rocket': '🚀', 'space': '🚀',
        'plane': '✈️', 'airplane': '✈️', 'flight': '✈️',
        'train': '🚂', 'bike': '🚲', 'bicycle': '🚲',
        'bus': '🚌', 'taxi': '🚕',
        'ship': '🚢', 'boat': '⛵',
        'umbrella': '☂️', 'rain': '🌧️',
        'clock': '🕐', 'time': '🕐', 'watch': '⌚',
        'calendar': '📅', 'date': '📅',
        'key': '🔑', 'keys': '🔑', 'lock': '🔒',
        'light': '💡', 'bulb': '💡', 'idea': '💡',
        'fire': '🔥', 'flame': '🔥',
        'thunder': '⚡', 'lightning': '⚡',
        'snow': '❄️', 'snowflake': '❄️', 'winter': '❄️',
        'beach': '🏖️', 'ocean': '🌊', 'sea': '🌊', 'wave': '🌊',
        
        # Animals
        'dog': '🐶', 'puppy': '🐶', 'dogs': '🐶',
        'cat': '🐱', 'kitten': '🐱', 'cats': '🐱',
        'bird': '🐦', 'birds': '🐦',
        'fish': '🐟', 'fishes': '🐟',
        'lion': '🦁', 'tiger': '🐯',
        'bear': '🐻', 'panda': '🐼',
        'rabbit': '🐰', 'bunny': '🐰',
        'monkey': '🐵', 'ape': '🐵',
        'elephant': '🐘', 'cow': '🐄',
        'horse': '🐴', 'pig': '🐷',
        'chicken': '🐔', 'rooster': '🐔',
        'duck': '🦆', 'owl': '🦉',
        'bee': '🐝', 'bug': '🐛',
        'butterfly': '🦋', 'spider': '🕷️',
        'snake': '🐍', 'dragon': '🐉',
        
        # People & Actions
        'man': '👨', 'boy': '👦', 'male': '👨',
        'woman': '👩', 'girl': '👧', 'female': '👩',
        'baby': '👶', 'child': '👶', 'kid': '👶',
        'person': '👤', 'people': '👥',
        'family': '👨‍👩‍👧‍👦', 'parents': '👨‍👩‍👧‍👦',
        'friend': '👫', 'friends': '👫',
        'hand': '✋', 'hands': '✋',
        'wave': '👋', 'waving': '👋', 'hi': '👋', 'hello': '👋',
        'clap': '👏', 'clapping': '👏', 'applause': '👏',
        'point': '👆', 'pointing': '👆',
        'ok': '👌', 'okay': '👌',
        'victory': '✌️', 'peace': '✌️', 'win': '✌️',
        'fist': '✊', 'punch': '✊', 'power': '✊',
        'pray': '🙏', 'praying': '🙏', 'please': '🙏',
        'muscle': '💪', 'strong': '💪', 'power': '💪',
        'run': '🏃', 'running': '🏃',
        'walk': '🚶', 'walking': '🚶',
        'dance': '💃', 'dancing': '💃',
        'sing': '🎤', 'singing': '🎤', 'microphone': '🎤',
        'work': '💼', 'office': '💼', 'business': '💼',
        'study': '📚', 'studying': '📚', 'student': '📚',
        'teacher': '👨‍🏫', 'school': '🏫',
        'doctor': '👨‍⚕️', 'hospital': '🏥', 'medicine': '💊',
        'police': '👮', 'cop': '👮', 'security': '👮',
        'cook': '👨‍🍳', 'chef': '👨‍🍳', 'kitchen': '👨‍🍳',
        
        # Time & Days
        'today': '📅', 'tomorrow': '📅', 'yesterday': '📅',
        'monday': '📅', 'tuesday': '📅', 'wednesday': '📅',
        'thursday': '📅', 'friday': '📅', 'saturday': '📅', 'sunday': '📅',
        'morning': '🌅', 'dawn': '🌅',
        'noon': '☀️', 'afternoon': '☀️',
        'evening': '🌆', 'sunset': '🌆',
        'night': '🌙', 'midnight': '🌙',
        
        # Colors
        'red': '❤️', 'blue': '💙', 'green': '💚',
        'yellow': '💛', 'orange': '🧡', 'purple': '💜',
        'black': '⬛', 'white': '⬜',
        
        # Common expressions
        'yes': '✅', 'yep': '✅', 'yeah': '✅', 'ok': '✅',
        'no': '❌', 'nope': '❌', 'nah': '❌',
        'maybe': '🤷', 'perhaps': '🤷',
        'thanks': '🙏', 'thank': '🙏', 'thank you': '🙏',
        'welcome': '👋', 'hi': '👋', 'hello': '👋',
        'bye': '👋', 'goodbye': '👋', 'see you': '👋',
        'congratulations': '🎉', 'congrats': '🎉',
        'good luck': '🍀', 'luck': '🍀', 'lucky': '🍀',
        'good': '👍', 'great': '👍', 'excellent': '👍',
        'bad': '👎', 'terrible': '👎',
        'best': '⭐', 'awesome': '⭐',
        'new': '🆕', 'news': '📰',
        'free': '🆓',
        'up': '⬆️', 'down': '⬇️', 'left': '⬅️', 'right': '➡️',
        'top': '⬆️', 'bottom': '⬇️',
        'next': '➡️', 'previous': '⬅️',
        'here': '📍', 'location': '📍', 'place': '📍',
        'search': '🔍', 'find': '🔍', 'looking': '🔍',
        'eye': '👁️', 'eyes': '👁️', 'see': '👁️',
        'ear': '👂', 'ears': '👂', 'listen': '👂',
        'mouth': '👄', 'lip': '👄', 'speak': '👄', 'talk': '👄',
        'nose': '👃', 'smell': '👃',
        
        # Food & Drinks (Expanded)
        'apple': '🍎', 'apples': '🍎', 'red apple': '🍎',
        'banana': '🍌', 'bananas': '🍌',
        'orange': '🍊', 'oranges': '🍊', 'tangerine': '🍊',
        'strawberry': '🍓', 'strawberries': '🍓', 'berry': '🍓',
        'grape': '🍇', 'grapes': '🍇',
        'watermelon': '🍉', 'melon': '🍉',
        'cherry': '🍒', 'cherries': '🍒',
        'peach': '🍑', 'peaches': '🍑',
        'mango': '🥭', 'mangos': '🥭',
        'pineapple': '🍍', 'pineapples': '🍍',
        'coconut': '🥥', 'coconuts': '🥥',
        'kiwi': '🥝', 'kiwis': '🥝',
        'lemon': '🍋', 'lemons': '🍋',
        'tomato': '🍅', 'tomatoes': '🍅',
        'eggplant': '🍆', 'aubergine': '🍆',
        'corn': '🌽', 'maize': '🌽',
        'bread': '🍞', 'toast': '🍞',
        'baguette': '🥖', 'french bread': '🥖',
        'pretzel': '🥨', 'pretzels': '🥨',
        'croissant': '🥐', 'croissants': '🥐',
        'cheese': '🧀', 'cheeses': '🧀',
        'meat': '🥩', 'steak': '🥩', 'beef': '🥩',
        'chicken': '🍗', 'drumstick': '🍗',
        'bacon': '🥓', 'pork': '🥓',
        'hotdog': '🌭', 'hot dog': '🌭', 'sausage': '🌭',
        'taco': '🌮', 'tacos': '🌮',
        'burrito': '🌯', 'burritos': '🌯',
        'sandwich': '🥪', 'sandwiches': '🥪',
        'salad': '🥗', 'salads': '🥗', 'green salad': '🥗',
        'popcorn': '🍿', 'corn': '🍿',
        'butter': '🧈', 'margarine': '🧈',
        'salt': '🧂', 'salt shaker': '🧂',
        'canned food': '🥫', 'can': '🥫',
        'bento': '🍱', 'bento box': '🍱', 'lunch box': '🍱',
        'rice': '🍚', 'cooked rice': '🍚',
        'curry': '🍛', 'curry rice': '🍛',
        'ramen': '🍜', 'noodles': '🍜', 'noodle': '🍜',
        'spaghetti': '🍝', 'pasta': '🍝',
        'sushi': '🍣', 'sashimi': '🍣',
        'dango': '🍡', 'sweet dumpling': '🍡',
        'oden': '🍢', 'skewer': '🍢',
        'shrimp': '🦐', 'prawn': '🦐',
        'crab': '🦀', 'crabs': '🦀',
        'lobster': '🦞', 'lobsters': '🦞',
        'oyster': '🦪', 'oysters': '🦪',
        'fried shrimp': '🍤', 'tempura': '🍤',
        'fish cake': '🍥', 'naruto': '🍥',
        'moon cake': '🥮', 'mooncake': '🥮',
        'dumpling': '🥟', 'dumplings': '🥟',
        'fortune cookie': '🥠', 'cookie': '🥠',
        'takeout box': '🥡', 'takeaway': '🥡',
        'soft ice cream': '🍦', 'soft serve': '🍦',
        'shaved ice': '🍧', 'ice': '🍧',
        'ice cream': '🍨', 'icecream': '🍨',
        'doughnut': '🍩', 'donut': '🍩',
        'cookie': '🍪', 'cookies': '🍪',
        'birthday cake': '🎂', 'celebration cake': '🎂',
        'shortcake': '🍰', 'cake': '🍰',
        'cupcake': '🧁', 'cupcakes': '🧁',
        'pie': '🥧', 'pies': '🥧',
        'chocolate': '🍫', 'chocolate bar': '🍫',
        'candy': '🍬', 'sweet': '🍬', 'sweets': '🍬',
        'lollipop': '🍭', 'lolly': '🍭',
        'custard': '🍮', 'pudding': '🍮',
        'honey': '🍯', 'honey pot': '🍯',
        'baby bottle': '🍼', 'milk': '🍼',
        'glass of milk': '🥛', 'milk glass': '🥛',
        'drinking glass': '🥛', 'glass': '🥛',
        'tumbler': '🥃', 'whiskey': '🥃',
        'clinking glasses': '🥂', 'cheers': '🥂',
        'champagne': '🍾', 'bottle': '🍾',
        'wine': '🍷', 'wine glass': '🍷',
        'cocktail': '🍸', 'cocktails': '🍸',
        'tropical drink': '🍹', 'pina colada': '🍹',
        'beer': '🍺', 'beer mug': '🍺',
        'clinking beer mugs': '🍻', 'cheers beer': '🍻',
        'baby bottle': '🍼', 'formula': '🍼',
        'spoon': '🥄', 'spoons': '🥄',
        'fork and knife': '🍴', 'fork': '🍴', 'knife': '🍴',
        'chopsticks': '🥢', 'chopstick': '🥢',
        'bowl': '🥣', 'bowls': '🥣',
        'amphora': '🏺', 'vase': '🏺',
        
        # Sports & Activities
        'soccer': '⚽', 'football': '⚽', 'soccer ball': '⚽',
        'basketball': '🏀', 'basket': '🏀',
        'american football': '🏈', 'football': '🏈',
        'baseball': '⚾', 'baseball bat': '⚾',
        'tennis': '🎾', 'tennis ball': '🎾',
        'volleyball': '🏐', 'volley': '🏐',
        'rugby': '🏉', 'rugby football': '🏉',
        'ping pong': '🏓', 'table tennis': '🏓',
        'badminton': '🏸', 'shuttlecock': '🏸',
        'goal': '🥅', 'net': '🥅',
        'ice hockey': '🏒', 'hockey': '🏒',
        'field hockey': '🏑', 'field hockey stick': '🏑',
        'lacrosse': '🥍', 'lacrosse stick': '🥍',
        'skis': '🎿', 'skiing': '🎿', 'ski': '🎿',
        'sled': '🛷', 'sledge': '🛷',
        'curling stone': '🥌', 'curling': '🥌',
        'dart': '🎯', 'target': '🎯', 'darts': '🎯',
        'yo-yo': '🪀', 'yoyo': '🪀',
        'kite': '🪁', 'kites': '🪁',
        '8ball': '🎱', 'pool': '🎱', 'billiards': '🎱',
        'crystal ball': '🔮', 'magic': '🔮',
        'magic wand': '🪄', 'wand': '🪄',
        'video game': '🎮', 'controller': '🎮',
        'joystick': '🕹️', 'game controller': '🕹️',
        'slot machine': '🎰', 'casino': '🎰',
        'game die': '🎲', 'dice': '🎲', 'die': '🎲',
        'puzzle piece': '🧩', 'puzzle': '🧩',
        'teddy bear': '🧸', 'teddy': '🧸', 'bear toy': '🧸',
        'pinata': '🪅', 'pinata': '🪅',
        'nesting dolls': '🪆', 'matryoshka': '🪆',
        'spade suit': '♠️', 'spades': '♠️',
        'heart suit': '♥️', 'hearts': '♥️',
        'diamond suit': '♦️', 'diamonds': '♦️',
        'club suit': '♣️', 'clubs': '♣️',
        'chess pawn': '♟️', 'chess': '♟️',
        'joker': '🃏', 'joker card': '🃏',
        'mahjong': '🀄', 'mahjong red dragon': '🀄',
        'flower cards': '🎴', 'flower playing cards': '🎴',
        'performing arts': '🎭', 'theater': '🎭', 'theatre': '🎭',
        'framed picture': '🖼️', 'frame': '🖼️', 'picture frame': '🖼️',
        'art': '🎨', 'artist': '🎨', 'palette': '🎨',
        'thread': '🧵', 'threads': '🧵',
        'sewing needle': '🪡', 'needle': '🪡',
        'yarn': '🧶', 'ball of yarn': '🧶',
        'knot': '🪢', 'rope': '🪢',
        'goggles': '🥽', 'safety glasses': '🥽',
        'lab coat': '🥼', 'doctor coat': '🥼',
        'safety vest': '🦺', 'vest': '🦺',
        'necktie': '👔', 'tie': '👔',
        'shirt': '👕', 'tshirt': '👕', 't-shirt': '👕',
        'jeans': '👖', 'jean': '👖',
        'scarf': '🧣', 'scarves': '🧣',
        'gloves': '🧤', 'glove': '🧤',
        'coat': '🧥', 'jacket': '🧥',
        'socks': '🧦', 'sock': '🧦',
        'dress': '👗', 'dresses': '👗',
        'kimono': '👘', 'kimonos': '👘',
        'sari': '🥻', 'saris': '🥻',
        'one-piece swimsuit': '🩱', 'swimsuit': '🩱',
        'briefs': '🩲', 'underwear': '🩲',
        'shorts': '🩳', 'short': '🩳',
        'bikini': '👙', 'bikinis': '👙',
        'womans clothes': '👚', 'womens clothes': '👚',
        'purse': '👛', 'handbag': '👛',
        'clutch bag': '👜', 'handbag': '👜',
        'shopping bags': '🛍️', 'shopping': '🛍️',
        'backpack': '🎒', 'schoolbag': '🎒', 'bag': '🎒',
        'thong sandal': '🩴', 'sandal': '🩴',
        'mans shoe': '👞', 'shoe': '👞', 'shoes': '👞',
        'athletic shoe': '👟', 'sneaker': '👟', 'sneakers': '👟',
        'hiking boot': '🥾', 'boot': '🥾', 'boots': '🥾',
        'flat shoe': '🥿', 'ballet flat': '🥿',
        'high heel': '👠', 'high heels': '👠', 'heels': '👠',
        'sandal': '👡', 'sandals': '👡',
        'ballet shoes': '🩰', 'ballet': '🩰',
        'womans boot': '👢', 'boot': '👢',
        'crown': '👑', 'royal': '👑', 'king': '👑', 'queen': '👑',
        'womans hat': '👒', 'hat': '👒', 'hats': '👒',
        'top hat': '🎩', 'tophat': '🎩',
        'graduation cap': '🎓', 'graduation': '🎓', 'degree': '🎓',
        'billed cap': '🧢', 'cap': '🧢', 'baseball cap': '🧢',
        'military helmet': '🪖', 'helmet': '🪖',
        'rescue workers helmet': '⛑️', 'hard hat': '⛑️',
        'prayer beads': '📿', 'rosary': '📿',
        'lipstick': '💄', 'makeup': '💄',
        'ring': '💍', 'rings': '💍', 'wedding ring': '💍',
        'gem': '💎', 'diamond': '💎', 'gems': '💎',
        'muted speaker': '🔇', 'mute': '🔇',
        'speaker low volume': '🔈', 'speaker': '🔈',
        'speaker medium volume': '🔉', 'volume': '🔉',
        'speaker high volume': '🔊', 'loud': '🔊',
        'loudspeaker': '📢', 'megaphone': '📢',
        'megaphone': '📣', 'megaphone': '📣',
        'postal horn': '📯', 'horn': '📯',
        'bell': '🔔', 'bells': '🔔',
        'bell with slash': '🔕', 'no bell': '🔕',
        'musical score': '🎼', 'music score': '🎼',
        'musical note': '🎵', 'note': '🎵',
        'musical notes': '🎶', 'notes': '🎶',
        'studio microphone': '🎙️', 'mic': '🎙️',
        'level slider': '🎚️', 'slider': '🎚️',
        'control knobs': '🎛️', 'knobs': '🎛️',
        'radio': '📻', 'radios': '📻',
        'saxophone': '🎷', 'sax': '🎷',
        'accordion': '🪗', 'accordions': '🪗',
        'guitar': '🎸', 'guitars': '🎸',
        'musical keyboard': '🎹', 'piano': '🎹', 'keyboard': '🎹',
        'trumpet': '🎺', 'trumpets': '🎺',
        'violin': '🎻', 'violins': '🎻',
        'banjo': '🪕', 'banjos': '🪕',
        'drum': '🥁', 'drums': '🥁',
        'long drum': '🪘', 'long drums': '🪘',
        'mobile phone': '📱', 'cellphone': '📱',
        'mobile phone with arrow': '📲', 'call': '📲',
        'telephone': '☎️', 'phone': '☎️',
        'telephone receiver': '📞', 'phone receiver': '📞',
        'pager': '📟', 'pagers': '📟',
        'fax machine': '📠', 'fax': '📠',
        'battery': '🔋', 'batteries': '🔋',
        'electric plug': '🔌', 'plug': '🔌',
        'laptop': '💻', 'notebook': '💻',
        'desktop computer': '🖥️', 'desktop': '🖥️',
        'printer': '🖨️', 'printers': '🖨️',
        'keyboard': '⌨️', 'keyboards': '⌨️',
        'computer mouse': '🖱️', 'mouse': '🖱️',
        'trackball': '🖲️', 'trackballs': '🖲️',
        'computer disk': '💽', 'minidisc': '💽',
        'floppy disk': '💾', 'disk': '💾',
        'optical disk': '💿', 'cd': '💿', 'dvd': '💿',
        'dvd': '📀', 'dvd disk': '📀',
        'abacus': '🧮', 'calculator': '🧮',
        'movie camera': '🎥', 'video camera': '🎥',
        'film frames': '🎞️', 'film': '🎞️',
        'film projector': '📽️', 'projector': '📽️',
        'clapper board': '🎬', 'clapper': '🎬',
        'television': '📺', 'tv': '📺',
        'camera': '📷', 'photo camera': '📷',
        'camera with flash': '📸', 'camera flash': '📸',
        'video camera': '📹', 'camcorder': '📹',
        'videocassette': '📼', 'vhs': '📼',
        'magnifying glass tilted left': '🔍', 'search': '🔍',
        'magnifying glass tilted right': '🔎', 'zoom': '🔎',
        'candle': '🕯️', 'candles': '🕯️',
        'light bulb': '💡', 'lightbulb': '💡',
        'flashlight': '🔦', 'torch': '🔦',
        'red paper lantern': '🏮', 'lantern': '🏮',
        'diya lamp': '🪔', 'lamp': '🪔',
        'notebook with decorative cover': '📔', 'notebook': '📔',
        'closed book': '📕', 'book': '📕',
        'open book': '📖', 'reading book': '📖',
        'green book': '📗', 'books': '📗',
        'blue book': '📘', 'book': '📘',
        'orange book': '📙', 'book': '📙',
        'books': '📚', 'library': '📚',
        'notebook': '📓', 'notebooks': '📓',
        'ledger': '📒', 'account book': '📒',
        'page with curl': '📃', 'page': '📃',
        'scroll': '📜', 'scrolls': '📜',
        'page facing up': '📄', 'document': '📄',
        'newspaper': '📰', 'news': '📰',
        'rolled-up newspaper': '🗞️', 'newspaper roll': '🗞️',
        'bookmark tabs': '📑', 'bookmarks': '📑',
        'bookmark': '🔖', 'bookmarks': '🔖',
        'label': '🏷️', 'labels': '🏷️',
        'money bag': '💰', 'money': '💰',
        'yen banknote': '💴', 'yen': '💴',
        'dollar banknote': '💵', 'dollar': '💵',
        'euro banknote': '💶', 'euro': '💶',
        'pound banknote': '💷', 'pound': '💷',
        'money with wings': '💸', 'flying money': '💸',
        'credit card': '💳', 'card': '💳',
        'receipt': '🧾', 'receipts': '🧾',
        'chart increasing with yen': '💹', 'chart': '💹',
        'envelope': '✉️', 'mail': '✉️',
        'e-mail': '📧', 'email': '📧',
        'incoming envelope': '📨', 'incoming mail': '📨',
        'envelope with arrow': '📩', 'outgoing envelope': '📩',
        'outbox tray': '📤', 'outbox': '📤',
        'inbox tray': '📥', 'inbox': '📥',
        'package': '📦', 'parcel': '📦',
        'closed mailbox with raised flag': '📫', 'mailbox': '📫',
        'closed mailbox with lowered flag': '📪', 'mailbox': '📪',
        'open mailbox with raised flag': '📬', 'mailbox': '📬',
        'open mailbox with lowered flag': '📭', 'mailbox': '📭',
        'postbox': '📮', 'mailbox': '📮',
        'ballot box with ballot': '🗳️', 'ballot': '🗳️',
        'pencil': '✏️', 'pencils': '✏️',
        'black nib': '✒️', 'pen': '✒️',
        'fountain pen': '🖋️', 'fountain': '🖋️',
        'pen': '🖊️', 'ballpoint pen': '🖊️',
        'paintbrush': '🖌️', 'brush': '🖌️',
        'crayon': '🖍️', 'crayons': '🖍️',
        'memo': '📝', 'note': '📝', 'notes': '📝',
        'briefcase': '💼', 'briefcases': '💼',
        'file folder': '📁', 'folder': '📁',
        'open file folder': '📂', 'open folder': '📂',
        'card index dividers': '🗂️', 'dividers': '🗂️',
        'calendar': '📅', 'calendars': '📅',
        'tear-off calendar': '📆', 'calendar tear': '📆',
        'spiral notepad': '🗒️', 'notepad': '🗒️',
        'spiral calendar': '🗓️', 'calendar spiral': '🗓️',
        'card index': '📇', 'card file': '📇',
        'chart increasing': '📈', 'chart up': '📈',
        'chart decreasing': '📉', 'chart down': '📉',
        'bar chart': '📊', 'graph': '📊',
        'clipboard': '📋', 'clipboards': '📋',
        'pushpin': '📌', 'pin': '📌',
        'round pushpin': '📍', 'location pin': '📍',
        'paperclip': '📎', 'clip': '📎',
        'linked paperclips': '🖇️', 'paperclip chain': '🖇️',
        'straight ruler': '📏', 'ruler': '📏',
        'triangular ruler': '📐', 'triangle ruler': '📐',
        'scissors': '✂️', 'scissor': '✂️',
        'card file box': '🗃️', 'file box': '🗃️',
        'file cabinet': '🗄️', 'cabinet': '🗄️',
        'wastebasket': '🗑️', 'trash': '🗑️', 'garbage': '🗑️',
        'locked': '🔒', 'lock': '🔒',
        'unlocked': '🔓', 'unlock': '🔓',
        'locked with pen': '🔏', 'locked pen': '🔏',
        'locked with key': '🔐', 'locked key': '🔐',
        'key': '🔑', 'keys': '🔑',
        'old key': '🗝️', 'antique key': '🗝️',
        'hammer': '🔨', 'hammers': '🔨',
        'axe': '🪓', 'ax': '🪓',
        'pick': '⛏️', 'mining pick': '⛏️',
        'hammer and pick': '⚒️', 'hammer pick': '⚒️',
        'hammer and wrench': '🛠️', 'tools': '🛠️',
        'dagger': '🗡️', 'knife': '🗡️',
        'crossed swords': '⚔️', 'swords': '⚔️',
        'water pistol': '🔫', 'gun': '🔫',
        'boomerang': '🪃', 'boomerangs': '🪃',
        'bow and arrow': '🏹', 'archery': '🏹',
        'shield': '🛡️', 'shields': '🛡️',
        'carpentry saw': '🪚', 'saw': '🪚',
        'wrench': '🔧', 'wrenches': '🔧',
        'screwdriver': '🪛', 'screw driver': '🪛',
        'nut and bolt': '🔩', 'bolt': '🔩',
        'gear': '⚙️', 'cog': '⚙️',
        'clamp': '🗜️', 'vice': '🗜️',
        'balance scale': '⚖️', 'scales': '⚖️',
        'white cane': '🦯', 'cane': '🦯',
        'link': '🔗', 'links': '🔗',
        'chains': '⛓️', 'chain': '⛓️',
        'hook': '🪝', 'hooks': '🪝',
        'toolbox': '🧰', 'tool box': '🧰',
        'magnet': '🧲', 'magnets': '🧲',
        'ladder': '🪜', 'ladders': '🪜',
        'alembic': '⚗️', 'chemistry': '⚗️',
        'test tube': '🧪', 'test tubes': '🧪',
        'petri dish': '🧫', 'petri': '🧫',
        'dna': '🧬', 'genetics': '🧬',
        'microscope': '🔬', 'microscopes': '🔬',
        'telescope': '🔭', 'telescopes': '🔭',
        'satellite antenna': '📡', 'satellite': '📡',
        'syringe': '💉', 'syringes': '💉',
        'drop of blood': '🩸', 'blood': '🩸',
        'pill': '💊', 'pills': '💊',
        'adhesive bandage': '🩹', 'bandage': '🩹',
        'stethoscope': '🩺', 'medical': '🩺',
        'door': '🚪', 'doors': '🚪',
        'elevator': '🛗', 'lift': '🛗',
        'mirror': '🪞', 'mirrors': '🪞',
        'window': '🪟', 'windows': '🪟',
        'bed': '🛏️', 'beds': '🛏️',
        'couch and lamp': '🛋️', 'sofa': '🛋️',
        'chair': '🪑', 'chairs': '🪑',
        'toilet': '🚽', 'toilets': '🚽',
        'plunger': '🪠', 'plungers': '🪠',
        'shower': '🚿', 'showers': '🚿',
        'bathtub': '🛁', 'bath': '🛁',
        'mouse trap': '🪤', 'trap': '🪤',
        'razor': '🪒', 'razors': '🪒',
        'lotion bottle': '🧴', 'bottle': '🧴',
        'safety pin': '🧷', 'safety pins': '🧷',
        'broom': '🧹', 'brooms': '🧹',
        'basket': '🧺', 'baskets': '🧺',
        'roll of paper': '🧻', 'toilet paper': '🧻',
        'bucket': '🪣', 'buckets': '🪣',
        'soap': '🧼', 'soaps': '🧼',
        'toothbrush': '🪥', 'brush': '🪥',
        'sponge': '🧽', 'sponges': '🧽',
        'fire extinguisher': '🧯', 'extinguisher': '🧯',
        'shopping cart': '🛒', 'cart': '🛒',
        'smoking': '🚬', 'cigarette': '🚬',
        'coffin': '⚰️', 'coffins': '⚰️',
        'headstone': '🪦', 'tombstone': '🪦',
        'moai': '🗿', 'statue': '🗿',
        'placard': '🪧', 'sign': '🪧',
        'atm sign': '🏧', 'atm': '🏧',
        'litter in bin sign': '🚮', 'litter': '🚮',
        'potable water': '🚰', 'water': '🚰',
        'wheelchair symbol': '♿', 'wheelchair': '♿',
        'mens room': '🚹', 'mens': '🚹',
        'womens room': '🚺', 'womens': '🚺',
        'restroom': '🚻', 'toilet': '🚻',
        'baby symbol': '🚼', 'baby': '🚼',
        'water closet': '🚾', 'wc': '🚾',
        'passport control': '🛂', 'passport': '🛂',
        'customs': '🛃', 'custom': '🛃',
        'baggage claim': '🛄', 'luggage': '🛄',
        'left luggage': '🛅', 'luggage': '🛅',
        'warning': '⚠️', 'warn': '⚠️',
        'children crossing': '🚸', 'children': '🚸',
        'no entry': '⛔', 'no entry sign': '⛔',
        'prohibited': '🚫', 'forbidden': '🚫',
        'no bicycles': '🚳', 'no bike': '🚳',
        'no smoking': '🚭', 'no smoke': '🚭',
        'no littering': '🚯', 'no litter': '🚯',
        'non-potable water': '🚱', 'no water': '🚱',
        'no pedestrians': '🚷', 'no walking': '🚷',
        'no mobile phones': '📵', 'no phones': '📵',
        'no one under eighteen': '🔞', '18+': '🔞',
        'radioactive': '☢️', 'radiation': '☢️',
        'biohazard': '☣️', 'bio hazard': '☣️',
        'up arrow': '⬆️', 'up': '⬆️',
        'up-right arrow': '↗️', 'up right': '↗️',
        'right arrow': '➡️', 'right': '➡️',
        'down-right arrow': '↘️', 'down right': '↘️',
        'down arrow': '⬇️', 'down': '⬇️',
        'down-left arrow': '↙️', 'down left': '↙️',
        'left arrow': '⬅️', 'left': '⬅️',
        'up-left arrow': '↖️', 'up left': '↖️',
        'up-down arrow': '↕️', 'up down': '↕️',
        'left-right arrow': '↔️', 'left right': '↔️',
        'right arrow curving left': '↩️', 'return': '↩️',
        'left arrow curving right': '↪️', 'back': '↪️',
        'right arrow curving up': '⤴️', 'curve up': '⤴️',
        'right arrow curving down': '⤵️', 'curve down': '⤵️',
        'clockwise vertical arrows': '🔃', 'refresh': '🔃',
        'counterclockwise arrows button': '🔄', 'counterclockwise': '🔄',
        'back arrow': '🔙', 'return': '🔙',
        'end arrow': '🔚', 'end': '🔚',
        'on arrow': '🔛', 'on': '🔛',
        'soon arrow': '🔜', 'soon': '🔜',
        'top arrow': '🔝', 'top': '🔝',
        'place of worship': '🛐', 'worship': '🛐',
        'atom symbol': '⚛️', 'atom': '⚛️',
        'om': '🕉️', 'hindu': '🕉️',
        'star of david': '✡️', 'david': '✡️',
        'wheel of dharma': '☸️', 'dharma': '☸️',
        'yin yang': '☯️', 'yin yang': '☯️',
        'latin cross': '✝️', 'cross': '✝️',
        'orthodox cross': '☦️', 'orthodox': '☦️',
        'star and crescent': '☪️', 'islam': '☪️',
        'peace symbol': '☮️', 'peace': '☮️',
        'menorah': '🕎', 'hanukkah': '🕎',
        'dotted six-pointed star': '🔯', 'star': '🔯',
        'khanda': '🪯', 'khanda': '🪯',
        'aries': '♈', 'zodiac': '♈',
        'taurus': '♉', 'bull': '♉',
        'gemini': '♊', 'twins': '♊',
        'cancer': '♋', 'crab': '♋',
        'leo': '♌', 'lion': '♌',
        'virgo': '♍', 'virgin': '♍',
        'libra': '♎', 'scales': '♎',
        'scorpio': '♏', 'scorpion': '♏',
        'sagittarius': '♐', 'archer': '♐',
        'capricorn': '♑', 'goat': '♑',
        'aquarius': '♒', 'water bearer': '♒',
        'pisces': '♓', 'fish': '♓',
        'ophiuchus': '⛎', 'snake bearer': '⛎',
        'shuffle tracks button': '🔀', 'shuffle': '🔀',
        'repeat button': '🔁', 'repeat': '🔁',
        'repeat single button': '🔂', 'repeat one': '🔂',
        'play button': '▶️', 'play': '▶️',
        'fast-forward button': '⏩', 'fast forward': '⏩',
        'next track button': '⏭️', 'next': '⏭️',
        'play or pause button': '⏯️', 'play pause': '⏯️',
        'reverse button': '⏪', 'reverse': '⏪',
        'fast reverse button': '⏮️', 'fast reverse': '⏮️',
        'upwards button': '🔼', 'up button': '🔼',
        'fast up button': '⏫', 'fast up': '⏫',
        'downwards button': '🔽', 'down button': '🔽',
        'fast down button': '⏬', 'fast down': '⏬',
        'pause button': '⏸️', 'pause': '⏸️',
        'stop button': '⏹️', 'stop': '⏹️',
        'record button': '⏺️', 'record': '⏺️',
        'eject button': '⏏️', 'eject': '⏏️',
        'cinema': '🎦', 'movie': '🎦',
        'dim button': '🔅', 'dim': '🔅',
        'bright button': '🔆', 'bright': '🔆',
        'antenna bars': '📶', 'signal': '📶',
        'vibration mode': '📳', 'vibrate': '📳',
        'mobile phone off': '📴', 'phone off': '📴',
        'female sign': '♀️', 'female': '♀️',
        'male sign': '♂️', 'male': '♂️',
        'transgender symbol': '⚧️', 'transgender': '⚧️',
        'multiply': '✖️', 'times': '✖️',
        'plus': '➕', 'add': '➕',
        'minus': '➖', 'subtract': '➖',
        'divide': '➗', 'division': '➗',
        'infinity': '♾️', 'infinite': '♾️',
        'double exclamation mark': '‼️', 'exclamation': '‼️',
        'exclamation question mark': '⁉️', 'exclamation question': '⁉️',
        'red question mark': '❓', 'question': '❓',
        'white question mark': '❔', 'question white': '❔',
        'white exclamation mark': '❕', 'exclamation white': '❕',
        'red exclamation mark': '❗', 'exclamation red': '❗',
        'wavy dash': '〰️', 'wavy': '〰️',
        'currency exchange': '💱', 'exchange': '💱',
        'heavy dollar sign': '💲', 'dollar sign': '💲',
        'medical symbol': '⚕️', 'medical': '⚕️',
        'recycling symbol': '♻️', 'recycle': '♻️',
        'fleur-de-lis': '⚜️', 'fleur': '⚜️',
        'trident emblem': '🔱', 'trident': '🔱',
        'name badge': '📛', 'badge': '📛',
        'japanese symbol for beginner': '🔰', 'beginner': '🔰',
        'hollow red circle': '⭕', 'red circle': '⭕',
        'check mark button': '✅', 'check': '✅',
        'check box with check': '☑️', 'checkbox': '☑️',
        'check mark': '✔️', 'checkmark': '✔️',
        'cross mark': '❌', 'x': '❌',
        'cross mark button': '❎', 'x button': '❎',
        'curly loop': '➰', 'loop': '➰',
        'double curly loop': '➿', 'double loop': '➿',
        'part alternation mark': '〽️', 'part': '〽️',
        'eight-pointed star': '✳️', 'star': '✳️',
        'eight-spoked asterisk': '✴️', 'asterisk': '✴️',
        'sparkle': '❇️', 'sparkles': '❇️',
        'copyright': '©️', 'copyright symbol': '©️',
        'registered': '®️', 'registered symbol': '®️',
        'trade mark': '™️', 'trademark': '™️',
        'keycap': '#️⃣', 'hash': '#️⃣',
        'keycap 0': '0️⃣', 'zero': '0️⃣',
        'keycap 1': '1️⃣', 'one': '1️⃣',
        'keycap 2': '2️⃣', 'two': '2️⃣',
        'keycap 3': '3️⃣', 'three': '3️⃣',
        'keycap 4': '4️⃣', 'four': '4️⃣',
        'keycap 5': '5️⃣', 'five': '5️⃣',
        'keycap 6': '6️⃣', 'six': '6️⃣',
        'keycap 7': '7️⃣', 'seven': '7️⃣',
        'keycap 8': '8️⃣', 'eight': '8️⃣',
        'keycap 9': '9️⃣', 'nine': '9️⃣',
        'keycap 10': '🔟', 'ten': '🔟',
        'input latin uppercase': '🔠', 'uppercase': '🔠',
        'input latin lowercase': '🔡', 'lowercase': '🔡',
        'input numbers': '🔢', 'numbers': '🔢',
        'input symbols': '🔣', 'symbols': '🔣',
        'input latin letters': '🔤', 'letters': '🔤',
        'a button (blood type)': '🅰️', 'a': '🅰️',
        'ab button (blood type)': '🆎', 'ab': '🆎',
        'b button (blood type)': '🅱️', 'b': '🅱️',
        'cl button': '🆑', 'clear': '🆑',
        'cool button': '🆒', 'cool': '🆒',
        'free button': '🆓', 'free': '🆓',
        'information': 'ℹ️', 'info': 'ℹ️',
        'id button': '🆔', 'id': '🆔',
        'circled m': 'Ⓜ️', 'm': 'Ⓜ️',
        'new button': '🆕', 'new': '🆕',
        'ng button': '🆖', 'ng': '🆖',
        'o button (blood type)': '🅾️', 'o': '🅾️',
        'ok button': '🆗', 'ok': '🆗',
        'p button': '🅿️', 'p': '🅿️',
        'sos button': '🆘', 'sos': '🆘',
        'up button': '🆙', 'up': '🆙',
        'vs button': '🆚', 'vs': '🆚',
        'japanese here button': '🈁', 'here': '🈁',
        'japanese service charge button': '🈂️', 'service': '🈂️',
        'japanese monthly amount button': '🈷️', 'monthly': '🈷️',
        'japanese not free of charge button': '🈶', 'not free': '🈶',
        'japanese free of charge button': '🈚', 'free': '🈚',
        'japanese reserved button': '🈯', 'reserved': '🈯',
        'japanese bargain button': '🉐', 'bargain': '🉐',
        'japanese discount button': '🈹', 'discount': '🈹',
        'japanese no vacancy button': '🈵', 'no vacancy': '🈵',
        'japanese prohibited button': '🈲', 'prohibited': '🈲',
        'japanese acceptable button': '🉑', 'acceptable': '🉑',
        'japanese application button': '🈸', 'application': '🈸',
        'japanese passing grade button': '🈴', 'passing': '🈴',
        'japanese vacancy button': '🈳', 'vacancy': '🈳',
        'japanese congratulations button': '㊗️', 'congratulations': '㊗️',
        'japanese secret button': '㊙️', 'secret': '㊙️',
        'japanese open for business button': '🈺', 'open': '🈺',
        'japanese no vacancy button': '🈵', 'full': '🈵',
        'red circle': '🔴', 'red': '🔴',
        'orange circle': '🟠', 'orange': '🟠',
        'yellow circle': '🟡', 'yellow': '🟡',
        'green circle': '🟢', 'green': '🟢',
        'blue circle': '🔵', 'blue': '🔵',
        'purple circle': '🟣', 'purple': '🟣',
        'brown circle': '🟤', 'brown': '🟤',
        'black circle': '⚫', 'black': '⚫',
        'white circle': '⚪', 'white': '⚪',
        'red square': '🟥', 'red square': '🟥',
        'orange square': '🟧', 'orange square': '🟧',
        'yellow square': '🟨', 'yellow square': '🟨',
        'green square': '🟩', 'green square': '🟩',
        'blue square': '🟦', 'blue square': '🟦',
        'purple square': '🟪', 'purple square': '🟪',
        'brown square': '🟫', 'brown square': '🟫',
        'black large square': '⬛', 'black square': '⬛',
        'white large square': '⬜', 'white square': '⬜',
        'black medium square': '◼️', 'black medium': '◼️',
        'white medium square': '◻️', 'white medium': '◻️',
        'black medium-small square': '◾', 'black small': '◾',
        'white medium-small square': '◽', 'white small': '◽',
        'black small square': '▪️', 'black dot': '▪️',
        'white small square': '▫️', 'white dot': '▫️',
        'large orange diamond': '🔶', 'orange diamond': '🔶',
        'large blue diamond': '🔷', 'blue diamond': '🔷',
        'small orange diamond': '🔸', 'small orange': '🔸',
        'small blue diamond': '🔹', 'small blue': '🔹',
        'red triangle pointed up': '🔺', 'red triangle': '🔺',
        'red triangle pointed down': '🔻', 'red triangle down': '🔻',
        'diamond with a dot': '💠', 'diamond dot': '💠',
        'radio button': '🔘', 'radio': '🔘',
        'white square button': '🔳', 'square button': '🔳',
        'black square button': '🔲', 'square button black': '🔲',
    }
    
    # Convert text to lowercase for matching
    words = text.lower().split()
    result = []
    
    for word in words:
        # Remove punctuation for matching
        clean_word = word.strip('.,!?;:()[]{}"\'')
        
        # Check if word matches any emoji
        if clean_word in emoji_map:
            result.append(emoji_map[clean_word])
        else:
            # Keep original word if no emoji found
            result.append(word)
    
    return ' '.join(result)

async def texttoemoji_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert text words to emojis."""
    try:
        if not context.args or len(context.args) == 0:
            # Show help
            help_text = (
                "😊 **Text to Emoji Converter**\n\n"
                "**Usage:** `/texttoemoji <text>`\n\n"
                "**Convert words to emojis!**\n\n"
                "**Examples:**\n"
                "• `/texttoemoji happy birthday`\n"
                "  → 😊 🎂\n\n"
                "• `/texttoemoji I love pizza`\n"
                "  → I ❤️ 🍕\n\n"
                "• `/texttoemoji good morning coffee`\n"
                "  → 👍 🌅 ☕\n\n"
                "**Supported Words:**\n"
                "• Emotions: happy, sad, angry, love, like, etc.\n"
                "• Food & Drinks: apple, pizza, coffee, cake, etc.\n"
                "• Objects: phone, car, house, computer, etc.\n"
                "• Animals: dog, cat, bird, fish, etc.\n"
                "• Sports: soccer, basketball, tennis, etc.\n"
                "• Actions: run, dance, sing, work, etc.\n"
                "• Technology: laptop, phone, camera, etc.\n"
                "• Time: morning, night, today, etc.\n"
                "• Symbols & Signs: check, arrow, star, etc.\n"
                "• And 700+ more words!\n\n"
                "💡 **Tip:** Words that don't have emojis will stay as text.\n\n"
                "**Aliases:** `/emoji`, `/textemoji`, `/wordtoemoji`"
            )
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        text = ' '.join(context.args)
        
        if len(text) > 500:
            await update.message.reply_text(
                "❌ Text is too long! Please keep it under 500 characters."
            )
            return
        
        # Convert text to emoji
        emoji_text = text_to_emoji(text)
        
        # Build response
        response = "😊 **Text to Emoji**\n\n"
        response += f"**Original:**\n`{text}`\n\n"
        response += f"**With Emojis:**\n`{emoji_text}`\n\n"
        response += f"💡 Copy the emoji text above!"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Text to emoji command error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error converting text to emoji. Please try again.\n\n"
            "Usage: `/texttoemoji <text>`\n"
            "Example: `/texttoemoji happy birthday`",
            parse_mode='Markdown'
        )

async def mp4tomp3_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert MP4 video files to MP3 audio files."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    try:
        # Check if MoviePy is available
        if not MOVIEPY_AVAILABLE or VideoFileClip is None:
            await update.message.reply_text(
                "❌ **MoviePy Not Available**\n\n"
                "This feature requires MoviePy library.\n\n"
                "**To install:**\n"
                "```\n"
                "pip install moviepy\n"
                "```\n\n"
                "After installation, restart the bot to use this feature."
            )
            return
        
        # Check if user sent a video file
        if not update.message.video and not update.message.document:
            help_text = (
                "🎵 **MP4 to MP3 Converter**\n\n"
                "**Usage:** Send a video file (MP4) to convert it to MP3 audio.\n\n"
                "**How to use:**\n"
                "1. Send a video file (MP4 format)\n"
                "2. The bot will extract audio and convert to MP3\n"
                "3. You'll receive the MP3 file\n\n"
                "**Supported formats:**\n"
                "• MP4 videos\n"
                "• Other video formats (will be converted)\n\n"
                "**Limitations:**\n"
                "• Maximum file size: 50MB\n"
                "• Processing time depends on video length\n\n"
                "💡 **Tip:** Send the video file directly to this chat!"
            )
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        # Get video file
        video_file = None
        file_name = "video.mp4"
        
        if update.message.video:
            video_file = await context.bot.get_file(update.message.video.file_id)
            file_name = update.message.video.file_name or "video.mp4"
        elif update.message.document:
            # Check if document is a video
            mime_type = update.message.document.mime_type or ""
            if not mime_type.startswith('video/'):
                await update.message.reply_text(
                    "❌ Please send a video file (MP4, AVI, MOV, etc.)\n\n"
                    "The file you sent is not a video file."
                )
                return
            video_file = await context.bot.get_file(update.message.document.file_id)
            file_name = update.message.document.file_name or "video.mp4"
        
        if not video_file:
            await update.message.reply_text("❌ Could not get video file. Please try again.")
            return
        
        # Check file size (Telegram limit is ~50MB for downloads)
        file_size = video_file.file_size or 0
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(
                "❌ Video file is too large (>50MB).\n\n"
                "Please send a smaller video file (under 50MB)."
            )
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            "🎵 Converting video to MP3...\n"
            "⏳ This may take a moment depending on video length..."
        )
        
        try:
            # Get file path and bot token for download
            file_path = video_file.file_path
            bot_token = context.bot.token
            
            # Download video to temporary file
            loop = asyncio.get_event_loop()
            
            def convert_video_to_mp3():
                video_path = None
                audio_path = None
                try:
                    # Create temporary files
                    video_fd, video_path = tempfile.mkstemp(suffix='.mp4')
                    audio_fd, audio_path = tempfile.mkstemp(suffix='.mp3')
                    os.close(video_fd)
                    os.close(audio_fd)
                    
                    # Download video using requests
                    # Construct download URL
                    # file_path from Telegram API should be relative (e.g., "videos/file_18.mp4")
                    # But sometimes it might contain partial URL, so handle both cases
                    
                    # Get the actual file_path value (closure variable)
                    actual_file_path = file_path
                    
                    # Check if file_path already contains the full URL
                    if actual_file_path.startswith('https://api.telegram.org/file/bot'):
                        # Already contains full URL - extract just the path part
                        # Format: https://api.telegram.org/file/bot{token}/path
                        # Extract path after /file/bot{token}/
                        if f'/file/bot{bot_token}/' in actual_file_path:
                            # Extract path after token
                            path_part = actual_file_path.split(f'/file/bot{bot_token}/', 1)[-1]
                            download_url = f"https://api.telegram.org/file/bot{bot_token}/{path_part}"
                        else:
                            # Extract path after any /file/bot/ pattern
                            import re
                            match = re.search(r'/file/bot[^/]+/(.+)$', actual_file_path)
                            if match:
                                path_part = match.group(1)
                                download_url = f"https://api.telegram.org/file/bot{bot_token}/{path_part}"
                            else:
                                # Fallback: use as is
                                download_url = actual_file_path
                    elif actual_file_path.startswith('http://') or actual_file_path.startswith('https://'):
                        # Other HTTP URL - use as is
                        download_url = actual_file_path
                    else:
                        # Relative path - construct full URL
                        download_url = f"https://api.telegram.org/file/bot{bot_token}/{actual_file_path}"
                    
                    logger.info(f"Downloading video from: {download_url}")
                    
                    # Download file
                    response = requests.get(download_url, stream=True, timeout=60)
                    response.raise_for_status()
                    
                    with open(video_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # Convert to MP3
                    video_clip = VideoFileClip(video_path)
                    audio_clip = video_clip.audio
                    
                    if audio_clip is None:
                        raise Exception("Video has no audio track")
                    
                    # Write audio to file
                    audio_clip.write_audiofile(
                        audio_path,
                        codec='mp3',
                        bitrate='192k',
                        logger=None  # Suppress moviepy logs
                    )
                    
                    # Clean up
                    audio_clip.close()
                    video_clip.close()
                    
                    # Read audio file into memory
                    with open(audio_path, 'rb') as f:
                        audio_data = f.read()
                    
                    return audio_data
                    
                except Exception as e:
                    logger.error(f"Video to MP3 conversion error: {e}", exc_info=True)
                    raise
                finally:
                    # Clean up temporary files
                    try:
                        if video_path and os.path.exists(video_path):
                            os.unlink(video_path)
                        if audio_path and os.path.exists(audio_path):
                            os.unlink(audio_path)
                    except Exception as cleanup_error:
                        logger.warning(f"Error cleaning up temp files: {cleanup_error}")
            
            # Run conversion in executor
            audio_data = await loop.run_in_executor(None, convert_video_to_mp3)
            
            # Delete processing message
            try:
                await processing_msg.delete()
            except:
                pass
            
            # Create audio buffer
            audio_buffer = io.BytesIO(audio_data)
            audio_buffer.name = file_name.replace('.mp4', '.mp3').replace('.avi', '.mp3').replace('.mov', '.mp3') or "audio.mp3"
            
            # Send MP3 file
            await update.message.reply_audio(
                audio=audio_buffer,
                filename=audio_buffer.name,
                title="Converted Audio",
                performer="MP4 to MP3 Converter"
            )
            
            logger.info(f"Successfully converted video to MP3: {file_name}")
            
        except Exception as e:
            logger.error(f"MP4 to MP3 conversion error: {e}", exc_info=True)
            try:
                await processing_msg.delete()
            except:
                pass
            
            error_msg = str(e).lower()
            if "no audio" in error_msg or "audio track" in error_msg:
                await update.message.reply_text(
                    "❌ **No Audio Track Found**\n\n"
                    "This video file doesn't contain any audio.\n"
                    "Please send a video with audio."
                )
            elif "too large" in error_msg or "size" in error_msg:
                await update.message.reply_text(
                    "❌ **File Too Large**\n\n"
                    "The converted audio file is too large.\n"
                    "Please try with a shorter video."
                )
            else:
                await update.message.reply_text(
                    "❌ **Conversion Failed**\n\n"
                    f"Error: {str(e)}\n\n"
                    "**Possible reasons:**\n"
                    "• Video format not supported\n"
                    "• Video file is corrupted\n"
                    "• Video is too long\n\n"
                    "Please try again with a different video file."
                )
    
    except Exception as e:
        logger.error(f"MP4 to MP3 command error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error processing video. Please try again.\n\n"
            "Make sure you're sending a valid video file."
        )

async def fancyfont_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate fancy font styles from text."""
    try:
        if not context.args or len(context.args) < 2:
            # Show help with all font styles
            help_text = (
                "✨ **Fancy Font Generator**\n\n"
                "**Usage:** `/fancyfont <style> <text>`\n\n"
                "**Available Styles (13 types):**\n\n"
                "1️⃣ **Bold** - Bold text (𝐁𝐨𝐥𝐝)\n"
                "   `/fancyfont bold Hello`\n\n"
                "2️⃣ **Italic** - Italic text (𝑖𝑡𝑎𝑙𝑖𝑐)\n"
                "   `/fancyfont italic Hello`\n\n"
                "3️⃣ **Bold Italic** - Bold Italic (𝒃𝒐𝒍𝒅 𝒊𝒕𝒂𝒍𝒊𝒄)\n"
                "   `/fancyfont bolditalic Hello`\n\n"
                "4️⃣ **Monospace** - Monospace font (𝚖𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎)\n"
                "   `/fancyfont monospace Hello`\n\n"
                "5️⃣ **Script** - Script/Cursive (𝓈𝒸𝓇𝒾𝓅𝓉)\n"
                "   `/fancyfont script Hello`\n\n"
                "6️⃣ **Fraktur** - Fraktur/Gothic (𝔣𝔯𝔞𝔨𝔱𝔲𝔯)\n"
                "   `/fancyfont fraktur Hello`\n\n"
                "7️⃣ **Double-struck** - Double-struck (𝕕𝕠𝕦𝕓𝕝𝕖)\n"
                "   `/fancyfont doublestruck Hello`\n\n"
                "8️⃣ **Fullwidth** - Fullwidth (ｆｕｌｌｗｉｄｔｈ)\n"
                "   `/fancyfont fullwidth Hello`\n\n"
                "9️⃣ **Small Caps** - Small Caps (sᴍᴀʟʟ)\n"
                "   `/fancyfont smallcaps Hello`\n\n"
                "🔟 **Circled** - Circled letters (ⓒⓘⓡⓒⓛⓔⓓ)\n"
                "   `/fancyfont circled Hello`\n\n"
                "1️⃣1️⃣ **Squared** - Squared letters (🅂🅀🅄🄰🅁🄴🄳)\n"
                "   `/fancyfont squared Hello`\n\n"
                "1️⃣2️⃣ **Upside Down** - Upside down text (pɹɐʍ sʇuı)\n"
                "   `/fancyfont upsidedown Hello`\n\n"
                "💡 **Quick Examples:**\n"
                "• `/fancyfont bold Hello World`\n"
                "• `/fancyfont script Beautiful`\n"
                "• `/fancyfont upsidedown Hello`\n\n"
                "**Aliases:** `/font`, `/fancy`, `/textfont`"
            )
            await update.message.reply_text(help_text, parse_mode='Markdown')
            return
        
        style = context.args[0].lower()
        text = ' '.join(context.args[1:])
        
        if len(text) > 500:
            await update.message.reply_text(
                "❌ Text is too long! Please keep it under 500 characters."
            )
            return
        
        # Convert text to fancy font
        fancy_text = convert_to_fancy_font(text, style)
        
        # Build response
        response = f"✨ **Fancy Font - {style.upper()}**\n\n"
        response += f"**Original:**\n`{text}`\n\n"
        response += f"**Styled:**\n`{fancy_text}`\n\n"
        response += f"💡 Copy the styled text above!"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Fancy font command error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Error generating fancy font. Please try again.\n\n"
            "Usage: `/fancyfont <style> <text>`\n"
            "Example: `/fancyfont bold Hello World`",
            parse_mode='Markdown'
        )

async def removeduplicates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove duplicate lines from text."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Get text from message or reply
    text = ""
    
    # Priority 1: If reply to message, get text from replied message
    if update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        logger.info(f"Remove duplicates: Got text from reply, length: {len(text)}")
    # Priority 2: If command has arguments, use them (join with newlines to preserve line structure)
    elif context.args and len(context.args) > 0:
        # Join all arguments - if they contain \n, they'll be preserved
        text = "\n".join(context.args)
        logger.info(f"Remove duplicates: Got text from args, length: {len(text)}")
    # Priority 3: Try to get from current message text
    else:
        message_text = update.message.text or update.message.caption or ""
        logger.info(f"Remove duplicates: Message text: {message_text[:50]}...")
        
        # Skip if it's just the button text
        if message_text.strip() == "🔀 Remove Duplicates":
            await update.message.reply_text(
                "🔀 **Remove Duplicates**\n\n"
                "**Usage:**\n"
                "• Reply to a message with: `/removeduplicates`\n"
                "• Or send: `/removeduplicates line1\\nline2\\nline1`\n\n"
                "**Example:**\n"
                "Reply to a message containing:\n"
                "```\nline1\nline2\nline1\nline3\n```\n\n"
                "With: `/removeduplicates`",
                parse_mode='Markdown'
            )
            return
        
        # Remove command prefix if present
        if message_text.startswith('/removeduplicates') or message_text.startswith('/removedup') or message_text.startswith('/dedup') or message_text.startswith('/rmdup'):
            parts = message_text.split(' ', 1)
            if len(parts) > 1:
                text = parts[1]
            else:
                text = ""
        else:
            text = message_text
        logger.info(f"Remove duplicates: Final text length: {len(text)}")
    
    if not text or len(text.strip()) == 0:
        await update.message.reply_text(
            "❌ **Please provide text or reply to a message!**\n\n"
            "**Usage:**\n"
            "• `/removeduplicates` (reply to a message)\n"
            "• `/removeduplicates line1\nline2\nline1`\n"
            "• Or send text directly (without command)\n\n"
            "**Example:**\n"
            "Reply to a message with:\n"
            "`/removeduplicates`\n\n"
            "Or send:\n"
            "`/removeduplicates line1\nline2\nline1\nline3`\n\n"
            "**Output:**\n"
            "`line1\nline2\nline3`"
        )
        return
    
    try:
        # Split text into lines
        lines = text.split('\n')
        logger.info(f"Remove duplicates: Processing {len(lines)} lines")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_lines = []
        removed_count = 0
        
        for line in lines:
            # Strip whitespace for comparison (but keep original line)
            line_stripped = line.strip()
            
            # Check if line is empty - keep empty lines (but only first occurrence)
            if line_stripped == "":
                # Keep only first empty line occurrence
                if "" not in seen:
                    seen.add("")
                    unique_lines.append(line)
                else:
                    removed_count += 1
                continue
            
            # Check if we've seen this line before
            if line_stripped not in seen:
                seen.add(line_stripped)
                unique_lines.append(line)
            else:
                removed_count += 1
        
        # Join unique lines
        result = '\n'.join(unique_lines)
        
        # Prepare response message
        if removed_count > 0:
            message = (
                f"✅ **Duplicates Removed!**\n\n"
                f"📊 **Statistics:**\n"
                f"• Original lines: {len(lines)}\n"
                f"• Unique lines: {len(unique_lines)}\n"
                f"• Removed: {removed_count}\n\n"
                f"📝 **Result:**\n"
                f"```\n{result}\n```"
            )
        else:
            message = (
                f"ℹ️ **No Duplicates Found!**\n\n"
                f"📊 **Statistics:**\n"
                f"• Total lines: {len(lines)}\n"
                f"• All lines are unique!\n\n"
                f"📝 **Original Text:**\n"
                f"```\n{result}\n```"
            )
        
        # Send result
        if len(message) > 4096:
            # If message is too long, send result in parts
            await update.message.reply_text(
                f"✅ **Duplicates Removed!**\n\n"
                f"📊 **Statistics:**\n"
                f"• Original lines: {len(lines)}\n"
                f"• Unique lines: {len(unique_lines)}\n"
                f"• Removed: {removed_count}\n\n"
                f"📝 **Result:**"
            )
            # Send result in chunks if too long
            chunk_size = 4000
            for i in range(0, len(result), chunk_size):
                chunk = result[i:i + chunk_size]
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Remove duplicates error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ **Error removing duplicates:** {str(e)}\n\n"
            "💡 Please try again or check your text format."
        )

async def hash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate MD5, SHA1, SHA256, SHA512 hashes for text."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Get text and hash type
    text = ""
    hash_type = "all"  # Default
    
    # Priority 1: If reply to message, get text from replied message
    if update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
        # Get hash type from command args if provided
        if context.args and len(context.args) > 0:
            hash_type = context.args[0].lower()
        else:
            hash_type = "all"
    # Priority 2: If command has arguments
    elif context.args and len(context.args) > 0:
        hash_type = context.args[0].lower()
        if len(context.args) > 1:
            text = " ".join(context.args[1:])
        else:
            text = ""
    # Priority 3: Try to get from current message text
    else:
        message_text = update.message.text or update.message.caption or ""
        
        # Skip if it's just the button text
        if message_text.strip() == "🔐 Hash Generator":
            await update.message.reply_text(
                "🔐 **Hash Generator**\n\n"
                "**Usage:**\n"
                "• `/hash <type> <text>`\n"
                "• Reply to a message with: `/hash <type>`\n\n"
                "**Hash Types:**\n"
                "• `md5` - MD5 hash\n"
                "• `sha1` - SHA1 hash\n"
                "• `sha256` - SHA256 hash\n"
                "• `sha512` - SHA512 hash\n"
                "• `all` - All hash types\n\n"
                "**Example:**\n"
                "`/hash md5 Hello World`\n"
                "`/hash all MyPassword`\n"
                "Reply to message with: `/hash sha256`",
                parse_mode='Markdown'
            )
            return
        
        # Remove command prefix if present
        if message_text.startswith('/hash') or message_text.startswith('/md5') or message_text.startswith('/sha'):
            parts = message_text.split(' ', 2)
            if len(parts) >= 2:
                hash_type = parts[1].lower()
                if len(parts) > 2:
                    text = parts[2]
                else:
                    text = ""
            else:
                # Only command, no type or text
                await update.message.reply_text(
                    "❌ **Please specify hash type!**\n\n"
                    "**Usage:** `/hash <type> <text>`\n\n"
                    "**Hash Types:** `md5`, `sha1`, `sha256`, `sha512`, `all`\n\n"
                    "**Example:** `/hash md5 Hello World`"
                )
                return
        else:
            text = message_text
    
    if not text or len(text.strip()) == 0:
        await update.message.reply_text(
            "❌ **Please provide text or reply to a message!**\n\n"
            "**Usage:**\n"
            "• `/hash <type> <text>`\n"
            "• Reply to a message with: `/hash <type>`\n\n"
            "**Hash Types:**\n"
            "• `md5` - MD5 hash\n"
            "• `sha1` - SHA1 hash\n"
            "• `sha256` - SHA256 hash\n"
            "• `sha512` - SHA512 hash\n"
            "• `all` - All hash types\n\n"
            "**Example:**\n"
            "`/hash md5 Hello World`\n"
            "`/hash all MyPassword`"
        )
        return
    
    try:
        import hashlib
        
        # Normalize hash type
        hash_type = hash_type.lower()
        
        if hash_type not in ['md5', 'sha1', 'sha256', 'sha512', 'all']:
            await update.message.reply_text(
                "❌ **Invalid hash type!**\n\n"
                "**Available Hash Types:**\n"
                "• `md5` - MD5 hash\n"
                "• `sha1` - SHA1 hash\n"
                "• `sha256` - SHA256 hash\n"
                "• `sha512` - SHA512 hash\n"
                "• `all` - All hash types\n\n"
                "**Example:** `/hash md5 Hello World`"
            )
            return
        
        # Generate hashes
        hashes = {}
        
        if hash_type == 'all' or hash_type == 'md5':
            hashes['MD5'] = hashlib.md5(text.encode()).hexdigest()
        
        if hash_type == 'all' or hash_type == 'sha1':
            hashes['SHA1'] = hashlib.sha1(text.encode()).hexdigest()
        
        if hash_type == 'all' or hash_type == 'sha256':
            hashes['SHA256'] = hashlib.sha256(text.encode()).hexdigest()
        
        if hash_type == 'all' or hash_type == 'sha512':
            hashes['SHA512'] = hashlib.sha512(text.encode()).hexdigest()
        
        # Escape special characters for Markdown
        def escape_markdown_v2(text):
            """Escape special characters for Telegram Markdown V2."""
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in special_chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        # Escape text and hash values
        escaped_text = text.replace('`', '\\`').replace('*', '\\*').replace('_', '\\_').replace('[', '\\[').replace(']', '\\]')
        
        # Build response message
        if hash_type == 'all':
            message = (
                f"🔐 **Hash Generator - All Types**\n\n"
                f"📝 **Text:**\n"
                f"`{escaped_text}`\n\n"
                f"🔑 **Hashes:**\n"
            )
            for hash_name, hash_value in hashes.items():
                # Hash values are hex, so they should be safe, but escape just in case
                escaped_hash = hash_value.replace('`', '\\`')
                message += f"**{hash_name}:**\n`{escaped_hash}`\n\n"
        else:
            hash_name = hash_type.upper()
            hash_value = hashes[hash_name]
            # Hash values are hex, so they should be safe, but escape just in case
            escaped_hash = hash_value.replace('`', '\\`')
            message = (
                f"🔐 **Hash Generator - {hash_name}**\n\n"
                f"📝 **Text:**\n"
                f"`{escaped_text}`\n\n"
                f"🔑 **{hash_name} Hash:**\n"
                f"`{escaped_hash}`"
            )
        
        try:
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as parse_error:
            # If Markdown parsing fails, send without parse_mode
            logger.warning(f"Markdown parsing failed in hash command: {parse_error}")
            # Fallback: send plain text
            if hash_type == 'all':
                plain_message = (
                    f"🔐 Hash Generator - All Types\n\n"
                    f"📝 Text:\n{text}\n\n"
                    f"🔑 Hashes:\n"
                )
                for hash_name, hash_value in hashes.items():
                    plain_message += f"{hash_name}:\n{hash_value}\n\n"
            else:
                hash_name = hash_type.upper()
                hash_value = hashes[hash_name]
                plain_message = (
                    f"🔐 Hash Generator - {hash_name}\n\n"
                    f"📝 Text:\n{text}\n\n"
                    f"🔑 {hash_name} Hash:\n{hash_value}"
                )
            await update.message.reply_text(plain_message)
        
    except Exception as e:
        logger.error(f"Hash generation error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ **Error generating hash:** {str(e)}\n\n"
            "💡 Please try again or check your input."
        )

async def shorturl_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shorten URLs using free API."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Get URL from message or reply
    url = ""
    
    # Priority 1: If reply to message, get URL from replied message
    if update.message.reply_to_message:
        url = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    # Priority 2: If command has arguments
    elif context.args and len(context.args) > 0:
        url = " ".join(context.args)
    # Priority 3: Try to get from current message text
    else:
        message_text = update.message.text or update.message.caption or ""
        
        # Skip if it's just the button text
        if message_text.strip() == "🔗 URL Shortener":
            await update.message.reply_text(
                "🔗 **URL Shortener**\n\n"
                "**Usage:**\n"
                "• `/shorturl <URL>`\n"
                "• Reply to a message with: `/shorturl`\n"
                "• Or send URL directly\n\n"
                "**Example:**\n"
                "`/shorturl https://www.google.com`\n"
                "`/shorturl https://www.youtube.com/watch?v=example`\n\n"
                "Reply to message with URL using: `/shorturl`",
                parse_mode='Markdown'
            )
            return
        
        # Remove command prefix if present
        if message_text.startswith('/shorturl') or message_text.startswith('/short') or message_text.startswith('/url'):
            parts = message_text.split(' ', 1)
            if len(parts) > 1:
                url = parts[1]
            else:
                url = ""
        else:
            url = message_text
    
    if not url or len(url.strip()) == 0:
        await update.message.reply_text(
            "❌ **Please provide a URL or reply to a message!**\n\n"
            "**Usage:**\n"
            "• `/shorturl <URL>`\n"
            "• Reply to a message with: `/shorturl`\n"
            "• Or send URL directly\n\n"
            "**Example:**\n"
            "`/shorturl https://www.google.com`\n"
            "`/shorturl https://www.youtube.com/watch?v=example`"
        )
        return
    
    # Clean and validate URL
    url = url.strip()
    
    # Add http:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Basic URL validation
    if not (url.startswith('http://') or url.startswith('https://')):
        await update.message.reply_text(
            "❌ **Invalid URL format!**\n\n"
            "**Please provide a valid URL.**\n\n"
            "**Example:**\n"
            "`https://www.google.com`\n"
            "`https://www.youtube.com/watch?v=example`"
        )
        return
    
    try:
        processing_msg = await update.message.reply_text("🔗 Shortening URL...")
        
        # Use is.gd API (free, no API key needed)
        def shorten_url(url_to_shorten):
            try:
                api_url = f"https://is.gd/create.php?format=json&url={quote(url_to_shorten)}"
                response = requests.get(api_url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if 'shorturl' in data:
                        return data['shorturl']
                    else:
                        raise Exception("Failed to get short URL from response")
                else:
                    raise Exception(f"API returned status {response.status_code}")
            except Exception as e:
                logger.error(f"URL shortening error: {e}")
                # Try alternative API (v.gd)
                try:
                    api_url = f"https://v.gd/create.php?format=json&url={quote(url_to_shorten)}"
                    response = requests.get(api_url, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        if 'shorturl' in data:
                            return data['shorturl']
                except:
                    pass
                raise
        
        loop = asyncio.get_event_loop()
        short_url = await loop.run_in_executor(None, shorten_url, url)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Send result
        message = (
            f"🔗 **URL Shortened!**\n\n"
            f"📝 **Original URL:**\n"
            f"`{url}`\n\n"
            f"🔗 **Short URL:**\n"
            f"`{short_url}`\n\n"
            f"💡 Click the link above to copy!"
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"URL shortening error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "timeout" in error_msg or "connection" in error_msg:
            await update.message.reply_text(
                "❌ **Connection Error!**\n\n"
                "Could not connect to URL shortening service.\n\n"
                "**Please try again later.**"
            )
        else:
            await update.message.reply_text(
                f"❌ **Error shortening URL:** {str(e)}\n\n"
                "💡 Please make sure the URL is valid and try again."
            )

async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Take screenshot of a website."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Get URL from message or reply
    url = ""
    
    # Priority 1: If reply to message, get URL from replied message
    if update.message.reply_to_message:
        url = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    # Priority 2: If command has arguments
    elif context.args and len(context.args) > 0:
        url = " ".join(context.args)
    # Priority 3: Try to get from current message text
    else:
        message_text = update.message.text or update.message.caption or ""
        
        # Skip if it's just the button text
        if message_text.strip() == "📸 Screenshot":
            await update.message.reply_text(
                "📸 **Website Screenshot**\n\n"
                "**Usage:**\n"
                "• `/screenshot <URL>`\n"
                "• Reply to a message with: `/screenshot`\n"
                "• Or send URL directly\n\n"
                "**Example:**\n"
                "`/screenshot https://www.google.com`\n"
                "`/screenshot https://www.github.com`\n\n"
                "Reply to message with URL using: `/screenshot`",
                parse_mode='Markdown'
            )
            return
        
        # Remove command prefix if present
        if message_text.startswith('/screenshot') or message_text.startswith('/ss'):
            parts = message_text.split(' ', 1)
            if len(parts) > 1:
                url = parts[1]
            else:
                url = ""
        else:
            url = message_text
    
    if not url or len(url.strip()) == 0:
        await update.message.reply_text(
            "❌ **Please provide a URL or reply to a message!**\n\n"
            "**Usage:**\n"
            "• `/screenshot <URL>`\n"
            "• Reply to a message with: `/screenshot`\n"
            "• Or send URL directly\n\n"
            "**Example:**\n"
            "`/screenshot https://www.google.com`\n"
            "`/screenshot https://www.github.com`"
        )
        return
    
    # Clean and validate URL
    url = url.strip()
    
    # Add http:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Basic URL validation
    if not (url.startswith('http://') or url.startswith('https://')):
        await update.message.reply_text(
            "❌ **Invalid URL format!**\n\n"
            "**Please provide a valid URL.**\n\n"
            "**Example:**\n"
            "`https://www.google.com`\n"
            "`https://www.github.com`"
        )
        return
    
    try:
        processing_msg = await update.message.reply_text("📸 Taking website screenshot...")
        
        # Use free screenshot API
        def take_screenshot(url_to_screenshot):
            encoded_url = quote(url_to_screenshot)
            
            # Try multiple free screenshot APIs
            apis = [
                # API 1: api.screenshotlayer.com (free tier, no key needed for demo)
                {
                    'url': f"https://api.screenshotlayer.com/capture?access_key=demo&url={encoded_url}&viewport=1920x1080&format=PNG",
                    'name': 'screenshotlayer.com'
                },
                # API 2: mini.s-shot.ru (alternative format)
                {
                    'url': f"https://mini.s-shot.ru/1024x768/PNG/Z100/?{encoded_url}",
                    'name': 'mini.s-shot.ru'
                },
                # API 3: screenshotapi.net (free tier)
                {
                    'url': f"https://api.screenshotapi.net/?access_key=demo&url={encoded_url}&viewport=1920x1080",
                    'name': 'screenshotapi.net'
                },
                # API 4: Use a simple web-based screenshot service
                {
                    'url': f"https://image.thum.io/get/width/1920/crop/1920/noanimate/{url_to_screenshot}",
                    'name': 'thum.io'
                }
            ]
            
            for api in apis:
                try:
                    logger.info(f"Trying screenshot API: {api['name']}")
                    response = requests.get(api['url'], timeout=30, allow_redirects=True, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    if response.status_code == 200 and response.content:
                        # Check if response is actually an image (check content length and type)
                        content_length = len(response.content)
                        content_type = response.headers.get('content-type', '').lower()
                        
                        # Validate it's an image (must be > 1KB and have image content type or be binary data)
                        if content_length > 1024:  # At least 1KB
                            if content_type.startswith('image/') or content_length > 5000:
                                # Try to verify it's a valid image by checking magic bytes
                                img_bytes = response.content[:20]
                                # PNG: 89 50 4E 47, JPEG: FF D8 FF, GIF: 47 49 46 38
                                is_image = (
                                    img_bytes.startswith(b'\x89PNG') or  # PNG
                                    img_bytes.startswith(b'\xff\xd8\xff') or  # JPEG
                                    img_bytes.startswith(b'GIF8') or  # GIF
                                    img_bytes.startswith(b'BM')  # BMP
                                )
                                
                                if is_image or content_length > 10000:  # If large enough, assume it's valid
                                    img_buffer = io.BytesIO(response.content)
                                    img_buffer.seek(0)
                                    logger.info(f"Screenshot successful from {api['name']}, size: {content_length} bytes")
                                    return img_buffer
                        
                        logger.warning(f"Invalid image response from {api['name']}: content_length={content_length}, content_type={content_type}")
                except Exception as e:
                    logger.warning(f"Error with {api['name']}: {e}")
                    continue
            
            # If all APIs failed, raise exception
            raise Exception("All screenshot APIs failed. Please try again later or check the URL.")
        
        loop = asyncio.get_event_loop()
        screenshot_image = await loop.run_in_executor(None, take_screenshot, url)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Validate screenshot image before sending
        screenshot_image.seek(0)
        image_data = screenshot_image.read()
        
        if not image_data or len(image_data) < 1024:  # Less than 1KB is likely invalid
            raise Exception("Screenshot image is too small or invalid")
        
        # Reset buffer position
        screenshot_image.seek(0)
        screenshot_image.name = "screenshot.png"
        
        # Escape URL for Markdown
        escaped_url = url.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
        
        try:
            await update.message.reply_photo(
                photo=screenshot_image,
                caption=f"📸 **Website Screenshot**\n\n🔗 **URL:**\n`{escaped_url}`",
                parse_mode='Markdown'
            )
        except Exception as parse_error:
            # If Markdown parsing fails, send without parse_mode
            logger.warning(f"Markdown parsing failed in screenshot command: {parse_error}")
            try:
                screenshot_image.seek(0)  # Reset position
                await update.message.reply_photo(
                    photo=screenshot_image,
                    caption=f"📸 Website Screenshot\n\n🔗 URL:\n{url}"
                )
            except Exception as send_error:
                # If sending photo fails, try sending as document
                logger.warning(f"Failed to send as photo: {send_error}")
                screenshot_image.seek(0)
                await update.message.reply_document(
                    document=screenshot_image,
                    filename="screenshot.png",
                    caption=f"📸 Website Screenshot\n\n🔗 URL:\n{url}"
                )
        
    except Exception as e:
        logger.error(f"Website screenshot error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "timeout" in error_msg or "connection" in error_msg:
            await update.message.reply_text(
                "❌ **Connection Error!**\n\n"
                "Could not connect to screenshot service.\n\n"
                "**Please try again later.**"
            )
        elif "invalid" in error_msg or "not found" in error_msg:
            await update.message.reply_text(
                "❌ **Invalid URL or Website Error!**\n\n"
                "Could not take screenshot of this website.\n\n"
                "**Possible reasons:**\n"
                "• Website is not accessible\n"
                "• Website blocks screenshots\n"
                "• Invalid URL\n\n"
                "**Please try a different URL.**"
            )
        else:
            await update.message.reply_text(
                f"❌ **Error taking screenshot:** {str(e)}\n\n"
                "💡 Please make sure the URL is valid and try again."
            )

async def ip_lookup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get IP address information."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Get IP from message or reply
    ip_address = ""
    
    # Priority 1: If reply to message, get IP from replied message
    if update.message.reply_to_message:
        ip_address = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    # Priority 2: If command has arguments
    elif context.args and len(context.args) > 0:
        ip_address = " ".join(context.args)
    # Priority 3: Try to get from current message text
    else:
        message_text = update.message.text or update.message.caption or ""
        
        # Skip if it's just the button text
        if message_text.strip() == "🌐 IP Lookup":
            await update.message.reply_text(
                "🌐 **IP Lookup**\n\n"
                "**Usage:**\n"
                "• `/iplookup <IP>` - Get IP address information\n"
                "• Reply to a message with: `/iplookup`\n"
                "• Or send IP directly\n\n"
                "**Example:**\n"
                "`/iplookup 8.8.8.8`\n"
                "`/iplookup 1.1.1.1`\n\n"
                "Reply to message with IP using: `/iplookup`",
                parse_mode='Markdown'
            )
            return
        
        # Remove command prefix if present
        if message_text.startswith('/iplookup') or message_text.startswith('/ip') or message_text.startswith('/ipinfo'):
            parts = message_text.split(' ', 1)
            if len(parts) > 1:
                ip_address = parts[1]
            else:
                ip_address = ""
        else:
            ip_address = message_text
    
    if not ip_address or len(ip_address.strip()) == 0:
        await update.message.reply_text(
            "❌ **Please provide an IP address or reply to a message!**\n\n"
            "**Usage:**\n"
            "• `/iplookup <IP>` - Get IP address information\n"
            "• Reply to a message with: `/iplookup`\n"
            "• Or send IP directly\n\n"
            "**Example:**\n"
            "`/iplookup 8.8.8.8`\n"
            "`/iplookup 1.1.1.1`"
        )
        return
    
    # Clean IP address
    ip_address = ip_address.strip()
    
    # Basic IP validation (IPv4 format)
    import re
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(ipv4_pattern, ip_address):
        await update.message.reply_text(
            "❌ **Invalid IP address format!**\n\n"
            "**Please provide a valid IPv4 address.**\n\n"
            "**Example:**\n"
            "`8.8.8.8`\n"
            "`1.1.1.1`"
        )
        return
    
    # Check for private/reserved IP ranges
    ip_parts = ip_address.split('.')
    if len(ip_parts) == 4:
        try:
            first_octet = int(ip_parts[0])
            second_octet = int(ip_parts[1])
            
            # Private IP ranges
            is_private = (
                ip_address.startswith('127.') or  # Loopback
                ip_address.startswith('169.254.') or  # Link-local
                ip_address.startswith('0.') or  # Invalid
                (first_octet == 10) or  # 10.0.0.0/8
                (first_octet == 172 and 16 <= second_octet <= 31) or  # 172.16.0.0/12
                (first_octet == 192 and second_octet == 168) or  # 192.168.0.0/16
                (first_octet >= 224)  # Multicast/Reserved
            )
            
            if is_private:
                await update.message.reply_text(
                    "❌ **Private/Reserved IP Address!**\n\n"
                    "**This is a private or reserved IP address that cannot be looked up.**\n\n"
                    "**Private IP ranges include:**\n"
                    "• `127.0.0.0/8` - Loopback (localhost)\n"
                    "• `10.0.0.0/8` - Private network\n"
                    "• `172.16.0.0/12` - Private network\n"
                    "• `192.168.0.0/16` - Private network\n"
                    "• `169.254.0.0/16` - Link-local\n\n"
                    "**Please use a public IP address for lookup.**\n\n"
                    "**Example:**\n"
                    "`8.8.8.8` (Google DNS)\n"
                    "`1.1.1.1` (Cloudflare DNS)"
                )
                return
        except ValueError:
            pass  # If conversion fails, let API handle it
    
    try:
        processing_msg = await update.message.reply_text("🌐 Looking up IP information...")
        
        # Use free IP lookup API (ip-api.com - free tier, no API key needed)
        def lookup_ip(ip_to_lookup):
            try:
                # ip-api.com free tier (no API key needed)
                api_url = f"http://ip-api.com/json/{ip_to_lookup}?fields=status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
                response = requests.get(api_url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('status') == 'success':
                        return data
                    else:
                        raise Exception(data.get('message', 'Unknown error'))
                else:
                    raise Exception(f"API returned status {response.status_code}")
            except Exception as e:
                logger.error(f"IP lookup error: {e}")
                raise
        
        loop = asyncio.get_event_loop()
        ip_data = await loop.run_in_executor(None, lookup_ip, ip_address)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Format response
        country = ip_data.get('country', 'N/A')
        country_code = ip_data.get('countryCode', 'N/A')
        region = ip_data.get('regionName', 'N/A')
        city = ip_data.get('city', 'N/A')
        zip_code = ip_data.get('zip', 'N/A')
        lat = ip_data.get('lat', 'N/A')
        lon = ip_data.get('lon', 'N/A')
        timezone = ip_data.get('timezone', 'N/A')
        isp = ip_data.get('isp', 'N/A')
        org = ip_data.get('org', 'N/A')
        asn = ip_data.get('as', 'N/A')
        
        # Escape special characters for Markdown
        def escape_md(text):
            if text == 'N/A':
                return text
            return str(text).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
        
        message = (
            f"🌐 **IP Address Information**\n\n"
            f"📍 **IP Address:**\n"
            f"`{ip_address}`\n\n"
            f"🌍 **Location:**\n"
            f"• **Country:** {escape_md(country)} ({country_code})\n"
            f"• **Region:** {escape_md(region)}\n"
            f"• **City:** {escape_md(city)}\n"
            f"• **ZIP Code:** {escape_md(zip_code)}\n"
            f"• **Coordinates:** {lat}, {lon}\n\n"
            f"⏰ **Timezone:**\n"
            f"`{escape_md(timezone)}`\n\n"
            f"💻 **Network:**\n"
            f"• **ISP:** {escape_md(isp)}\n"
            f"• **Organization:** {escape_md(org)}\n"
            f"• **ASN:** {escape_md(asn)}\n"
        )
        
        try:
            await update.message.reply_text(message, parse_mode='Markdown')
        except Exception as parse_error:
            # If Markdown parsing fails, send without parse_mode
            logger.warning(f"Markdown parsing failed in IP lookup: {parse_error}")
            plain_message = (
                f"🌐 IP Address Information\n\n"
                f"📍 IP Address:\n{ip_address}\n\n"
                f"🌍 Location:\n"
                f"• Country: {country} ({country_code})\n"
                f"• Region: {region}\n"
                f"• City: {city}\n"
                f"• ZIP Code: {zip_code}\n"
                f"• Coordinates: {lat}, {lon}\n\n"
                f"⏰ Timezone:\n{timezone}\n\n"
                f"💻 Network:\n"
                f"• ISP: {isp}\n"
                f"• Organization: {org}\n"
                f"• ASN: {asn}\n"
            )
            await update.message.reply_text(plain_message)
        
    except Exception as e:
        logger.error(f"IP lookup error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "timeout" in error_msg or "connection" in error_msg:
            await update.message.reply_text(
                "❌ **Connection Error!**\n\n"
                "Could not connect to IP lookup service.\n\n"
                "**Please try again later.**"
            )
        elif "private" in error_msg or "private range" in error_msg:
            await update.message.reply_text(
                "❌ **Private/Reserved IP Address!**\n\n"
                "**This is a private or reserved IP address that cannot be looked up.**\n\n"
                "**Private IP ranges include:**\n"
                "• `127.0.0.0/8` - Loopback (localhost)\n"
                "• `10.0.0.0/8` - Private network\n"
                "• `172.16.0.0/12` - Private network\n"
                "• `192.168.0.0/16` - Private network\n"
                "• `169.254.0.0/16` - Link-local\n\n"
                "**Please use a public IP address for lookup.**\n\n"
                "**Example:**\n"
                "`8.8.8.8` (Google DNS)\n"
                "`1.1.1.1` (Cloudflare DNS)"
            )
        elif "invalid" in error_msg or "not found" in error_msg:
            await update.message.reply_text(
                "❌ **Invalid IP Address!**\n\n"
                "Could not find information for this IP address.\n\n"
                "**Please check the IP address and try again.**"
            )
        else:
            await update.message.reply_text(
                f"❌ **Error looking up IP:** {str(e)}\n\n"
                "💡 Please make sure the IP address is valid and try again."
            )

async def audio_to_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert audio/voice message to text using speech recognition."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    # Get language from command arguments (e.g., /audiototext bn or /audiototext en)
    language = 'bn-BD'  # Default to Bangla
    if context.args and len(context.args) > 0:
        lang_arg = context.args[0].lower()
        # Map common language codes
        lang_map = {
            'bn': 'bn-BD',  # Bangla
            'bangla': 'bn-BD',
            'bengali': 'bn-BD',
            'en': 'en-US',  # English
            'english': 'en-US',
            'hi': 'hi-IN',  # Hindi
            'hindi': 'hi-IN',
            'ar': 'ar-SA',  # Arabic
            'arabic': 'ar-SA',
            'es': 'es-ES',  # Spanish
            'spanish': 'es-ES',
            'fr': 'fr-FR',  # French
            'french': 'fr-FR',
        }
        language = lang_map.get(lang_arg, 'bn-BD')  # Default to Bangla if not recognized
    
    # Check if message has voice or audio
    if not update.message.voice and not update.message.audio:
        # Check if replying to a voice/audio message
        if update.message.reply_to_message:
            if not update.message.reply_to_message.voice and not update.message.reply_to_message.audio:
                await update.message.reply_text(
                    "❌ **Please send or reply to a voice/audio message!**\n\n"
                    "**Usage:**\n"
                    "• Send a voice message or audio file\n"
                    "• Or reply to a voice/audio message with `/audiototext`\n\n"
                    "**Language Support:**\n"
                    "• `/audiototext` - Default: Bangla (bn-BD)\n"
                    "• `/audiototext bn` - Bangla/Bengali\n"
                    "• `/audiototext en` - English\n"
                    "• `/audiototext hi` - Hindi\n"
                    "• `/audiototext ar` - Arabic\n"
                    "• `/audiototext es` - Spanish\n"
                    "• `/audiototext fr` - French\n\n"
                    "**Example:**\n"
                    "Send a voice message directly, or:\n"
                    "Reply to a voice message with: `/audiototext bn`"
                )
                return
        else:
            await update.message.reply_text(
                "❌ **Please send or reply to a voice/audio message!**\n\n"
                "**Usage:**\n"
                "• Send a voice message or audio file\n"
                "• Or reply to a voice/audio message with `/audiototext`\n\n"
                "**Example:**\n"
                "Send a voice message directly, or:\n"
                "Reply to a voice message with: `/audiototext`"
            )
            return
    
    try:
        # Get voice or audio from message or reply
        voice = None
        audio = None
        
        if update.message.voice:
            voice = update.message.voice
        elif update.message.audio:
            audio = update.message.audio
        elif update.message.reply_to_message:
            if update.message.reply_to_message.voice:
                voice = update.message.reply_to_message.voice
            elif update.message.reply_to_message.audio:
                audio = update.message.reply_to_message.audio
        
        processing_msg = await update.message.reply_text("🎤 Converting audio to text...")
        
        # Download file first (async)
        file_id = voice.file_id if voice else audio.file_id
        file = await context.bot.get_file(file_id)
        
        # Download to temporary file
        import tempfile
        import os
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_audio:
            temp_path = temp_audio.name
        
        # Download file content
        file_path = file.file_path
        if file_path.startswith('http'):
            download_url = file_path
        else:
            download_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"
        
        # Download file
        response = requests.get(download_url, timeout=30)
        response.raise_for_status()
        
        with open(temp_path, 'wb') as f:
            f.write(response.content)
        
        # Convert audio to text
        def convert_audio_to_text(lang=language):
            wav_path = None
            try:
                import speech_recognition as sr
                
                # Initialize recognizer
                r = sr.Recognizer()
                
                # Try to convert OGG to WAV using ffmpeg (if available)
                # Otherwise, try direct OGG recognition or use alternative
                try:
                    # First, try to convert OGG to WAV using ffmpeg directly
                    # Check if ffmpeg is available
                    import subprocess
                    # Try multiple ffmpeg paths
                    # Get the directory where bot.py is located
                    bot_dir = os.path.dirname(os.path.abspath(__file__))
                    ffmpeg_paths = [
                        'ffmpeg',  # In PATH
                        os.path.join(bot_dir, 'ffmpeg-8.0-essentials_build', 'bin', 'ffmpeg.exe'),  # Workspace ffmpeg
                        r'C:\ffmpeg\bin\ffmpeg.exe',
                        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
                        os.path.join(os.path.expanduser('~'), 'ffmpeg', 'bin', 'ffmpeg.exe'),
                        os.path.join(os.path.expanduser('~'), 'Downloads', 'ffmpeg', 'bin', 'ffmpeg.exe'),
                    ]
                    
                    ffmpeg_cmd = None
                    ffprobe_cmd = None
                    for path in ffmpeg_paths:
                        try:
                            if path == 'ffmpeg':
                                # Try system PATH
                                result = subprocess.run(['ffmpeg', '-version'], 
                                                       stdout=subprocess.PIPE, 
                                                       stderr=subprocess.PIPE, 
                                                       timeout=2)
                                if result.returncode == 0:
                                    ffmpeg_cmd = 'ffmpeg'
                                    ffprobe_cmd = 'ffprobe'
                                    break
                            else:
                                # Try specific path - make it absolute
                                abs_path = os.path.abspath(path)
                                if os.path.exists(abs_path):
                                    result = subprocess.run([abs_path, '-version'], 
                                                           stdout=subprocess.PIPE, 
                                                           stderr=subprocess.PIPE, 
                                                           timeout=2)
                                    if result.returncode == 0:
                                        ffmpeg_cmd = abs_path
                                        # Set ffprobe path
                                        ffprobe_path = abs_path.replace('ffmpeg.exe', 'ffprobe.exe')
                                        if os.path.exists(ffprobe_path):
                                            ffprobe_cmd = ffprobe_path
                                        else:
                                            ffprobe_cmd = abs_path.replace('ffmpeg.exe', 'ffprobe.exe')
                                        logger.info(f"Found ffmpeg at: {ffmpeg_cmd}")
                                        break
                        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
                            continue
                    
                    if ffmpeg_cmd:
                        # ffmpeg is available, convert OGG to WAV using subprocess directly
                        wav_path = temp_path.replace('.ogg', '.wav')
                        
                        # Verify input file exists
                        if not os.path.exists(temp_path):
                            raise Exception(f"Input OGG file not found: {temp_path}")
                        
                        logger.info(f"Input file: {temp_path} (size: {os.path.getsize(temp_path)} bytes)")
                        logger.info(f"Output file will be: {wav_path}")
                        
                        # Use subprocess to call ffmpeg directly (more reliable than pydub)
                        convert_cmd = [
                            ffmpeg_cmd,
                            '-i', temp_path,  # Input OGG file
                            '-ar', '16000',   # Sample rate 16kHz (good for speech recognition)
                            '-ac', '1',       # Mono channel
                            '-f', 'wav',      # Output format WAV
                            '-y',             # Overwrite output file
                            wav_path          # Output WAV file
                        ]
                        
                        # Log command (with quotes for paths with spaces)
                        cmd_str = ' '.join(f'"{arg}"' if ' ' in str(arg) else str(arg) for arg in convert_cmd)
                        logger.info(f"Running ffmpeg conversion: {cmd_str}")
                        
                        # Prepare subprocess args
                        subprocess_kwargs = {
                            'stdout': subprocess.PIPE,
                            'stderr': subprocess.PIPE,
                            'timeout': 30
                        }
                        
                        # Add Windows-specific flag to hide console window
                        if sys.platform == 'win32':
                            try:
                                subprocess_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                            except AttributeError:
                                # CREATE_NO_WINDOW not available in this Python version
                                pass
                        
                        result = subprocess.run(convert_cmd, **subprocess_kwargs)
                        
                        if result.returncode != 0:
                            error_msg = result.stderr.decode('utf-8', errors='ignore')
                            stdout_msg = result.stdout.decode('utf-8', errors='ignore')
                            logger.error(f"ffmpeg stderr: {error_msg}")
                            logger.error(f"ffmpeg stdout: {stdout_msg}")
                            logger.error(f"ffmpeg return code: {result.returncode}")
                            # Raise exception with detailed error - this will be caught by outer handler
                            raise Exception(f"ffmpeg conversion failed (return code {result.returncode}): {error_msg[:500]}")
                        
                        # Verify WAV file was created
                        if not os.path.exists(wav_path):
                            raise Exception(f"WAV file was not created by ffmpeg. Expected path: {wav_path}")
                        
                        # Verify file size is reasonable (not empty)
                        file_size = os.path.getsize(wav_path)
                        if file_size < 1000:  # Less than 1KB is suspicious
                            raise Exception(f"WAV file is too small ({file_size} bytes), conversion may have failed")
                        
                        logger.info(f"Successfully converted OGG to WAV: {wav_path} ({file_size} bytes)")
                        
                        # Use WAV file for recognition
                        with sr.AudioFile(wav_path) as source:
                            audio_data = r.record(source)
                        
                        text = r.recognize_google(audio_data, language=lang)
                        
                        # Clean up
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        if wav_path and os.path.exists(wav_path):
                            os.unlink(wav_path)
                        return text
                    else:
                        # ffmpeg not found, will try alternative method below
                        logger.warning("ffmpeg not found, attempting alternative conversion methods")
                    
                    # If conversion fails or ffmpeg not found, try using alternative method:
                    # Send raw audio data directly to Google Speech API
                    # Read audio file and send as bytes
                    with open(temp_path, 'rb') as audio_file:
                        audio_bytes = audio_file.read()
                    
                    # Try using Google Speech Recognition with audio data
                    # Note: This might not work for OGG, but worth trying
                    try:
                        # Use recognize_google with raw audio data
                        # This requires converting to a format Google accepts
                        text = r.recognize_google(audio_bytes, language='en-US')
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                        return text
                    except Exception:
                        # If that fails, try creating a temporary WAV using wave
                        # This is a workaround for OGG files
                        import wave
                        import struct
                        
                        # Try to extract audio data from OGG and create WAV
                        # This is a simplified approach - may not work perfectly
                        try:
                            # Read OGG file and try to create WAV manually
                            # This is a basic workaround
                            wav_path = temp_path.replace('.ogg', '.wav')
                            
                            # For now, raise an error with helpful message
                            raise Exception("OGG format requires ffmpeg for conversion. Please install ffmpeg or send audio in WAV/MP3 format.")
                        except Exception as e_wav:
                            raise Exception(f"Audio format not supported. Original error: {str(e_wav)}")
                
                except ImportError:
                    raise Exception("Speech recognition library not installed. Please install: pip install SpeechRecognition")
                
            except Exception as e:
                logger.error(f"Audio to text conversion error: {e}")
                # Clean up
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.unlink(temp_path)
                    if wav_path and os.path.exists(wav_path):
                        os.unlink(wav_path)
                except:
                    pass
                raise
        
        loop = asyncio.get_event_loop()
        recognized_text = await loop.run_in_executor(None, convert_audio_to_text, language)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Send result
        if recognized_text and len(recognized_text.strip()) > 0:
            # Get language name for display
            lang_names = {
                'bn-BD': 'বাংলা (Bangla)',
                'en-US': 'English',
                'hi-IN': 'हिंदी (Hindi)',
                'ar-SA': 'العربية (Arabic)',
                'es-ES': 'Español (Spanish)',
                'fr-FR': 'Français (French)',
            }
            lang_display = lang_names.get(language, language)
            
            message = (
                f"🎤 **Audio to Text**\n\n"
                f"🌐 **Language:** {lang_display}\n\n"
                f"📝 **Recognized Text:**\n"
                f"`{recognized_text}`"
            )
            
            # Escape Markdown
            escaped_text = recognized_text.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
            
            try:
                await update.message.reply_text(
                    f"🎤 **Audio to Text**\n\n"
                    f"🌐 **Language:** {lang_display}\n\n"
                    f"📝 **Recognized Text:**\n"
                    f"`{escaped_text}`",
                    parse_mode='Markdown'
                )
            except Exception as parse_error:
                logger.warning(f"Markdown parsing failed: {parse_error}")
                await update.message.reply_text(
                    f"🎤 Audio to Text\n\n"
                    f"🌐 Language: {lang_display}\n\n"
                    f"📝 Recognized Text:\n{recognized_text}"
                )
        else:
            await update.message.reply_text(
                "❌ **No text recognized!**\n\n"
                "Could not detect any speech in the audio.\n\n"
                "**Please try:**\n"
                "• Speak more clearly\n"
                "• Check audio quality\n"
                "• Ensure audio is not too long\n"
                "• Try a different audio format"
            )
        
    except Exception as e:
        logger.error(f"Audio to text error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "not installed" in error_msg or "import" in error_msg:
            await update.message.reply_text(
                "❌ **Library Not Installed!**\n\n"
                "Speech recognition library is required.\n\n"
                "**Please install:**\n"
                "`pip install SpeechRecognition`\n\n"
                "**Optional (for better support):**\n"
                "`pip install pydub`"
            )
        elif "ffmpeg" in error_msg or "format not supported" in error_msg or "ogg" in error_msg.lower():
            # Check if ffmpeg was found but conversion failed
            if "ffmpeg conversion failed" in error_msg.lower() or "return code" in error_msg.lower():
                # ffmpeg was found but conversion failed - show detailed error
                error_details = str(e)[:500]  # Limit error message length
                await update.message.reply_text(
                    f"❌ **FFmpeg Conversion Failed!**\n\n"
                    f"FFmpeg was found but the conversion failed.\n\n"
                    f"**Error Details:**\n"
                    f"`{error_details}`\n\n"
                    f"**Please check:**\n"
                    f"• Audio file is not corrupted\n"
                    f"• FFmpeg installation is complete\n"
                    f"• Try a different audio file\n\n"
                    f"**Alternative:** Send audio in WAV or MP3 format."
                )
            else:
                # ffmpeg not found or general format issue
                await update.message.reply_text(
                    "❌ **Audio Format Issue!**\n\n"
                    "OGG format requires ffmpeg for conversion.\n\n"
                    "**Solutions:**\n"
                    "1. **Install ffmpeg:**\n"
                    "   • Download from: https://ffmpeg.org/download.html\n"
                    "   • Add to system PATH\n"
                    "   • Or install via: `choco install ffmpeg` (Windows)\n\n"
                    "2. **Alternative:**\n"
                    "   • Send audio in WAV or MP3 format\n"
                    "   • Or use a different audio format\n\n"
                    "**Note:** Voice messages from Telegram are in OGG format and require ffmpeg for conversion."
                )
        elif "could not understand" in error_msg or "no speech" in error_msg:
            await update.message.reply_text(
                "❌ **Speech Not Recognized!**\n\n"
                "Could not understand the audio.\n\n"
                "**Please try:**\n"
                "• Speak more clearly\n"
                "• Check audio quality\n"
                "• Ensure audio contains speech\n"
                "• Try a shorter audio clip"
            )
        elif "timeout" in error_msg or "connection" in error_msg:
            await update.message.reply_text(
                "❌ **Connection Error!**\n\n"
                "Could not connect to speech recognition service.\n\n"
                "**Please try again later.**"
            )
        else:
            await update.message.reply_text(
                f"❌ **Error converting audio:** {str(e)}\n\n"
                "💡 Please make sure the audio file is valid and try again."
            )

async def repeat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Repeat text a specified number of times."""
    try:
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "❌ **Text Repeater**\n\n"
                "Usage: `/repeat <number> <text>`\n"
                "Example: `/repeat 5 Hello`\n"
                "Example: `/repeat 100 Welcome`\n"
                "Example: `/repeat 1000 Text` (unlimited!)\n\n"
                "Or use: `/repeat <text>` (default: repeats 1 time)\n"
                "Example: `/repeat Hello World`\n\n"
                "💡 **Unlimited repetitions!** Large results will be split into multiple messages.",
                parse_mode='Markdown'
            )
            return
        
        # Join all arguments first
        all_args = ' '.join(context.args)
        
        # Try to parse first argument as number
        first_arg = context.args[0]
        
        # Check if first argument is a number
        if first_arg.isdigit() or (first_arg.startswith('-') and first_arg[1:].isdigit()):
            try:
                repeat_count = int(first_arg)
                if repeat_count <= 0:
                    await update.message.reply_text(
                        "❌ Number must be greater than 0!\n"
                        "Example: /repeat 5 Hello"
                    )
                    return
                
                # Get text from remaining args (skip the number)
                if len(context.args) > 1:
                    text = ' '.join(context.args[1:])
                else:
                    text = ""
            except ValueError:
                # If conversion fails, treat as text
                repeat_count = 1
                text = all_args
        else:
            # No number provided, default to 1 repetition
            repeat_count = 1
            text = all_args
        
        # Check if text is empty
        if not text or not text.strip():
            await update.message.reply_text(
                "❌ Please provide text to repeat!\n"
                "Example: /repeat 5 Hello\n"
                "Example: /repeat Hello World"
            )
            return
        
        # Repeat the text (each on a new line)
        repeated_lines = []
        for i in range(repeat_count):
            repeated_lines.append(text)
        
        repeated_text = '\n'.join(repeated_lines)
        
        # Create the full message with header
        header = f'🔄 **Text Repeated {repeat_count} time(s):**\n\n'
        
        # Telegram message limit is 4096 characters
        max_chars_per_message = 4000  # Leave some buffer
        
        # If message fits in one message, send it
        full_message = header + repeated_text
        if len(full_message) <= 4096:
            await update.message.reply_text(full_message, parse_mode='Markdown')
        else:
            # Send header first
            await update.message.reply_text(header, parse_mode='Markdown')
            
            # Split repeated text into multiple messages if needed
            if len(repeated_text) <= max_chars_per_message:
                # Fits in one message
                await update.message.reply_text(repeated_text)
            else:
                # Need to split into multiple messages
                # Calculate how many lines per message
                lines = repeated_text.split('\n')
                lines_per_message = len(lines) // ((len(repeated_text) // max_chars_per_message) + 1)
                
                current_chunk = []
                current_length = 0
                messages_sent = 0
                
                for line in lines:
                    line_with_newline = line + '\n'
                    
                    # If adding this line would exceed limit, send current chunk
                    if current_length + len(line_with_newline) > max_chars_per_message and current_chunk:
                        chunk_text = '\n'.join(current_chunk)
                        await update.message.reply_text(chunk_text)
                        messages_sent += 1
                        current_chunk = [line]
                        current_length = len(line)
                    else:
                        current_chunk.append(line)
                        current_length += len(line_with_newline)
                
                # Send remaining chunk
                if current_chunk:
                    chunk_text = '\n'.join(current_chunk)
                    await update.message.reply_text(chunk_text)
                    messages_sent += 1
                
                # Send summary
                if messages_sent > 1:
                    await update.message.reply_text(
                        f"✅ **Sent {messages_sent} messages** with {repeat_count} repetitions!",
                        parse_mode='Markdown'
                    )
        
    except ValueError as ve:
        await update.message.reply_text(
            f"❌ Invalid number format: {str(ve)}\n"
            "Example: /repeat 5 Hello"
        )
    except Exception as e:
        logger.error(f"Repeat command error: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Error: {str(e)}\n"
            "Please try again.\n\n"
            "Usage: /repeat <number> <text>"
        )

async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate QR code for text/URL using online API."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide text or URL to generate QR code!\n"
            "Example: /qr https://google.com\n"
            "Example: /qr Hello World\n"
            "Example: /qr +8801234567890"
        )
        return
    
    data = ' '.join(context.args)
    
    # Show processing message
    processing_msg = await update.message.reply_text("📱 Generating QR code...")
    
    try:
        # Use online QR code API (no PIL/Pillow needed)
        loop = asyncio.get_event_loop()
        
        def generate_qr():
            try:
                # Encode data for URL
                encoded_data = quote(data)
                # Use QR Server API
                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_data}"
                
                # Download QR code image
                response = requests.get(qr_url, timeout=10)
                if response.status_code == 200:
                    img_buffer = io.BytesIO(response.content)
                    img_buffer.seek(0)
                    return img_buffer
                else:
                    raise Exception(f"QR API returned status {response.status_code}")
            except Exception as e:
                logger.error(f"QR generation function error: {e}", exc_info=True)
                raise
        
        # Run QR generation in executor
        qr_image = await loop.run_in_executor(None, generate_qr)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Send QR code image
        await update.message.reply_photo(
            photo=qr_image,
            caption=f"📱 QR Code for:\n`{data}`",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        logger.error(f"QR code generation error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ Sorry, I encountered an error while generating QR code. "
            "Please try again later."
        )

async def blur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blur an image."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image blur feature requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please send an image or reply to an image message!\n"
            "Example: Reply to an image with /blur"
        )
        return
    
    try:
        # Get image from message or reply
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text("🎨 Blurring image...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def process_blur(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                blurred_img = img.filter(ImageFilter.GaussianBlur(radius=5))
                
                output_buffer = io.BytesIO()
                if blurred_img.mode != 'RGB':
                    blurred_img = blurred_img.convert('RGB')
                blurred_img.save(output_buffer, format='PNG')
                output_buffer.seek(0)
                return output_buffer
            except Exception as e:
                logger.error(f"Blur processing error: {e}", exc_info=True)
                raise
        
        blurred_image = await loop.run_in_executor(None, process_blur, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_photo(
            photo=blurred_image,
            caption="🎨 Blurred image"
        )
    
    except Exception as e:
        logger.error(f"Blur command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ Error: {str(e)}. Please try again."
        )

async def watermark_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add watermark text to an image."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image watermark feature requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ **Please send an image or reply to an image message!**\n\n"
            "**Usage:**\n"
            "• Reply to an image with: `/watermark <text>`\n"
            "• Or: `/watermark <text> <position>`\n\n"
            "**Positions:**\n"
            "• `center` - Center of image\n"
            "• `top-left`, `top-right`\n"
            "• `bottom-left`, `bottom-right`\n"
            "• `top`, `bottom`\n\n"
            "**Example:**\n"
            "`/watermark @MyBrand center`\n"
            "`/watermark Copyright 2024 bottom-right`"
        )
        return
    
    # Get watermark text from command arguments
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Please provide watermark text!**\n\n"
            "**Usage:** `/watermark <text> [position]`\n\n"
            "**Example:**\n"
            "`/watermark @MyBrand`\n"
            "`/watermark Copyright 2024 bottom-right`"
        )
        return
    
    watermark_text = ' '.join(context.args)
    position = "bottom-right"  # Default position
    
    # Check if last argument is a position
    if len(context.args) > 1:
        last_arg = context.args[-1].lower()
        positions = ['center', 'top-left', 'top-right', 'bottom-left', 'bottom-right', 'top', 'bottom']
        if last_arg in positions:
            position = last_arg
            watermark_text = ' '.join(context.args[:-1])
    
    try:
        # Get image from message or reply
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text("💧 Adding watermark...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def add_watermark(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                # Download image
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                width, height = img.size
                
                # Create a transparent overlay for watermark
                overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                
                # Calculate font size (adaptive based on image size)
                font_size = max(24, min(width, height) // 20)
                
                # Try to use a font, fallback to default if not available
                font = None
                if IMAGEFONT_AVAILABLE:
                    try:
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except:
                        try:
                            font = ImageFont.truetype("Arial.ttf", font_size)
                        except:
                            try:
                                from PIL import ImageFont
                                font = ImageFont.load_default()
                            except:
                                pass
                
                # Calculate text position
                if font:
                    try:
                        bbox = draw.textbbox((0, 0), watermark_text, font=font)
                        text_width = bbox[2] - bbox[0]
                        text_height = bbox[3] - bbox[1]
                    except:
                        text_width = len(watermark_text) * (font_size // 2)
                        text_height = font_size
                else:
                    text_width = len(watermark_text) * (font_size // 2)
                    text_height = font_size
                
                # Position calculations
                padding = max(20, min(width, height) // 30)
                
                if position == "center":
                    x = (width - text_width) // 2
                    y = (height - text_height) // 2
                elif position == "top-left":
                    x = padding
                    y = padding
                elif position == "top-right":
                    x = width - text_width - padding
                    y = padding
                elif position == "bottom-left":
                    x = padding
                    y = height - text_height - padding
                elif position == "bottom-right":
                    x = width - text_width - padding
                    y = height - text_height - padding
                elif position == "top":
                    x = (width - text_width) // 2
                    y = padding
                elif position == "bottom":
                    x = (width - text_width) // 2
                    y = height - text_height - padding
                else:
                    # Default to bottom-right
                    x = width - text_width - padding
                    y = height - text_height - padding
                
                # Draw semi-transparent background for better visibility
                bg_padding = 10
                bg_x = x - bg_padding
                bg_y = y - bg_padding
                bg_width = text_width + (bg_padding * 2)
                bg_height = text_height + (bg_padding * 2)
                
                # Semi-transparent dark background
                draw.rectangle(
                    [(bg_x, bg_y), (bg_x + bg_width, bg_y + bg_height)],
                    fill=(0, 0, 0, 128)  # Semi-transparent black
                )
                
                # Draw watermark text (white with transparency)
                text_color = (255, 255, 255, 200)  # White with some transparency
                
                if font:
                    draw.text((x, y), watermark_text, font=font, fill=text_color)
                else:
                    draw.text((x, y), watermark_text, fill=text_color)
                
                # Composite overlay onto original image
                watermarked_img = Image.alpha_composite(
                    img.convert('RGBA'),
                    overlay
                ).convert('RGB')
                
                # Save to buffer
                output_buffer = io.BytesIO()
                watermarked_img.save(output_buffer, format='PNG', quality=95)
                output_buffer.seek(0)
                return output_buffer
            except Exception as e:
                logger.error(f"Watermark processing error: {e}", exc_info=True)
                raise
        
        watermarked_image = await loop.run_in_executor(None, add_watermark, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_photo(
            photo=watermarked_image,
            caption=f"💧 **Watermarked Image**\n\n"
                   f"📝 Text: `{watermark_text}`\n"
                   f"📍 Position: `{position}`",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        logger.error(f"Watermark command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ **Error:** {str(e)}\n\n"
            "💡 Please try again or check your command format."
        )

async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply filters (Grayscale, Sepia, Vintage, Bright, Dark, Contrast, Saturate, Invert, Warm, Cool, Vibrant, Faded, Sharp) to an image."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image filter feature requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ **Please send an image or reply to an image message!**\n\n"
            "**Usage:**\n"
            "• Reply to an image with: `/filter <type>`\n\n"
            "**Available Filters:**\n"
            "• `grayscale` or `gray` - Black & white\n"
            "• `sepia` - Vintage brown tone\n"
            "• `vintage` - Old photo effect\n"
            "• `bright` - Brighten image\n"
            "• `dark` - Darken image\n"
            "• `contrast` - Increase contrast\n"
            "• `saturate` - Increase color saturation\n"
            "• `invert` - Negative/invert colors\n"
            "• `warm` - Warm color tone\n"
            "• `cool` - Cool color tone\n"
            "• `vibrant` - Vibrant colors\n"
            "• `faded` - Faded/desaturated look\n"
            "• `sharp` - Sharpen image\n\n"
            "**Example:**\n"
            "`/filter grayscale`\n"
            "`/filter bright`\n"
            "`/filter invert`"
        )
        return
    
    # Get filter type from command arguments
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ **Please specify a filter type!**\n\n"
            "**Usage:** `/filter <type>`\n\n"
            "**Available Filters:**\n"
            "• `grayscale` or `gray` - Black & white\n"
            "• `sepia` - Vintage brown tone\n"
            "• `vintage` - Old photo effect\n"
            "• `bright` - Brighten image\n"
            "• `dark` - Darken image\n"
            "• `contrast` - Increase contrast\n"
            "• `saturate` - Increase color saturation\n"
            "• `invert` - Negative/invert colors\n"
            "• `warm` - Warm color tone\n"
            "• `cool` - Cool color tone\n"
            "• `vibrant` - Vibrant colors\n"
            "• `faded` - Faded/desaturated look\n"
            "• `sharp` - Sharpen image\n\n"
            "**Example:**\n"
            "`/filter grayscale`\n"
            "`/filter bright`\n"
            "`/filter invert`"
        )
        return
    
    filter_type = context.args[0].lower()
    
    # Normalize filter type
    if filter_type in ['grayscale', 'gray', 'bw', 'blackwhite', 'greyscale']:
        filter_type = 'grayscale'
    elif filter_type in ['sepia']:
        filter_type = 'sepia'
    elif filter_type in ['vintage', 'old', 'retro']:
        filter_type = 'vintage'
    elif filter_type in ['bright', 'brighten', 'light']:
        filter_type = 'bright'
    elif filter_type in ['dark', 'darken']:
        filter_type = 'dark'
    elif filter_type in ['contrast', 'highcontrast']:
        filter_type = 'contrast'
    elif filter_type in ['saturate', 'saturation', 'colorful']:
        filter_type = 'saturate'
    elif filter_type in ['invert', 'inverse', 'negative', 'neg']:
        filter_type = 'invert'
    elif filter_type in ['warm', 'warmth']:
        filter_type = 'warm'
    elif filter_type in ['cool', 'coolness', 'cold']:
        filter_type = 'cool'
    elif filter_type in ['vibrant', 'vibrance', 'vivid']:
        filter_type = 'vibrant'
    elif filter_type in ['faded', 'fade', 'desaturate', 'muted']:
        filter_type = 'faded'
    elif filter_type in ['sharp', 'sharpen', 'sharpness']:
        filter_type = 'sharp'
    else:
        await update.message.reply_text(
            "❌ **Invalid filter type!**\n\n"
            "**Available Filters:**\n"
            "• `grayscale` or `gray` - Black & white\n"
            "• `sepia` - Vintage brown tone\n"
            "• `vintage` - Old photo effect\n"
            "• `bright` or `brighten` - Brighten image\n"
            "• `dark` or `darken` - Darken image\n"
            "• `contrast` - Increase contrast\n"
            "• `saturate` or `saturation` - Increase color saturation\n"
            "• `invert` or `negative` - Negative/invert colors\n"
            "• `warm` - Warm color tone\n"
            "• `cool` - Cool color tone\n"
            "• `vibrant` or `vivid` - Vibrant colors\n"
            "• `faded` or `desaturate` - Faded/desaturated look\n"
            "• `sharp` or `sharpen` - Sharpen image\n\n"
            "**Example:**\n"
            "`/filter grayscale`\n"
            "`/filter bright`\n"
            "`/filter invert`"
        )
        return
    
    try:
        # Get image from message or reply
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        filter_names = {
            'grayscale': 'Grayscale',
            'sepia': 'Sepia',
            'vintage': 'Vintage',
            'bright': 'Bright',
            'dark': 'Dark',
            'contrast': 'High Contrast',
            'saturate': 'Saturated',
            'invert': 'Inverted',
            'warm': 'Warm',
            'cool': 'Cool',
            'vibrant': 'Vibrant',
            'faded': 'Faded',
            'sharp': 'Sharpened'
        }
        
        processing_msg = await update.message.reply_text(f"🎨 Applying {filter_names[filter_type]} filter...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def apply_filter(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                # Download image
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                width, height = img.size
                
                # Apply filter based on type
                if filter_type == 'grayscale':
                    # Grayscale filter
                    filtered_img = img.convert('L').convert('RGB')
                    
                elif filter_type == 'sepia':
                    # Sepia filter - apply brown vintage tone
                    filtered_img = img.copy()
                    pixels = filtered_img.load()
                    
                    for y in range(height):
                        for x in range(width):
                            r, g, b = pixels[x, y]
                            
                            # Sepia formula
                            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                            
                            # Clamp values to 0-255
                            tr = min(255, max(0, tr))
                            tg = min(255, max(0, tg))
                            tb = min(255, max(0, tb))
                            
                            pixels[x, y] = (tr, tg, tb)
                    
                elif filter_type == 'vintage':
                    # Vintage filter - combination of sepia + slight contrast/desaturation
                    filtered_img = img.copy()
                    pixels = filtered_img.load()
                    
                    for y in range(height):
                        for x in range(width):
                            r, g, b = pixels[x, y]
                            
                            # Vintage effect: sepia + slight desaturation + slight darkening
                            # Sepia tone
                            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                            
                            # Add slight darkening and contrast
                            tr = int(tr * 0.9)  # Slight darkening
                            tg = int(tg * 0.88)
                            tb = int(tb * 0.85)
                            
                            # Add slight yellow tint (vintage look)
                            tr = min(255, int(tr * 1.05))
                            tg = min(255, int(tg * 1.02))
                            tb = min(255, int(tb * 0.95))
                            
                            # Clamp values
                            tr = min(255, max(0, tr))
                            tg = min(255, max(0, tg))
                            tb = min(255, max(0, tb))
                            
                            pixels[x, y] = (tr, tg, tb)
                            
                elif filter_type == 'bright':
                    # Bright filter - brighten the image
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Brightness(img)
                    filtered_img = enhancer.enhance(1.5)  # 50% brighter
                    
                elif filter_type == 'dark':
                    # Dark filter - darken the image
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Brightness(img)
                    filtered_img = enhancer.enhance(0.6)  # 40% darker
                    
                elif filter_type == 'contrast':
                    # High contrast filter
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Contrast(img)
                    filtered_img = enhancer.enhance(1.8)  # 80% more contrast
                    
                elif filter_type == 'saturate':
                    # Increase color saturation
                    from PIL import ImageEnhance
                    enhancer = ImageEnhance.Color(img)
                    filtered_img = enhancer.enhance(1.6)  # 60% more saturation
                    
                elif filter_type == 'invert':
                    # Invert/Negative filter
                    from PIL import ImageOps
                    filtered_img = ImageOps.invert(img)
                    
                elif filter_type == 'warm':
                    # Warm filter - add warm tones (orange/yellow)
                    filtered_img = img.copy()
                    pixels = filtered_img.load()
                    
                    for y in range(height):
                        for x in range(width):
                            r, g, b = pixels[x, y]
                            
                            # Add warm tones (increase red and yellow)
                            tr = min(255, int(r * 1.2))
                            tg = min(255, int(g * 1.1))
                            tb = max(0, int(b * 0.9))
                            
                            pixels[x, y] = (tr, tg, tb)
                    
                elif filter_type == 'cool':
                    # Cool filter - add cool tones (blue/cyan)
                    filtered_img = img.copy()
                    pixels = filtered_img.load()
                    
                    for y in range(height):
                        for x in range(width):
                            r, g, b = pixels[x, y]
                            
                            # Add cool tones (increase blue, decrease red)
                            tr = max(0, int(r * 0.9))
                            tg = min(255, int(g * 1.05))
                            tb = min(255, int(b * 1.15))
                            
                            pixels[x, y] = (tr, tg, tb)
                    
                elif filter_type == 'vibrant':
                    # Vibrant filter - increase saturation and contrast
                    from PIL import ImageEnhance
                    # First increase saturation
                    color_enhancer = ImageEnhance.Color(img)
                    filtered_img = color_enhancer.enhance(1.5)
                    # Then increase contrast
                    contrast_enhancer = ImageEnhance.Contrast(filtered_img)
                    filtered_img = contrast_enhancer.enhance(1.3)
                    
                elif filter_type == 'faded':
                    # Faded filter - desaturate and reduce contrast
                    from PIL import ImageEnhance
                    # First desaturate
                    color_enhancer = ImageEnhance.Color(img)
                    filtered_img = color_enhancer.enhance(0.5)  # 50% less saturation
                    # Then reduce contrast
                    contrast_enhancer = ImageEnhance.Contrast(filtered_img)
                    filtered_img = contrast_enhancer.enhance(0.7)  # 30% less contrast
                    
                elif filter_type == 'sharp':
                    # Sharpen filter
                    from PIL import ImageFilter
                    filtered_img = img.filter(ImageFilter.SHARPEN)
                    # Apply additional sharpening
                    try:
                        filtered_img = filtered_img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
                    except:
                        # Fallback if UnsharpMask not available
                        filtered_img = filtered_img.filter(ImageFilter.SHARPEN)
                
                # Save to buffer
                output_buffer = io.BytesIO()
                filtered_img.save(output_buffer, format='PNG', quality=95)
                output_buffer.seek(0)
                return output_buffer
            except Exception as e:
                logger.error(f"Filter processing error: {e}", exc_info=True)
                raise
        
        filtered_image = await loop.run_in_executor(None, apply_filter, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_photo(
            photo=filtered_image,
            caption=f"🎨 **{filter_names[filter_type]} Filter Applied**\n\n"
                   f"✨ Filter: `{filter_type}`",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        logger.error(f"Filter command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ **Error:** {str(e)}\n\n"
            "💡 Please try again or check your command format."
        )

async def bgblur_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blur only the background of an image, keeping foreground sharp."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Background blur feature requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please send an image or reply to an image message!\n"
            "Example: Reply to an image with /bgblur\n"
            "This will blur the background while keeping the subject sharp."
        )
        return
    
    try:
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text("🎨 Blurring background (keeping subject sharp)...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def process_bgblur(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                img = img.convert('RGB')
                width, height = img.size
                
                # Create blurred version
                blurred_img = img.filter(ImageFilter.GaussianBlur(radius=10))
                
                # Create mask - keep foreground (subject) sharp, blur background
                # Strategy: Use edge detection + color analysis to identify subject
                if NUMPY_AVAILABLE:
                    # Edge detection using PIL filter
                    edge_img = img.convert('L').filter(ImageFilter.FIND_EDGES)
                    edge_array = np.array(edge_img)
                    
                    # Create mask based on edge density and position
                    # Subject is usually in center-upper area with more edges
                    mask_array = np.zeros((height, width), dtype=np.uint8)
                    
                    # Method 1: Edge-based detection
                    # Areas with more edges are likely to be subject
                    edge_threshold = np.percentile(edge_array, 60)
                    edge_mask = edge_array > edge_threshold
                    
                    # Method 2: Center-biased (subject is usually in center)
                    y_coords, x_coords = np.ogrid[:height, :width]
                    center_x, center_y = width // 2, height // 2
                    
                    # Create distance from center (normalized)
                    dist_x = np.abs(x_coords - center_x) / (width / 2)
                    dist_y = np.abs(y_coords - center_y) / (height / 2)
                    dist_from_center = np.sqrt(dist_x**2 + dist_y**2)
                    
                    # Method 3: Bottom area is usually background
                    # Assume bottom 25% is likely background
                    bottom_threshold = height * 0.75
                    is_bottom = y_coords > bottom_threshold
                    
                    # Combine methods to create mask
                    # Subject = high edges + center area + not bottom
                    subject_score = (
                        (edge_mask.astype(float) * 0.4) +  # Edge importance
                        ((1 - np.clip(dist_from_center, 0, 1)) * 0.4) +  # Center importance
                        ((1 - is_bottom.astype(float)) * 0.2)  # Not bottom importance
                    )
                    
                    # Normalize and threshold
                    subject_score = (subject_score - subject_score.min()) / (subject_score.max() - subject_score.min() + 1e-8)
                    
                    # Threshold: keep top 50% as subject
                    threshold = np.percentile(subject_score, 50)
                    mask_array = (subject_score > threshold).astype(np.uint8) * 255
                    
                    # Expand subject area slightly to avoid cutting edges
                    # Use simple numpy-based expansion if scipy not available
                    try:
                        from scipy import ndimage
                        mask_array = ndimage.binary_dilation(mask_array > 0, iterations=3).astype(np.uint8) * 255
                    except (ImportError, ModuleNotFoundError):
                        # If scipy not available, use optimized numpy-based expansion
                        # Create expanded mask by shifting and ORing
                        expanded_mask = mask_array.copy()
                        # Expand horizontally and vertically
                        for shift in range(1, 4):
                            # Shift left, right, up, down and combine
                            expanded_mask = np.maximum(expanded_mask, np.roll(mask_array, shift, axis=1))
                            expanded_mask = np.maximum(expanded_mask, np.roll(mask_array, -shift, axis=1))
                            expanded_mask = np.maximum(expanded_mask, np.roll(mask_array, shift, axis=0))
                            expanded_mask = np.maximum(expanded_mask, np.roll(mask_array, -shift, axis=0))
                        mask_array = expanded_mask
                    except Exception:
                        # If any error, skip expansion
                        pass
                    
                    mask = Image.fromarray(mask_array, mode='L')
                    
                elif IMAGEDRAW_AVAILABLE:
                    # Fallback: Use edge detection + center area
                    mask = Image.new('L', (width, height), 0)
                    
                    # Get edge image
                    gray = img.convert('L')
                    edge_img = gray.filter(ImageFilter.FIND_EDGES)
                    
                    # Create mask: subject is in center with edges
                    draw = ImageDraw.Draw(mask)
                    
                    # Draw ellipse in center (subject area)
                    center_x, center_y = width // 2, height // 2
                    ellipse_width = int(width * 0.7)
                    ellipse_height = int(height * 0.8)
                    
                    # Create ellipse but exclude bottom 20%
                    ellipse_top = max(0, center_y - ellipse_height // 2)
                    ellipse_bottom = min(height * 0.8, center_y + ellipse_height // 2)
                    
                    draw.ellipse([
                        center_x - ellipse_width // 2,
                        ellipse_top,
                        center_x + ellipse_width // 2,
                        ellipse_bottom
                    ], fill=255)
                    
                    # Also mark areas with high edge density
                    edge_pixels = edge_img.load()
                    mask_pixels = mask.load()
                    edge_threshold = 50  # Threshold for edge detection
                    
                    for y in range(height):
                        for x in range(width):
                            if edge_pixels[x, y] > edge_threshold:
                                # If near center, keep it
                                dist_x = abs(x - center_x) / (width / 2)
                                dist_y = abs(y - center_y) / (height / 2)
                                if dist_x < 0.6 and dist_y < 0.7 and y < height * 0.85:
                                    mask_pixels[x, y] = 255
                else:
                    # Simple fallback: center area only
                    mask = Image.new('L', (width, height), 0)
                    center_x, center_y = width // 2, height // 2
                    radius = min(width, height) * 0.4
                    
                    for y in range(height):
                        for x in range(width):
                            dist = ((x - center_x)**2 + (y - center_y)**2)**0.5
                            # Keep center area, exclude bottom
                            if dist < radius and y < height * 0.8:
                                mask.putpixel((x, y), 255)
                            elif dist < radius * 1.2 and y < height * 0.8:
                                fade = 1 - (dist - radius) / (radius * 0.2)
                                mask.putpixel((x, y), int(255 * fade))
                
                # Smooth the mask edges
                mask = mask.filter(ImageFilter.GaussianBlur(radius=20))
                
                # Apply mask: 255 = keep sharp (subject), 0 = blur (background)
                if NUMPY_AVAILABLE:
                    img_array = np.array(img, dtype=np.float32)
                    blurred_array = np.array(blurred_img, dtype=np.float32)
                    mask_array = np.array(mask, dtype=np.float32) / 255.0
                    
                    # Expand mask to 3D if needed
                    if len(img_array.shape) == 3:
                        mask_array = np.expand_dims(mask_array, axis=2)
                    
                    # Blend: mask=1 (white/subject) = sharp, mask=0 (black/background) = blurred
                    result_array = img_array * mask_array + blurred_array * (1 - mask_array)
                    result_img = Image.fromarray(result_array.astype(np.uint8))
                else:
                    # PIL composite: mask=white keeps original (sharp), mask=black uses blurred
                    result_img = Image.composite(img, blurred_img, mask)
                
                output_buffer = io.BytesIO()
                if result_img.mode != 'RGB':
                    result_img = result_img.convert('RGB')
                result_img.save(output_buffer, format='PNG', quality=95)
                output_buffer.seek(0)
                
                if len(output_buffer.getvalue()) == 0:
                    raise Exception("Failed to generate output image")
                
                return output_buffer
            except Exception as e:
                logger.error(f"Background blur processing error: {e}", exc_info=True)
                raise
        
        result_image = await loop.run_in_executor(None, process_bgblur, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        result_image.seek(0, 2)
        buffer_size = result_image.tell()
        result_image.seek(0)
        
        if buffer_size == 0:
            raise Exception("Enhanced image buffer is empty")
        
        await update.message.reply_photo(
            photo=result_image,
            caption="🎨 Background blurred (subject kept sharp)"
        )
    
    except Exception as e:
        logger.error(f"Background blur command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ Error: {str(e)}. Please try again."
        )

def unsharp_mask(image, radius=2, percent=150, threshold=3):
    """Apply unsharp mask filter for professional sharpening."""
    try:
        # Use Pillow's built-in UnsharpMask if available
        try:
            return image.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))
        except (AttributeError, TypeError):
            pass
        
        # Fallback: Manual unsharp mask
        # Apply Gaussian blur
        blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
        
        # Apply unsharp mask formula: original + (original - blurred) * percent / 100
        if NUMPY_AVAILABLE:
            original_array = np.array(image, dtype=np.float32)
            blurred_array = np.array(blurred, dtype=np.float32)
            diff = original_array - blurred_array
            enhanced_array = original_array + (diff * percent / 100.0)
            enhanced_array = np.clip(enhanced_array, 0, 255)
            return Image.fromarray(enhanced_array.astype(np.uint8))
        else:
            # Pixel-by-pixel fallback
            enhanced = image.copy()
            width, height = image.size
            for y in range(height):
                for x in range(width):
                    orig = image.getpixel((x, y))
                    blur = blurred.getpixel((x, y))
                    if isinstance(orig, tuple):
                        new_pixel = tuple(
                            min(255, max(0, int(o + (o - b) * percent / 100)))
                            for o, b in zip(orig, blur) if isinstance(blur, tuple)
                        )
                        enhanced.putpixel((x, y), new_pixel)
                    else:
                        diff = orig - blur
                        new_val = min(255, max(0, int(orig + diff * percent / 100)))
                        enhanced.putpixel((x, y), new_val)
            return enhanced
    except Exception as e:
        logger.error(f"Unsharp mask error: {e}")
        # Final fallback: simple sharpening
        enhancer = ImageEnhance.Sharpness(image)
        return enhancer.enhance(1.5)

def professional_enhance(img):
    """Professional Remini-style auto enhancement with multiple passes."""
    try:
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        original_size = img.size
        
        # Step 1: Auto brightness and contrast correction
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.15)
        
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.25)
        
        # Step 2: Color saturation enhancement
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.18)
        
        # Step 3: Unsharp mask for detail enhancement
        try:
            img = unsharp_mask(img, radius=1.5, percent=120, threshold=3)
        except:
            # Fallback to standard sharpening
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.4)
        
        # Step 4: Additional contrast pass for depth
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.08)
        
        # Step 5: Final color balance
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.05)
        
        # Step 6: Final sharpening pass
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.2)
        
        return img
    except Exception as e:
        logger.error(f"Professional enhance error: {e}")
        return img

async def enhance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Professional Remini-style image enhancement."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image enhancement requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "✨ **Professional Image Enhancement**\n\n"
            "Usage: Reply to an image with /enhance\n\n"
            "**Features:**\n"
            "• AI-style auto enhancement\n"
            "• Professional sharpening\n"
            "• Color correction\n"
            "• Detail enhancement\n"
            "• Brightness & contrast optimization\n\n"
            "Example: Reply to image with /enhance"
        )
        return
    
    try:
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text(
            "✨ Applying professional AI-style enhancement...\n"
            "⏳ This may take a few seconds..."
        )
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def process_professional_enhance(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                original_size = img.size
                
                # Apply professional enhancement
                enhanced_img = professional_enhance(img)
                
                # Ensure high quality output
                output_buffer = io.BytesIO()
                if enhanced_img.mode != 'RGB':
                    enhanced_img = enhanced_img.convert('RGB')
                enhanced_img.save(output_buffer, format='JPEG', quality=98, optimize=True)
                output_buffer.seek(0)
                
                if len(output_buffer.getvalue()) == 0:
                    raise Exception("Failed to generate enhanced image")
                
                return output_buffer
            except Exception as e:
                logger.error(f"Professional enhance processing error: {e}", exc_info=True)
                raise
        
        result_image = await loop.run_in_executor(None, process_professional_enhance, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        result_image.seek(0, 2)
        buffer_size = result_image.tell()
        result_image.seek(0)
        
        if buffer_size == 0:
            raise Exception("Enhanced image buffer is empty")
        
        await update.message.reply_photo(
            photo=result_image,
            caption="✨ **Professional Enhanced Image**\n\n"
                   "🎨 AI-style enhancement applied:\n"
                   "• Brightness & contrast optimized\n"
                   "• Professional sharpening\n"
                   "• Color correction\n"
                   "• Detail enhancement",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        logger.error(f"Enhance command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ Error: {str(e)}. Please try again."
        )

async def resize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resize an image."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image resize requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please send an image or reply to an image message!\n"
            "Usage: Reply to an image with /resize <width>x<height>\n"
            "Example: /resize 500x500\n"
            "Example: /resize 1920x1080"
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide dimensions!\n"
            "Usage: /resize <width>x<height>\n"
            "Example: /resize 500x500"
        )
        return
    
    try:
        dimensions = ' '.join(context.args)
        if 'x' not in dimensions.lower():
            await update.message.reply_text(
                "❌ Invalid format! Use: /resize <width>x<height>\n"
                "Example: /resize 500x500"
            )
            return
        
        width, height = map(int, dimensions.lower().split('x'))
        
        if width <= 0 or height <= 0 or width > 10000 or height > 10000:
            await update.message.reply_text(
                "❌ Invalid dimensions! Width and height must be between 1 and 10000."
            )
            return
        
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text(f"📏 Resizing image to {width}x{height}...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def process_resize(file_path_url, w, h):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                resized_img = img.resize((w, h), Image.Resampling.LANCZOS)
                
                output_buffer = io.BytesIO()
                format_type = img.format if img.format else 'PNG'
                if format_type not in ['JPEG', 'PNG']:
                    format_type = 'PNG'
                if resized_img.mode != 'RGB' and format_type == 'JPEG':
                    resized_img = resized_img.convert('RGB')
                resized_img.save(output_buffer, format=format_type)
                output_buffer.seek(0)
                
                if len(output_buffer.getvalue()) == 0:
                    raise Exception("Failed to generate resized image")
                
                return output_buffer
            except Exception as e:
                logger.error(f"Resize processing error: {e}", exc_info=True)
                raise
        
        resized_image = await loop.run_in_executor(None, process_resize, file_path, width, height)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        resized_image.seek(0, 2)
        buffer_size = resized_image.tell()
        resized_image.seek(0)
        
        if buffer_size == 0:
            raise Exception("Resized image buffer is empty")
        
        await update.message.reply_photo(
            photo=resized_image,
            caption=f"📏 Resized image: {width}x{height}"
        )
    
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid dimensions format! Use: /resize <width>x<height>\n"
            "Example: /resize 500x500"
        )
    except Exception as e:
        logger.error(f"Resize command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ Error: {str(e)}. Please try again."
        )

async def tojpg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert an image to JPG format."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image to JPG requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please send an image or reply to an image message!\n"
            "Usage: Reply to an image with /tojpg"
        )
        return
    
    try:
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text("🖼️ Converting image to JPG...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            file_path = file.file_path
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def process_to_jpg(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                output_buffer = io.BytesIO()
                img.save(output_buffer, format='JPEG', quality=95, optimize=True)
                output_buffer.seek(0)
                return output_buffer
            except Exception as e:
                logger.error(f"ToJPG processing error: {e}", exc_info=True)
                raise
        
        jpg_image = await loop.run_in_executor(None, process_to_jpg, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        jpg_image.seek(0, 2)
        file_size = jpg_image.tell()
        jpg_image.seek(0)
        
        if file_size == 0:
            raise Exception("Converted JPG buffer is empty")
        
        await update.message.reply_document(
            document=jpg_image,
            filename="converted.jpg",
            caption="✅ Converted to JPG"
        )
    except Exception as e:
        logger.error(f"ToJPG command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            f"❌ Error: {str(e)}. Please try again."
        )

async def sticker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert an image to Telegram sticker format."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Sticker conversion requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Please send an image or reply to an image message!\n\n"
            "💡 **Usage:**\n"
            "• Reply to an image with /sticker\n"
            "• Or send an image and use /sticker in the caption\n\n"
            "📝 **Note:** Stickers must be:\n"
            "• Maximum size: 512x512 pixels\n"
            "• Maximum file size: 512KB\n"
            "• PNG or WebP format"
        )
        return
    
    try:
        # Get image from message or reply
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text("🎨 Converting image to sticker...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            # Build a fully-qualified Telegram file URL
            if file.file_path and str(file.file_path).startswith('http'):
                file_path = file.file_path
            else:
                file_path = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def process_to_sticker(file_path_url):
            try:
                if not PIL_AVAILABLE:
                    raise ImportError("PIL not available")
                
                img_buffer = io.BytesIO()
                response = requests.get(file_path_url, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                img_buffer.write(response.content)
                img_buffer.seek(0)
                
                img = Image.open(img_buffer)
                
                # Get original dimensions
                original_width, original_height = img.size
                
                # Calculate new dimensions (max 512x512, maintain aspect ratio)
                max_size = 512
                if original_width > max_size or original_height > max_size:
                    ratio = min(max_size / original_width, max_size / original_height)
                    new_width = int(original_width * ratio)
                    new_height = int(original_height * ratio)
                else:
                    new_width = original_width
                    new_height = original_height
                
                # Resize image
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to RGBA for transparency support
                if img.mode != 'RGBA':
                    # Create RGBA image with white background if no transparency
                    rgba_img = Image.new('RGBA', img.size, (255, 255, 255, 255))
                    if img.mode == 'RGB':
                        rgba_img.paste(img, (0, 0))
                    else:
                        rgba_img.paste(img.convert('RGB'), (0, 0))
                    img = rgba_img
                
                # Save as PNG with optimization
                output_buffer = io.BytesIO()
                img.save(output_buffer, format='PNG', optimize=True)
                output_buffer.seek(0)
                
                # Check file size and compress if needed (max 512KB)
                file_size = len(output_buffer.getvalue())
                max_file_size = 512 * 1024  # 512KB
                
                if file_size > max_file_size:
                    # Try to compress by reducing quality/resizing more
                    quality = 95
                    while file_size > max_file_size and quality > 50:
                        quality -= 5
                        # Resize slightly more if still too large
                        if quality < 70:
                            new_width = int(new_width * 0.9)
                            new_height = int(new_height * 0.9)
                            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        
                        output_buffer = io.BytesIO()
                        img.save(output_buffer, format='PNG', optimize=True, compress_level=9)
                        output_buffer.seek(0)
                        file_size = len(output_buffer.getvalue())
                    
                    # If still too large, resize more aggressively
                    if file_size > max_file_size:
                        scale_factor = 0.8
                        while file_size > max_file_size and scale_factor > 0.5:
                            new_width = int(new_width * scale_factor)
                            new_height = int(new_height * scale_factor)
                            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            
                            output_buffer = io.BytesIO()
                            img.save(output_buffer, format='PNG', optimize=True, compress_level=9)
                            output_buffer.seek(0)
                            file_size = len(output_buffer.getvalue())
                            scale_factor -= 0.1
                
                output_buffer.seek(0)
                return output_buffer
            except Exception as e:
                logger.error(f"Sticker processing error: {e}", exc_info=True)
                raise
        
        sticker_image = await loop.run_in_executor(None, process_to_sticker, file_path)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        sticker_image.seek(0, 2)
        buffer_size = sticker_image.tell()
        sticker_image.seek(0)
        
        if buffer_size == 0:
            raise Exception("Sticker image buffer is empty")
        
        # Send as sticker
        try:
            await update.message.reply_sticker(sticker=sticker_image)
        except Exception as sticker_error:
            # If sending as sticker fails, try sending as document
            logger.warning(f"Failed to send as sticker: {sticker_error}")
            sticker_image.seek(0)
            await update.message.reply_document(
                document=sticker_image,
                filename="sticker.png",
                caption="✅ Image converted to sticker format\n\n"
                       "💡 Note: This is a PNG file. To use as a sticker, "
                       "you can add it to your sticker pack using @Stickers bot."
            )
    
    except Exception as e:
        logger.error(f"Sticker command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        error_msg = str(e)
        if "file is too big" in error_msg.lower() or "file_size" in error_msg.lower():
            await update.message.reply_text(
                "❌ Error: Image file is too large!\n\n"
                "💡 **Tips:**\n"
                "• Use a smaller image\n"
                "• Stickers must be under 512KB\n"
                "• Maximum dimensions: 512x512 pixels"
            )
        else:
            await update.message.reply_text(
                f"❌ Error: {str(e)}\n\n"
                "Please try again with a different image."
            )

def detect_language(text):
    """Detect if text contains Bengali characters."""
    bengali_chars = '\u0980-\u09FF'
    if re.search(f'[{bengali_chars}]', text):
        return 'bn'
    return 'en'

async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search Wikipedia for a topic."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a topic to search!\n"
            "Example: /wiki Python programming\n"
            "Example: /wiki বাংলা"
        )
        return
    
    query = ' '.join(context.args)
    lang = detect_language(query)
    lang_name = "বাংলা" if lang == 'bn' else "English"
    
    processing_msg = await update.message.reply_text(f"🔍 Searching Wikipedia ({lang_name}) for: {query}...")
    
    try:
        search_result = search_wikipedia(query, lang=lang)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        if search_result:
            title = search_result.get('title', query)
            extract = search_result.get('extract', 'No summary available.')
            url = search_result.get('content_urls', {}).get('desktop', {}).get('page', '')
            
            if len(extract) > 3000:
                extract = extract[:3000] + "..."
            
            wiki_text = (
                f'📚 **Wikipedia: {title}**\n\n'
                f'{extract}\n\n'
            )
            
            if url:
                wiki_text += f'📖 [Read more on Wikipedia]({url})'
            
            await update.message.reply_text(wiki_text, parse_mode='Markdown', disable_web_page_preview=False)
        else:
            await update.message.reply_text(
                f"❌ Sorry, I couldn't find information about '{query}' on Wikipedia.\n"
                "Please try a different search term or check the spelling."
            )
    
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ Sorry, I encountered an error while searching Wikipedia. "
            "Please try again later."
        )

def search_wikipedia(query, lang='en'):
    """Search Wikipedia and return summary in specified language."""
    headers = {
        'User-Agent': 'TelegramBot/1.0 (https://t.me/yourbot; contact@example.com)'
    }
    
    try:
        clean_query = query.strip()
        logger.info(f"Wikipedia search for: {clean_query} (language: {lang})")
        
        if lang == 'bn':
            wiki_domain = "bn.wikipedia.org"
        else:
            wiki_domain = "en.wikipedia.org"
        
        search_api_url = f"https://{wiki_domain}/w/api.php"
        base_url = f"https://{wiki_domain}/api/rest_v1/page/summary/"
        
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'search',
            'srsearch': clean_query,
            'srlimit': 1,
            'srprop': 'snippet'
        }
        
        try:
            search_resp = requests.get(search_api_url, params=params, headers=headers, timeout=10)
            logger.info(f"Search API status: {search_resp.status_code} (lang: {lang})")
            
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                searches = search_data.get('query', {}).get('search', [])
                
                if searches and len(searches) > 0:
                    page_title = searches[0]['title']
                    logger.info(f"Found page: {page_title}")
                    
                    page_title_formatted = page_title.replace(' ', '_')
                    encoded_title = quote(page_title_formatted, safe='')
                    summary_url = base_url + encoded_title
                    
                    summary_resp = requests.get(summary_url, headers=headers, timeout=10)
                    logger.info(f"Summary API status: {summary_resp.status_code}")
                    
                    if summary_resp.status_code == 200:
                        data = summary_resp.json()
                        result = {
                            'title': data.get('title', page_title),
                            'extract': data.get('extract', 'No summary available.'),
                            'content_urls': data.get('content_urls', {})
                        }
                        logger.info(f"Successfully retrieved: {result.get('title')}")
                        return result
        except Exception as e:
            logger.error(f"Search API error: {e}")
        
        if lang == 'en':
            formatted_title = clean_query.title().replace(' ', '_')
            encoded_title1 = quote(formatted_title, safe='')
            url1 = base_url + encoded_title1
            
            try:
                resp1 = requests.get(url1, headers=headers, timeout=10)
                if resp1.status_code == 200:
                    data = resp1.json()
                    logger.info(f"Direct access success: {formatted_title}")
                    return {
                        'title': data.get('title', clean_query),
                        'extract': data.get('extract', 'No summary available.'),
                        'content_urls': data.get('content_urls', {})
                    }
            except Exception as e:
                logger.error(f"Direct access error 1: {e}")
        
        logger.warning(f"Wikipedia search failed for: {clean_query} (lang: {lang})")
        return None
        
    except requests.exceptions.Timeout:
        logger.error("Wikipedia API timeout")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Wikipedia API request error: {e}")
        return None
    except Exception as e:
        logger.error(f"Wikipedia search unexpected error: {e}", exc_info=True)
        return None

def calculate_math(expression, show_steps=False):
    """Safely calculate math expression with advanced features."""
    try:
        # Expanded allowed characters for all math functions
        allowed_chars = set('0123456789+-*/.()sqrtpowloglnexpabsasinacosatansinhcoshtanhasinacosatanhdeg2radrad2degfactorialgcdlcmceilfloorroundlog10log2tau ')
        
        # Check if expression contains only allowed characters
        if not all(c in allowed_chars or c.isalpha() or c in '%,' for c in expression):
            return None
        
        steps = []
        original_expr = expression
        
        # Replace common patterns
        expression = expression.replace('sqrt', 'math.sqrt')
        expression = expression.replace('**', '**')
        expression = expression.replace('^', '**')
        expression = expression.replace('pi', str(math.pi))
        expression = expression.replace('e', str(math.e))
        expression = expression.replace('tau', str(math.tau))
        expression = expression.replace('E', str(math.e))
        
        # Helper functions
        def factorial(n):
            if n < 0 or n != int(n):
                raise ValueError("Factorial only for non-negative integers")
            return math.factorial(int(n))
        
        def gcd_func(a, b):
            return math.gcd(int(a), int(b))
        
        def lcm_func(a, b):
            return abs(int(a) * int(b)) // math.gcd(int(a), int(b)) if a and b else 0
        
        def log10_func(x):
            return math.log10(x)
        
        def log2_func(x):
            return math.log2(x)
        
        def deg2rad_func(x):
            return math.radians(x)
        
        def rad2deg_func(x):
            return math.degrees(x)
        
        safe_dict = {
            "__builtins__": {},
            "math": math,
            "abs": abs,
            "pow": pow,
            "sqrt": math.sqrt,
            "exp": math.exp,
            "log": math.log,
            "log10": log10_func,
            "log2": log2_func,
            # Trigonometric functions
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            # Hyperbolic functions
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "asinh": math.asinh,
            "acosh": math.acosh,
            "atanh": math.atanh,
            # Rounding functions
            "ceil": math.ceil,
            "floor": math.floor,
            "round": round,
            # Other functions
            "factorial": factorial,
            "gcd": gcd_func,
            "lcm": lcm_func,
            "deg2rad": deg2rad_func,
            "rad2deg": rad2deg_func,
            # Constants
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
        }
        
        result = eval(expression, safe_dict)
        
        if isinstance(result, float):
            if abs(result) < 1e-10:
                return 0
            if show_steps:
                return (0, [f"{original_expr} = {result}"])
            return round(result, 10) if result != int(result) else int(result)
        
        if show_steps:
            return (result, [f"{original_expr} = {result}"])
        return result
        
    except Exception as e:
        logger.error(f"Math calculation error: {e}")
        return None

def is_math_expression(text):
    """Check if text is a math expression."""
    text_lower = text.lower()
    has_numbers = bool(re.search(r'\d', text))
    
    # Expanded list of math functions and operators
    math_keywords = [
        'sqrt', 'pow', 'log', 'ln', 'exp', 'sin', 'cos', 'tan', 
        'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh',
        'factorial', 'gcd', 'lcm', 'ceil', 'floor', 'round',
        'log10', 'log2', 'deg2rad', 'rad2deg', 'pi', 'e', 'tau'
    ]
    
    has_math_keyword = any(keyword in text_lower for keyword in math_keywords)
    has_operators = bool(re.search(r'[\+\-\*\/\^%]', text)) or has_math_keyword
    
    if len(text) > 200:  # Increased limit for complex expressions
        return False
    
    if not has_numbers and not has_math_keyword:
        return False
    
    # Expanded math characters
    math_chars = sum(1 for c in text if c in '0123456789+-*/.()^%sqrtpowloglnxpiasincoshtaufactorialgcdlcmceilfloor ')
    math_ratio = math_chars / len(text) if len(text) > 0 else 0
    
    return has_operators and (math_ratio > 0.5 or has_math_keyword)

def looks_like_image_prompt(text):
    """Check if text looks like an image generation prompt."""
    text_lower = text.lower().strip()
    
    # Image generation keywords
    image_keywords = [
        'a ', 'an ', 'the ', 'create ', 'generate ', 'make ', 'draw ', 'show ', 'picture ',
        'image ', 'photo ', 'portrait ', 'landscape ', 'sunset ', 'sunrise ', 'cat ', 'dog ',
        'beautiful ', 'cute ', 'futuristic ', 'abstract ', 'digital ', 'art ', 'painting ',
        'scene ', 'view ', 'mountain ', 'ocean ', 'forest ', 'city ', 'building ', 'sky ',
        'cloud ', 'flower ', 'bird ', 'animal ', 'person ', 'character ', 'design ', 'style '
    ]
    
    # Check if text contains image-related keywords
    keyword_count = sum(1 for keyword in image_keywords if keyword in text_lower)
    
    # If text is longer than 10 characters and has image keywords, likely an image prompt
    if len(text) > 10 and keyword_count > 0:
        return True
    
    # If text starts with common image prompt patterns
    if any(text_lower.startswith(prefix) for prefix in ['a ', 'an ', 'the ', 'create ', 'generate ', 'make ', 'show ']):
        return True
    
    # If text is descriptive (not a question, not a command, has adjectives)
    descriptive_words = ['beautiful', 'cute', 'amazing', 'stunning', 'colorful', 'bright', 'dark', 'vibrant']
    if any(word in text_lower for word in descriptive_words) and len(text) > 15:
        return True
    
    return False

async def text_to_speech(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smart text handler - auto-detect if it's image generation or text-to-speech."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    try:
        text = update.message.text.strip()
        
        # Handle custom keyboard button clicks - directly execute commands
        if text == "🌐 Web Clone":
            await clone_website_command(update, context)
            return
        elif text == "🎨 Generate":
            await generate_command(update, context)
            return
        elif text == "🏗️ Build":
            await build_website_command(update, context)
            return
        elif text == "🔐 Password":
            await password_command(update, context)
            return
        elif text == "📱 QR Code":
            await qr_command(update, context)
            return
        elif text == "📊 Calculator":
            await calc_command(update, context)
            return
        elif text == "📺 YouTube":
            await youtube_download_command(update, context)
            return
        elif text == "🎵 TikTok":
            await tiktok_download_command(update, context)
            return
        elif text == "📷 Instagram":
            await instagram_download_command(update, context)
            return
        elif text == "📘 Facebook":
            await facebook_download_command(update, context)
            return
        elif text == "🖼️ Blur":
            await blur_command(update, context)
            return
        elif text == "🎨 Filters":
            await update.message.reply_text(
                "🎨 **Image Filters**\n\n"
                "**Usage:** Reply to an image with:\n"
                "`/filter <type>`\n\n"
                "**Available Filters:**\n"
                "• `grayscale` or `gray` - Black & white\n"
                "• `sepia` - Vintage brown tone\n"
                "• `vintage` - Old photo effect\n"
                "• `bright` or `brighten` - Brighten image\n"
                "• `dark` or `darken` - Darken image\n"
                "• `contrast` - Increase contrast\n"
                "• `saturate` or `saturation` - Increase color saturation\n"
                "• `invert` or `negative` - Negative/invert colors\n"
                "• `warm` - Warm color tone\n"
                "• `cool` - Cool color tone\n"
                "• `vibrant` or `vivid` - Vibrant colors\n"
                "• `faded` or `desaturate` - Faded/desaturated look\n"
                "• `sharp` or `sharpen` - Sharpen image\n\n"
                "**Example:**\n"
                "`/filter grayscale`\n"
                "`/filter bright`\n"
                "`/filter invert`",
                parse_mode='Markdown'
            )
            return
        elif text == "🔄 Resize":
            await resize_command(update, context)
            return
        elif text == "🌐 Translate":
            await translate_command(update, context)
            return
        elif text == "💧 Watermark":
            await update.message.reply_text(
                "💧 **Image Watermark**\n\n"
                "**Usage:** Reply to an image with:\n"
                "`/watermark <text> [position]`\n\n"
                "**Positions:**\n"
                "• `center` - Center of image\n"
                "• `top-left`, `top-right`\n"
                "• `bottom-left`, `bottom-right`\n"
                "• `top`, `bottom`\n\n"
                "**Example:**\n"
                "`/watermark @MyBrand center`\n"
                "`/watermark Copyright 2024 bottom-right`",
                parse_mode='Markdown'
            )
            return
        elif text == "📱 Device Info":
            await deviceinfo_command(update, context)
            return
        elif text == "📄 OCR":
            await ocr_command(update, context)
            return
        elif text == "✨ Enhance":
            await enhance_command(update, context)
            return
        elif text == "ℹ️ Help":
            await help_command(update, context)
            return
        elif text == "📅 Calendar":
            await calendar_command(update, context)
            return
        elif text == "🎂 Birthday":
            await birthday_command(update, context)
            return
        elif text == "🔍 Wikipedia":
            await wiki_command(update, context)
            return
        elif text == "📝 Fancy Font":
            await fancyfont_command(update, context)
            return
        elif text == "🖼️ Text Image":
            await textonimage_command(update, context)
            return
        elif text == "📅 Leap Year":
            await leapyear_command(update, context)
            return
        elif text == "🔄 Referral":
            await refer_command(update, context)
            return
        elif text == "⏰ Time":
            await time_command(update, context)
            return
        elif text == "📆 Date":
            await date_command(update, context)
            return
        elif text == "⏰ Alarm":
            await alarm_command(update, context)
            return
        elif text == "📋 Repeat":
            await repeat_command(update, context)
            return
        elif text == "🎭 Emoji":
            await texttoemoji_command(update, context)
            return
        elif text == "📄 PDF Tools":
            await update.message.reply_text(
                "📄 **PDF Tools**\n\n"
                "**Available Commands:**\n"
                "• `/imagetopdf` - Convert images to PDF\n"
                "• `/pdftoimage` - Convert PDF to images\n\n"
                "**Usage:**\n"
                "• Reply to image(s) with `/imagetopdf`\n"
                "• Reply to PDF with `/pdftoimage`",
                parse_mode='Markdown'
            )
            return
        elif text == "🎵 MP3":
            await update.message.reply_text(
                "🎵 **MP3 Converter**\n\n"
                "**Usage:** Send a video file directly or reply to video with:\n"
                "`/mp4tomp3`\n\n"
                "**Supported Formats:**\n"
                "• MP4, AVI, MOV, MKV, etc.\n\n"
                "💡 Just send the video file and it will be converted!",
                parse_mode='Markdown'
            )
            return
        elif text == "🖼️ Image to PDF":
            await imagetopdf_command(update, context)
            return
        elif text == "📄 PDF to Image":
            await pdftoimage_command(update, context)
            return
        elif text == "🔄 Background Blur":
            await bgblur_command(update, context)
            return
        elif text == "📸 Image to JPG":
            await tojpg_command(update, context)
            return
        elif text == "🎨 Sticker":
            await sticker_command(update, context)
            return
        elif text == "🔀 Remove Duplicates":
            await update.message.reply_text(
                "🔀 **Remove Duplicates**\n\n"
                "**Usage:**\n"
                "• Reply to a message with: `/removeduplicates`\n"
                "• Or send: `/removeduplicates line1\nline2\nline1`\n\n"
                "**Example:**\n"
                "Reply to a message containing:\n"
                "```\nline1\nline2\nline1\nline3\n```\n\n"
                "With: `/removeduplicates`\n\n"
                "**Output:**\n"
                "```\nline1\nline2\nline3\n```",
                parse_mode='Markdown'
            )
            return
        elif text == "🔐 Hash Generator":
            await hash_command(update, context)
            return
        elif text == "🔗 URL Shortener":
            await shorturl_command(update, context)
            return
        elif text == "📸 Screenshot":
            await screenshot_command(update, context)
            return
        elif text == "🌐 IP Lookup":
            await ip_lookup_command(update, context)
            return
        elif text == "💰 Crypto Price":
            await crypto_command(update, context)
            return
        elif text == "🎤 Audio to Text":
            await update.message.reply_text(
                "🎤 **Audio to Text**\n\n"
                "**Usage:**\n"
                "• Send a voice message or audio file\n"
                "• Or reply to a voice/audio message with `/audiototext`\n\n"
                "**Language Support:**\n"
                "• `/audiototext` - Default: Bangla (bn-BD)\n"
                "• `/audiototext bn` - Bangla/Bengali\n"
                "• `/audiototext en` - English\n"
                "• `/audiototext hi` - Hindi\n"
                "• `/audiototext ar` - Arabic\n"
                "• `/audiototext es` - Spanish\n"
                "• `/audiototext fr` - French\n\n"
                "**Example:**\n"
                "Send a voice message directly, or:\n"
                "Reply to a voice message with: `/audiototext bn`"
            )
            return
        
        if not text or len(text.strip()) == 0:
            await update.message.reply_text("Please send me some text!")
            return
        
        # Check if it's a math expression
        if is_math_expression(text):
            result = calculate_math(text)
            if result is not None:
                await update.message.reply_text(
                    f'📊 **Math Calculation:**\n\n'
                    f'Expression: `{text}`\n'
                    f'Result: **{result}**\n\n'
                    f'💡 Send text to create image or convert to speech!',
                    parse_mode='Markdown'
                )
                return
        
        # Check if text looks like an image generation prompt
        if looks_like_image_prompt(text):
            # Automatically generate image from text
            await auto_generate_image(update, text)
            return
        
        # Otherwise, convert to speech
        if len(text) > 5000:
            await update.message.reply_text("Text is too long! Please send text shorter than 5000 characters.")
            return
        
        processing_msg = await update.message.reply_text("🎙️ Converting text to speech...")
        
        loop = asyncio.get_event_loop()
        
        def generate_speech():
            tts = gTTS(text=text, lang='en', slow=False)
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            return audio_buffer
        
        audio_buffer = await loop.run_in_executor(None, generate_speech)
        
        await update.message.reply_audio(
            audio=audio_buffer,
            filename="speech.mp3",
            title="Text to Speech",
            performer="TTS Bot"
        )
        
        try:
            await processing_msg.delete()
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in text_to_speech: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Sorry, I encountered an error. "
            "Please try again later."
        )

async def auto_generate_image(update: Update, prompt: str):
    """Automatically generate image from text prompt."""
    try:
        if len(prompt) > 500:
            await update.message.reply_text(
                "❌ Prompt is too long! Please keep it under 500 characters."
            )
            return
        
        processing_msg = await update.message.reply_text(
            f"🎨 Creating image from: {prompt[:50]}{'...' if len(prompt) > 50 else ''}\n"
            f"⏳ This may take 15-30 seconds..."
        )
        
        loop = asyncio.get_event_loop()
        
        def generate_image():
            try:
                encoded_prompt = quote(prompt)
                
                api_urls = [
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true",
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&enhance=true",
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true",
                ]
                
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                last_error = None
                
                for idx, image_url in enumerate(api_urls):
                    try:
                        logger.info(f"Trying API {idx + 1}/{len(api_urls)}: {image_url[:80]}...")
                        
                        response = requests.get(image_url, timeout=90, stream=True, headers=headers, allow_redirects=True)
                        
                        logger.info(f"Response status: {response.status_code}, Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                        
                        if response.status_code == 200:
                            img_buffer = io.BytesIO()
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    img_buffer.write(chunk)
                            
                            img_buffer.seek(0)
                            buffer_size = len(img_buffer.getvalue())
                            logger.info(f"Downloaded {buffer_size} bytes")
                            
                            if buffer_size < 1000:
                                logger.warning(f"Buffer too small: {buffer_size} bytes, trying next API...")
                                continue
                            
                            if PIL_AVAILABLE:
                                img = Image.open(img_buffer)
                                img.verify()
                                img_buffer.seek(0)
                                img = Image.open(img_buffer)
                                if img.mode != 'RGB':
                                    rgb_buffer = io.BytesIO()
                                    img.convert('RGB').save(rgb_buffer, format='JPEG', quality=95)
                                    rgb_buffer.seek(0)
                                    return rgb_buffer
                                img_buffer.seek(0)
                                return img_buffer
                            else:
                                img_buffer.seek(0)
                                header = img_buffer.read(4)
                                img_buffer.seek(0)
                                if header.startswith(b'\xff\xd8') or header.startswith(b'\x89PNG') or header.startswith(b'GIF8'):
                                    return img_buffer
                                else:
                                    logger.warning(f"Invalid image header: {header}, trying next API...")
                                    continue
                    except requests.exceptions.Timeout:
                        logger.warning(f"API {idx + 1} timed out, trying next...")
                        last_error = "Request timed out"
                        continue
                    except Exception as e:
                        logger.warning(f"API {idx + 1} error: {e}, trying next...")
                        last_error = e
                        continue
                
                raise Exception(f"All image generation APIs failed. Last error: {str(last_error) if last_error else 'Unknown error'}")
            
            except Exception as e:
                logger.error(f"Image generation error: {e}", exc_info=True)
                raise
        
        image_buffer = await loop.run_in_executor(None, generate_image)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        image_buffer.seek(0, 2)
        buffer_size = image_buffer.tell()
        image_buffer.seek(0)
        
        if buffer_size == 0:
            raise Exception("Generated image buffer is empty")
        
        # Add text overlay on image if PIL is available
        if PIL_AVAILABLE:
            try:
                image_buffer.seek(0)
                img = Image.open(image_buffer)
                img = img.convert('RGB')
                
                # Add text on image
                if IMAGEDRAW_AVAILABLE:
                    from PIL import ImageFont
                    draw = ImageDraw.Draw(img)
                    width, height = img.size
                    
                    # Prepare text (split into lines if too long)
                    max_chars_per_line = 40
                    words = prompt.split()
                    lines = []
                    current_line = ""
                    
                    for word in words:
                        if len(current_line + word) <= max_chars_per_line:
                            current_line += word + " "
                        else:
                            if current_line:
                                lines.append(current_line.strip())
                            current_line = word + " "
                    if current_line:
                        lines.append(current_line.strip())
                    
                    # Limit to 3 lines max
                    if len(lines) > 3:
                        lines = lines[:3]
                    
                    # Try to use a better font, fallback to default
                    try:
                        font_size = max(24, min(width // 20, 48))
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except:
                        try:
                            font = ImageFont.load_default()
                        except:
                            font = None
                    
                    # Calculate text position (bottom center)
                    line_height = 40
                    total_text_height = len(lines) * line_height
                    y_position = height - total_text_height - 30
                    
                    # Draw semi-transparent background for text
                    if len(lines) > 0:
                        text_bg_height = total_text_height + 20
                        text_bg = Image.new('RGBA', (width, text_bg_height), (0, 0, 0, 180))
                        img.paste(text_bg, (0, y_position - 10), text_bg)
                    
                    # Draw text on image
                    for i, line in enumerate(lines):
                        text_x = width // 2
                        text_y = y_position + (i * line_height)
                        
                        # Draw text with shadow for better visibility
                        if font:
                            # Shadow
                            draw.text((text_x + 2, text_y + 2), line, fill=(0, 0, 0), font=font, anchor="mm")
                            # Main text
                            draw.text((text_x, text_y), line, fill=(255, 255, 255), font=font, anchor="mm")
                        else:
                            # Fallback without font
                            draw.text((text_x + 2, text_y + 2), line, fill=(0, 0, 0), anchor="mm")
                            draw.text((text_x, text_y), line, fill=(255, 255, 255), anchor="mm")
                    
                    # Save image with text
                    output_buffer = io.BytesIO()
                    img.save(output_buffer, format='JPEG', quality=95)
                    output_buffer.seek(0)
                    image_buffer = output_buffer
            except Exception as e:
                logger.warning(f"Failed to add text overlay: {e}, sending image without text")
                image_buffer.seek(0)
        
        image_buffer.seek(0, 2)
        buffer_size = image_buffer.tell()
        image_buffer.seek(0)
        
        if buffer_size == 0:
            raise Exception("Generated image buffer is empty")
        
        await update.message.reply_photo(
            photo=image_buffer,
            caption=f"🎨 **AI Generated Image**\n\n📝 Text: `{prompt}`",
            parse_mode='Markdown'
        )
        
        logger.info(f"Auto-generated image successfully for prompt: {prompt}")
    
    except Exception as e:
        logger.error(f"Auto generate image error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e)
        if "timeout" in error_msg.lower():
            error_msg = "Image generation took too long. Please try again."
        elif "API" in error_msg or "status" in error_msg:
            error_msg = "Image generation service is temporarily unavailable. Please try again later."
        
        await update.message.reply_text(
            f"❌ **Error generating image:**\n\n{error_msg}\n\n"
            "💡 **Try:**\n"
            "• Wait 30-60 seconds and try again\n"
            "• Use a simpler, shorter description\n"
            "• Or use `/generate <prompt>` command"
        )

async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate image from text prompt using free AI."""
    if not context.args:
        await update.message.reply_text(
            "🎨 **AI Image Generation**\n\n"
            "Usage: /generate <your prompt>\n\n"
            "**Examples:**\n"
            "• /generate a beautiful sunset over mountains\n"
            "• /generate a cute cat playing with a ball\n"
            "• /generate futuristic city at night\n"
            "• /generate portrait of a person\n\n"
            "💡 Describe what you want to see, and AI will create it!\n"
            "✨ Using free AI image generation (no API key needed)"
        )
        return
    
    prompt = ' '.join(context.args)
    
    if len(prompt) > 500:
        await update.message.reply_text(
            "❌ Prompt is too long! Please keep it under 500 characters."
        )
        return
    
    processing_msg = await update.message.reply_text(
        f"🎨 Generating image from prompt...\n"
        f"📝 Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n"
        f"⏳ This may take 15-30 seconds..."
    )
    
    try:
        loop = asyncio.get_event_loop()
        
        def generate_image():
            try:
                # Encode prompt for URL
                encoded_prompt = quote(prompt)
                
                # Try multiple free APIs with fallback
                api_urls = [
                    # Pollinations.ai - primary
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true",
                    # Alternative: Pollinations with different parameters
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&enhance=true",
                    # Simple version
                    f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true",
                ]
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                last_error = None
                
                for idx, image_url in enumerate(api_urls):
                    try:
                        logger.info(f"Trying API {idx + 1}/{len(api_urls)}: {image_url[:80]}...")
                        
                        # Download the generated image
                        response = requests.get(
                            image_url, 
                            timeout=90, 
                            stream=True,
                            headers=headers,
                            allow_redirects=True
                        )
                        
                        logger.info(f"Response status: {response.status_code}, Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                        
                        if response.status_code == 200:
                            img_buffer = io.BytesIO()
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    img_buffer.write(chunk)
                            
                            img_buffer.seek(0)
                            buffer_size = len(img_buffer.getvalue())
                            logger.info(f"Downloaded {buffer_size} bytes")
                            
                            if buffer_size < 1000:  # Too small, probably error
                                logger.warning(f"Buffer too small: {buffer_size} bytes, trying next API...")
                                continue
                            
                            # Verify it's a valid image
                            try:
                                if PIL_AVAILABLE:
                                    img = Image.open(img_buffer)
                                    img.verify()  # Verify it's a valid image
                                    img_buffer.seek(0)
                                    
                                    # Reopen after verify (verify() closes the image)
                                    img = Image.open(img_buffer)
                                    
                                    # Convert to RGB if needed
                                    if img.mode != 'RGB':
                                        rgb_buffer = io.BytesIO()
                                        img.convert('RGB').save(rgb_buffer, format='JPEG', quality=95)
                                        rgb_buffer.seek(0)
                                        return rgb_buffer
                                    
                                    img_buffer.seek(0)
                                    return img_buffer
                                else:
                                    # Without PIL, just check if it starts with image headers
                                    img_buffer.seek(0)
                                    header = img_buffer.read(4)
                                    img_buffer.seek(0)
                                    
                                    # Check for common image formats
                                    if header.startswith(b'\xff\xd8') or header.startswith(b'\x89PNG') or header.startswith(b'GIF8'):
                                        return img_buffer
                                    else:
                                        logger.warning(f"Invalid image header: {header}, trying next API...")
                                        continue
                                        
                            except Exception as img_error:
                                logger.warning(f"Image verification failed: {img_error}, trying next API...")
                                last_error = img_error
                                continue
                        else:
                            logger.warning(f"API {idx + 1} returned status {response.status_code}")
                            continue
                    
                    except requests.exceptions.Timeout:
                        logger.warning(f"API {idx + 1} timed out, trying next...")
                        last_error = "Request timed out"
                        continue
                    except Exception as e:
                        logger.warning(f"API {idx + 1} error: {e}, trying next...")
                        last_error = e
                        continue
                
                # All APIs failed
                raise Exception(f"All image generation APIs failed. Last error: {str(last_error) if last_error else 'Unknown error'}")
            
            except Exception as e:
                logger.error(f"Image generation error: {e}", exc_info=True)
                raise
        
        # Generate image in executor (blocking operation)
        image_buffer = await loop.run_in_executor(None, generate_image)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Send the generated image
        await update.message.reply_photo(
            photo=image_buffer,
            caption=f"🎨 **AI Generated Image**\n\n"
                   f"📝 Prompt: `{prompt}`",
            parse_mode='Markdown'
        )
        
        logger.info(f"Image generated successfully for prompt: {prompt}")
    
    except Exception as e:
        logger.error(f"Generate command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e)
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            error_msg = "Image generation took too long. The service might be busy."
        elif "All image generation APIs failed" in error_msg:
            error_msg = "Image generation service is temporarily unavailable. Please try again in a few minutes."
        elif "API" in error_msg or "status" in error_msg:
            error_msg = "Image generation service error. Please try again later."
        
        await update.message.reply_text(
            f"❌ **Error generating image**\n\n{error_msg}\n\n"
            "💡 **Try these:**\n"
            "• Wait 30-60 seconds and try again\n"
            "• Use a simpler, shorter prompt\n"
            "• Be specific: 'sunset over ocean' instead of 'nice picture'\n"
            "• Try: `/generate a cat` or `/generate beautiful landscape`\n\n"
            "🔄 The service may be busy, please try again shortly."
        )

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Translate text between languages."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "🌐 **Translation Feature**\n\n"
            "Usage: /translate <target_language> <text>\n\n"
            "**Examples:**\n"
            "• /translate bn Hello, how are you?\n"
            "• /translate en আমি ভালো আছি\n"
            "• /translate es Good morning\n"
            "• /translate hi How are you?\n\n"
            "**Supported Languages:**\n"
            "• `bn` - Bengali (বাংলা)\n"
            "• `en` - English\n"
            "• `hi` - Hindi\n"
            "• `es` - Spanish\n"
            "• `fr` - French\n"
            "• `de` - German\n"
            "• `ar` - Arabic\n"
            "• `ja` - Japanese\n"
            "• `zh` - Chinese\n"
            "• `ru` - Russian\n"
            "• And 100+ more languages!\n\n"
            "💡 Just use the language code (e.g., bn, en, hi)"
        )
        return
    
    target_lang = context.args[0].lower()
    text_to_translate = ' '.join(context.args[1:])
    
    if len(text_to_translate) > 1000:
        await update.message.reply_text(
            "❌ Text is too long! Please keep it under 1000 characters."
        )
        return
    
    processing_msg = await update.message.reply_text(f"🌐 Translating to {target_lang.upper()}...")
    
    try:
        loop = asyncio.get_event_loop()
        
        def translate_text():
            try:
                # Method 1: Try MyMemory Translation API (free, no API key needed)
                try:
                    api_url = "https://api.mymemory.translated.net/get"
                    
                    params = {
                        'q': text_to_translate,
                        'langpair': f'auto|{target_lang}'
                    }
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    response = requests.get(api_url, params=params, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get('responseStatus') == 200:
                            translated_text = data['responseData']['translatedText']
                            detected_lang = data.get('responseData', {}).get('detectedSourceLanguage', 'auto')
                            
                            # Clean up translation (sometimes API returns extra text)
                            if translated_text and len(translated_text) > 0:
                                return {
                                    'translated': translated_text,
                                    'detected': detected_lang,
                                    'target': target_lang
                                }
                except Exception as e:
                    logger.warning(f"MyMemory API failed: {e}")
                
                # Method 2: Try LibreTranslate (free alternative)
                try:
                    libre_url = "https://libretranslate.com/translate"
                    
                    payload = {
                        'q': text_to_translate,
                        'source': 'auto',
                        'target': target_lang,
                        'format': 'text'
                    }
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0'
                    }
                    
                    response = requests.post(libre_url, json=payload, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('translatedText'):
                            return {
                                'translated': data['translatedText'],
                                'detected': data.get('detectedLanguage', {}).get('language', 'auto'),
                                'target': target_lang
                            }
                except Exception as e:
                    logger.warning(f"LibreTranslate API failed: {e}")
                
                # Method 3: Try Google Translate via web scraping (fallback)
                try:
                    # Use a simple translation service
                    google_url = f"https://translate.googleapis.com/translate_a/single"
                    params = {
                        'client': 'gtx',
                        'sl': 'auto',
                        'tl': target_lang,
                        'dt': 't',
                        'q': text_to_translate
                    }
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    response = requests.get(google_url, params=params, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data and len(data) > 0 and len(data[0]) > 0:
                            translated_parts = [item[0] for item in data[0] if item[0]]
                            translated_text = ''.join(translated_parts)
                            
                            if translated_text:
                                return {
                                    'translated': translated_text,
                                    'detected': data[2] if len(data) > 2 else 'auto',
                                    'target': target_lang
                                }
                except Exception as e:
                    logger.warning(f"Google Translate API failed: {e}")
                
                # All methods failed
                raise Exception("All translation APIs failed. Please check the language code and try again.")
            
            except Exception as e:
                logger.error(f"Translation error: {e}", exc_info=True)
                raise
        
        result = await loop.run_in_executor(None, translate_text)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Format response
        detected_info = ""
        if result['detected'] and result['detected'] != 'auto':
            detected_info = f"Detected: `{result['detected'].upper()}` → "
        
        response_text = (
            f"🌐 **Translation**\n\n"
            f"{detected_info}**{result['target'].upper()}:**\n"
            f"`{result['translated']}`\n\n"
            f"📝 **Original:**\n"
            f"`{text_to_translate}`"
        )
        
        await update.message.reply_text(response_text, parse_mode='Markdown')
    
    except Exception as e:
        logger.error(f"Translate command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"❌ **Translation Error**\n\n"
            f"Error: {str(e)}\n\n"
            "💡 **Try:**\n"
            "• Check language code (e.g., bn, en, hi)\n"
            "• Make sure text is valid\n"
            "• Try again in a moment"
        )

async def ocr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extract text from image (OCR - Optical Character Recognition).

    Usage:
    - /ocr → defaults to English (eng)
    - /ocr bn → Bangla
    - /ocr ben+eng → Bangla + English mixed
    - Supported short codes: en, bn, hi, ur, ar
    """
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "📸 **Image to Text (OCR)**\n\n"
            "Usage: Send an image or reply to an image with /ocr\n\n"
            "**What it does:**\n"
            "• Extracts text from images\n"
            "• Works with photos, screenshots, documents\n"
            "• Supports multiple languages\n\n"
            "**Examples:**\n"
            "• Send an image with text and use /ocr (English)\n"
            "• Reply to an image with /ocr bn (Bangla)\n\n"
            "💡 Perfect for:\n"
            "• Extracting text from photos\n"
            "• Reading text from screenshots\n"
            "• Converting image text to editable text"
        )
        return
    
    try:
        # Language selection
        lang_arg = ' '.join(context.args).strip().lower() if context.args else ''
        friendly_to_ocrspace = {
            '': 'eng',
            'en': 'eng', 'eng': 'eng', 'english': 'eng',
            'bn': 'ben', 'bangla': 'ben', 'bengali': 'ben', 'ben': 'ben',
            'hi': 'hin', 'hin': 'hin', 'hindi': 'hin',
            'ur': 'urd', 'urd': 'urd', 'urdu': 'urd',
            'ar': 'ara', 'ara': 'ara', 'arabic': 'ara',
        }
        # Allow combos like "ben+eng"
        def normalize_lang(arg: str) -> str:
            if not arg:
                return 'eng'
            tmp = arg.replace(',', '+').replace(' ', '+')
            parts = [p.strip() for p in tmp.split('+') if p.strip()]
            mapped = []
            for p in parts:
                mapped.append(friendly_to_ocrspace.get(p, p))
            # Deduplicate while preserving order
            seen = set()
            result = []
            for m in mapped:
                if m and m not in seen:
                    seen.add(m)
                    result.append(m)
            # Only allow supported OCR.space codes and join with commas
            allowed = {'eng','ben','hin','urd','ara'}
            filtered = [m for m in result if m in allowed]
            if not filtered:
                return 'eng'
            return ','.join(filtered)

        ocr_lang = normalize_lang(lang_arg)
        # Use only the primary language for OCR.space to avoid E201 on free tier
        ocr_lang_primary = ocr_lang.split(',')[0] if ',' in ocr_lang else ocr_lang
        try:
            logger.info(f"OCR language requested='{lang_arg}' mapped='{ocr_lang}' primary='{ocr_lang_primary}'")
        except Exception:
            pass
        # Get image from message or reply
        if update.message.reply_to_message and update.message.reply_to_message.photo:
            photo = update.message.reply_to_message.photo[-1]
        elif update.message.photo:
            photo = update.message.photo[-1]
        else:
            await update.message.reply_text("❌ No image found!")
            return
        
        processing_msg = await update.message.reply_text("📸 Extracting text from image...")
        
        loop = asyncio.get_event_loop()
        try:
            file = await context.bot.get_file(photo.file_id)
            # Build a fully-qualified Telegram file URL for external OCR services
            if file.file_path and str(file.file_path).startswith('http'):
                file_url_for_ocr = file.file_path
            else:
                file_url_for_ocr = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ Error downloading image: {str(e)}")
            return
        
        def extract_text_from_image(file_path_url):
            try:
                # Method 0: Local Tesseract OCR first (no API key)
                try:
                    import io as _io
                    import requests as _req
                    import shutil as _shutil
                    import os as _os
                    try:
                        import pytesseract as _pyt
                    except Exception:
                        _pyt = None
                    if _pyt is not None:
                        tesseract_exe = _shutil.which('tesseract')
                        default_win_path = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
                        if not tesseract_exe and _os.path.exists(default_win_path):
                            tesseract_exe = default_win_path
                        if tesseract_exe:
                            _pyt.pytesseract.tesseract_cmd = tesseract_exe
                            img_resp = _req.get(file_path_url, timeout=30)
                            if img_resp.status_code == 200 and img_resp.content:
                                buf = _io.BytesIO(img_resp.content)
                                pil_img = Image.open(buf)
                                try:
                                    from PIL import ImageOps
                                    if pil_img.mode != 'L':
                                        pil_img = pil_img.convert('L')
                                    pil_img = ImageOps.autocontrast(pil_img)
                                except Exception:
                                    pass
                                tess_lang = (ocr_lang_primary if 'ocr_lang_primary' in locals() else 'eng')
                                try:
                                    text_local = _pyt.image_to_string(pil_img, lang=tess_lang)
                                    if text_local and len(text_local.strip()) > 0:
                                        return text_local.strip()
                                except Exception:
                                    # Retry with English as fallback
                                    try:
                                        text_local = _pyt.image_to_string(pil_img, lang='eng')
                                        if text_local and len(text_local.strip()) > 0:
                                            return text_local.strip()
                                    except Exception:
                                        pass
                        else:
                            logger.info("Tesseract not found on system PATH; skipping local OCR")
                    else:
                        logger.info("pytesseract not installed; skipping local OCR")
                except Exception as _e:
                    logger.warning(f"Local Tesseract OCR attempt failed: {_e}")

                # Method 1: Try OCR.space API (free tier)
                try:
                    ocr_url = "https://api.ocr.space/parse/imageurl"
                    
                    payload = {
                        'apikey': OCR_SPACE_API_KEY,
                        'url': file_path_url,
                        'language': ocr_lang_primary,  # Use primary to avoid API E201
                        'isOverlayRequired': False,
                        'detectOrientation': True,
                        'scale': True,
                        'OCREngine': 2
                    }
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0'
                    }
                    
                    response = requests.post(ocr_url, data=payload, headers=headers, timeout=45)
                    
                    if response.status_code == 200:
                        data = response.json()
                        # Check for API-level errors
                        if data.get('IsErroredOnProcessing'):
                            logger.warning(f"OCR.space error: {data.get('ErrorMessage') or data.get('ErrorDetails')}")
                            err_text = ' '.join([str(x) for x in (data.get('ErrorMessage') or data.get('ErrorDetails') or [])])
                            # Retry sequence for language errors
                            if 'E201' in err_text or 'language' in err_text.lower():
                                for candidate in [ocr_lang_primary, 'ben', 'bn', 'eng']:
                                    try:
                                        retry_payload = payload.copy()
                                        retry_payload['language'] = candidate
                                        retry_resp = requests.post(ocr_url, data=retry_payload, headers=headers, timeout=45)
                                        if retry_resp.status_code == 200:
                                            retry_data = retry_resp.json()
                                            if retry_data.get('ParsedResults') and len(retry_data['ParsedResults']) > 0:
                                                parsed_text = retry_data['ParsedResults'][0].get('ParsedText', '')
                                                if parsed_text and len(parsed_text.strip()) > 0:
                                                    return parsed_text.strip()
                                    except Exception:
                                        continue
                        
                        if data.get('ParsedResults') and len(data['ParsedResults']) > 0:
                            parsed_text = data['ParsedResults'][0].get('ParsedText', '')
                            
                            if parsed_text and len(parsed_text.strip()) > 0:
                                return parsed_text.strip()
                except Exception as e:
                    logger.warning(f"OCR.space API failed: {e}")
                
                # Method 2: Download image and try alternative OCR
                try:
                    img_response = requests.get(file_path_url, timeout=30)
                    if img_response.status_code == 200:
                        # Try using PIL to process image if available
                        if PIL_AVAILABLE:
                            img_buffer = io.BytesIO(img_response.content)
                            img = Image.open(img_buffer)
                            
                            # Convert to RGB if needed
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            # Simple preprocessing to improve OCR accuracy
                            try:
                                from PIL import ImageEnhance, ImageFilter
                                # Increase contrast and sharpness
                                img = ImageEnhance.Contrast(img).enhance(1.5)
                                img = ImageEnhance.Sharpness(img).enhance(1.3)
                                # Upscale small images
                                if min(img.size) < 800:
                                    scale_factor = max(1.0, 800 / float(min(img.size)))
                                    new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                                # Light denoise
                                img = img.filter(ImageFilter.MedianFilter(size=3))
                            except Exception as _:
                                pass
                            
                            # Save to buffer for OCR.space file upload
                            output_buffer = io.BytesIO()
                            img.save(output_buffer, format='PNG')
                            output_buffer.seek(0)
                            
                            # Try OCR.space with file upload
                            ocr_url = "https://api.ocr.space/parse/image"
                            files = {
                                'file': ('image.png', output_buffer, 'image/png')
                            }
                            payload = {
                                'apikey': OCR_SPACE_API_KEY,
                                'language': ocr_lang_primary,
                                'isOverlayRequired': False,
                                'detectOrientation': True,
                                'scale': True,
                                'OCREngine': 2
                            }
                            
                            response = requests.post(ocr_url, files=files, data=payload, timeout=45)
                            
                            if response.status_code == 200:
                                data = response.json()
                                if data.get('IsErroredOnProcessing'):
                                    logger.warning(f"OCR.space upload error: {data.get('ErrorMessage') or data.get('ErrorDetails')}")
                                    err_text = ' '.join([str(x) for x in (data.get('ErrorMessage') or data.get('ErrorDetails') or [])])
                                    if 'E201' in err_text or 'language' in err_text.lower():
                                        for candidate in [ocr_lang_primary, 'ben', 'bn', 'eng']:
                                            try:
                                                retry_payload = payload.copy()
                                                retry_payload['language'] = candidate
                                                retry_resp = requests.post(ocr_url, files=files, data=retry_payload, timeout=45)
                                                if retry_resp.status_code == 200:
                                                    retry_data = retry_resp.json()
                                                    if retry_data.get('ParsedResults') and len(retry_data['ParsedResults']) > 0:
                                                        parsed_text = retry_data['ParsedResults'][0].get('ParsedText', '')
                                                        if parsed_text and len(parsed_text.strip()) > 0:
                                                            return parsed_text.strip()
                                            except Exception:
                                                continue
                                if data.get('ParsedResults') and len(data['ParsedResults']) > 0:
                                    parsed_text = data['ParsedResults'][0].get('ParsedText', '')
                                    if parsed_text and len(parsed_text.strip()) > 0:
                                        return parsed_text.strip()
                except Exception as e:
                    logger.warning(f"Alternative OCR method failed: {e}")
                
                # Method 3: Local Tesseract OCR fallback (if available)
                try:
                    import io as _io
                    import requests as _req
                    import shutil as _shutil
                    import os as _os
                    try:
                        import pytesseract as _pyt
                    except Exception as _:
                        _pyt = None
                    if _pyt is not None:
                        # Try to locate tesseract binary on Windows default path if not on PATH
                        tesseract_exe = _shutil.which('tesseract')
                        default_win_path = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
                        if not tesseract_exe and _os.path.exists(default_win_path):
                            tesseract_exe = default_win_path
                        if tesseract_exe:
                            _pyt.pytesseract.tesseract_cmd = tesseract_exe
                            # Download image bytes
                            img_resp = _req.get(file_path_url, timeout=30)
                            if img_resp.status_code == 200 and img_resp.content:
                                buf = _io.BytesIO(img_resp.content)
                                pil_img = Image.open(buf)
                                # Preprocess for OCR
                                try:
                                    from PIL import ImageOps
                                    if pil_img.mode != 'L':
                                        pil_img = pil_img.convert('L')
                                    pil_img = ImageOps.autocontrast(pil_img)
                                    # Simple thresholding
                                    pil_img = pil_img.point(lambda x: 0 if x < 180 else 255, '1')
                                except Exception:
                                    pass
                                # Map languages for pytesseract (uses '+' for multi)
                                tess_lang = ocr_lang.replace(',', '+') if 'ocr_lang' in locals() else 'ben'
                                if not tess_lang:
                                    tess_lang = ocr_lang_primary if 'ocr_lang_primary' in locals() else 'ben'
                                try:
                                    text_local = _pyt.image_to_string(pil_img, lang=tess_lang)
                                except Exception:
                                    # Retry with primary then English
                                    try:
                                        text_local = _pyt.image_to_string(pil_img, lang=(ocr_lang_primary if 'ocr_lang_primary' in locals() else 'ben'))
                                    except Exception:
                                        text_local = _pyt.image_to_string(pil_img, lang='eng')
                                if text_local and len(text_local.strip()) > 0:
                                    return text_local.strip()
                        else:
                            logger.info("Tesseract executable not found; skipping local OCR fallback")
                    else:
                        logger.info("pytesseract not installed; skipping local OCR fallback")
                except Exception as _e:
                    logger.warning(f"Local Tesseract OCR fallback failed: {_e}")

                # If all methods fail
                raise Exception("Could not extract text from image. Please make sure the image contains clear, readable text.")
            
            except Exception as e:
                logger.error(f"OCR extraction error: {e}", exc_info=True)
                raise
        
        extracted_text = await loop.run_in_executor(None, extract_text_from_image, file_url_for_ocr)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        if not extracted_text or len(extracted_text.strip()) == 0:
            hint_lines = [
                "❌ No text found in the image.\n",
                "💡 **Tips:**\n",
                "• Make sure the image contains clear, readable text\n",
                "• Try with a higher quality image\n",
                "• Ensure good lighting and contrast\n",
            ]
            if 'helloworld' in OCR_SPACE_API_KEY:
                hint_lines.append("• Set OCR_SPACE_API_KEY for better accuracy on OCR.space\n")
            try:
                import pytesseract  # noqa: F401
            except Exception:
                hint_lines.append("• Install Tesseract + pytesseract for local OCR fallback")
            await update.message.reply_text(''.join(hint_lines))
            return
        
        # Send extracted text (limit to 4096 characters for Telegram)
        if len(extracted_text) > 4000:
            extracted_text = extracted_text[:4000] + "\n\n... (text truncated)"
        
        await update.message.reply_text(
            f"📸 **Extracted Text:**\n\n"
            f"`{extracted_text}`",
            parse_mode='Markdown'
        )
        
        logger.info(f"OCR successful - extracted {len(extracted_text)} characters")
    
    except Exception as e:
        logger.error(f"OCR command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"❌ **Error extracting text**\n\n"
            f"Error: {str(e)}\n\n"
            "💡 **Try:**\n"
            "• Make sure the image contains clear text\n"
            "• Use a higher quality image\n"
            "• Try again in a moment"
        )

async def imagetopdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert image(s) to PDF."""
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Image to PDF feature requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not update.message.photo and not update.message.reply_to_message:
        await update.message.reply_text(
            "📄 **Image to PDF Converter**\n\n"
            "Usage: Send an image or reply to an image with /imagetopdf\n\n"
            "**What it does:**\n"
            "• Converts images to PDF format\n"
            "• Supports multiple images (creates multi-page PDF)\n"
            "• Works with JPG, PNG, and other image formats\n\n"
            "**Examples:**\n"
            "• Send an image and use /imagetopdf\n"
            "• Reply to an image message with /imagetopdf\n"
            "• Send multiple images and use /imagetopdf (creates multi-page PDF)\n\n"
            "💡 Perfect for:\n"
            "• Converting photos to PDF\n"
            "• Creating PDF documents from images\n"
            "• Combining multiple images into one PDF"
        )
        return
    
    try:
        processing_msg = await update.message.reply_text("📄 Converting image(s) to PDF...")
        
        # Get image from message or reply (similar to OCR command)
        photo = None
        doc = None
        
        # Priority 1: Check reply to message
        if update.message.reply_to_message:
            if update.message.reply_to_message.photo:
                photo = update.message.reply_to_message.photo[-1]
            elif update.message.reply_to_message.document:
                doc_obj = update.message.reply_to_message.document
                if doc_obj.mime_type and doc_obj.mime_type.startswith('image/'):
                    doc = doc_obj
        
        # Priority 2: Check current message
        if not photo and not doc:
            if update.message.photo:
                photo = update.message.photo[-1]
            elif update.message.document:
                doc_obj = update.message.document
                if doc_obj.mime_type and doc_obj.mime_type.startswith('image/'):
                    doc = doc_obj
        
        if not photo and not doc:
            await processing_msg.delete()
            await update.message.reply_text(
                "❌ No image found!\n\n"
                "💡 **Usage:**\n"
                "• Reply to an image message with /imagetopdf\n"
                "• Or send an image and use /imagetopdf in the caption"
            )
            return
        
        # Prepare list of images to process
        images_to_process = []
        if photo:
            images_to_process.append(photo)
        if doc:
            images_to_process.append(doc)
        
        loop = asyncio.get_event_loop()
        
        def convert_images_to_pdf(image_list):
            try:
                pdf_images = []
                
                for img_item in image_list:
                    try:
                        # Download image
                        file = None
                        if hasattr(img_item, 'file_id'):
                            # It's a PhotoSize or Document
                            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/"
                            # We need to download it
                            response = requests.get(f"{file_url}{img_item.file_path if hasattr(img_item, 'file_path') else ''}", timeout=30)
                            if response.status_code == 200:
                                img_data = response.content
                            else:
                                # Try to get file path
                                continue
                        else:
                            continue
                        
                        # Open image with PIL
                        img_buffer = io.BytesIO(img_data) if 'img_data' in locals() else None
                        if not img_buffer:
                            continue
                        
                        img = Image.open(img_buffer)
                        
                        # Convert to RGB if needed (PDF requires RGB)
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        pdf_images.append(img)
                        
                    except Exception as e:
                        logger.warning(f"Error processing image: {e}")
                        continue
                
                if not pdf_images:
                    return None
                
                # Create PDF
                pdf_buffer = io.BytesIO()
                
                if len(pdf_images) == 1:
                    # Single image PDF
                    pdf_images[0].save(pdf_buffer, format='PDF', quality=95)
                else:
                    # Multi-page PDF - save first image, then append others
                    pdf_images[0].save(pdf_buffer, format='PDF', save_all=True, append_images=pdf_images[1:] if len(pdf_images) > 1 else [], quality=95)
                
                pdf_buffer.seek(0)
                return pdf_buffer
                
            except Exception as e:
                logger.error(f"PDF conversion error: {e}", exc_info=True)
                return None
        
        # Download images first
        image_data_list = []
        for img_item in images_to_process:
            try:
                # Get file object
                file = await context.bot.get_file(img_item.file_id)
                
                # Check if file_path is available
                if not file.file_path:
                    logger.warning(f"File path is None for file_id: {img_item.file_id}")
                    # Try to get file info again
                    raise Exception("File path not available")
                
                # Download using file URL (Telegram Bot API)
                # Construct full URL
                if file.file_path.startswith('http'):
                    file_url = file.file_path
                else:
                    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
                
                logger.info(f"Downloading image from: {file_url[:100]}...")
                response = requests.get(file_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
                
                if response.status_code == 200 and response.content:
                    img_data = response.content
                    if len(img_data) > 0:
                        image_data_list.append(img_data)
                        logger.info(f"Successfully downloaded image: {len(img_data)} bytes, file_id: {img_item.file_id}")
                    else:
                        logger.warning(f"Downloaded image is empty for file_id: {img_item.file_id}")
                        raise Exception("Downloaded image is empty")
                elif response.status_code == 404:
                    logger.warning(f"File not found (404) for file_id: {img_item.file_id} - file may have expired or been deleted")
                    raise Exception("File not found or expired - please send the image again")
                else:
                    raise Exception(f"Failed to download image: HTTP {response.status_code}")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error downloading image: {error_msg}")
                
                # If it's a 404 or file not found, skip this image and inform user
                if "404" in error_msg or "not found" in error_msg.lower() or "expired" in error_msg.lower():
                    logger.warning(f"Skipping image {img_item.file_id} - file not available")
                    continue
                
                # Try alternative: download using stream
                try:
                    file = await context.bot.get_file(img_item.file_id)
                    if file.file_path:
                        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
                        response = requests.get(file_url, timeout=30, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
                        if response.status_code == 200:
                            file_buffer = io.BytesIO()
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    file_buffer.write(chunk)
                            file_buffer.seek(0)
                            img_data = file_buffer.read()
                            if len(img_data) > 0:
                                image_data_list.append(img_data)
                                logger.info(f"Downloaded via stream fallback: {len(img_data)} bytes")
                            else:
                                logger.warning(f"Stream download returned empty data")
                                continue
                        else:
                            logger.warning(f"Stream download failed: HTTP {response.status_code}")
                            continue
                    else:
                        logger.warning(f"No file path available for alternative download")
                        continue
                except Exception as e2:
                    logger.error(f"Alternative download method also failed: {e2}")
                continue
        
        if not image_data_list:
            await processing_msg.delete()
            await update.message.reply_text(
                "❌ Failed to download images!\n\n"
                "💡 **Please try:**\n"
                "• Reply to the image message with /imagetopdf\n"
                "• Make sure the image is still available\n"
                "• Try again in a moment"
            )
            return
        
        # Convert to PDF
        def create_pdf_from_images(img_data_list):
            try:
                pdf_images = []
                
                for img_data in img_data_list:
                    try:
                        img_buffer = io.BytesIO(img_data)
                        img = Image.open(img_buffer)
                        
                        # Convert to RGB if needed (PDF requires RGB)
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        pdf_images.append(img)
                    except Exception as e:
                        logger.warning(f"Error processing image: {e}")
                        continue
                
                if not pdf_images:
                    return None
                
                # Create PDF
                pdf_buffer = io.BytesIO()
                
                if len(pdf_images) == 1:
                    # Single image PDF
                    pdf_images[0].save(pdf_buffer, format='PDF', quality=95)
                else:
                    # Multi-page PDF
                    pdf_images[0].save(
                        pdf_buffer, 
                        format='PDF', 
                        save_all=True, 
                        append_images=pdf_images[1:] if len(pdf_images) > 1 else [], 
                        quality=95
                    )
                
                pdf_buffer.seek(0)
                return pdf_buffer
                
            except Exception as e:
                logger.error(f"PDF conversion error: {e}", exc_info=True)
                return None
        
        pdf_file = await loop.run_in_executor(None, create_pdf_from_images, image_data_list)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        if pdf_file:
            pdf_file.seek(0, 2)  # Seek to end
            file_size = pdf_file.tell()
            pdf_file.seek(0)
            
            # Check file size (Telegram limit is ~50MB)
            if file_size > 50 * 1024 * 1024:
                await update.message.reply_text(
                    "❌ PDF file is too large (>50MB).\n"
                    "Please use smaller images or fewer images."
                )
                return
            
            # Create filename
            filename = f"images_{len(image_data_list)}_pages.pdf"
            
            await update.message.reply_document(
                document=pdf_file,
                filename=filename,
                caption=f"📄 **PDF Created Successfully!**\n\n"
                       f"✅ Converted {len(image_data_list)} image(s) to PDF\n"
                       f"📊 File size: {file_size / 1024:.2f} KB"
            )
            logger.info(f"Image to PDF successful - {len(image_data_list)} images converted")
        else:
            await update.message.reply_text(
                "❌ **Failed to create PDF**\n\n"
                "💡 **Try:**\n"
                "• Make sure the images are valid\n"
                "• Try with different images\n"
                "• Check image format (JPG, PNG supported)"
            )
    
    except Exception as e:
        logger.error(f"Image to PDF command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"❌ **Error converting to PDF**\n\n"
            f"Error: {str(e)}\n\n"
            "💡 **Try:**\n"
            "• Make sure you sent valid images\n"
            "• Try again in a moment\n"
            "• Ensure Pillow is installed correctly"
        )

async def pdftoimage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Convert PDF pages to images."""
    if not PDF_AVAILABLE:
        # Check if it's a DLL error
        if PDF_ERROR and ("DLL" in PDF_ERROR or "load failed" in PDF_ERROR.lower()):
            await update.message.reply_text(
                "❌ **PyMuPDF DLL Load Error**\n\n"
                "**The library is installed but cannot load required DLL files.**\n\n"
                "**🔧 Solution (Required):**\n\n"
                "**Install Visual C++ Redistributables:**\n"
                "1️⃣ Download: https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
                "2️⃣ Run the installer and click 'Install'\n\n"
                "3️⃣ Restart your bot after installation\n\n"
                "**After installing, the PDF to image feature will work!**\n\n"
                "💡 **Note:** This is a Windows system requirement for PyMuPDF.\n"
                "All other bot features work perfectly without this."
            )
        else:
            # Try to import again to show specific error
            try:
                import fitz
                # If import works but PDF_AVAILABLE is False, it means there's a runtime issue
                await update.message.reply_text(
                    "❌ PDF to Image feature is not working properly.\n\n"
                    "**Possible solutions:**\n"
                    "• Reinstall: `python -m pip install --upgrade --force-reinstall PyMuPDF`\n"
                    "• Install Visual C++ Redistributables (if on Windows)\n"
                    "• Check Python version compatibility\n\n"
                    "💡 PyMuPDF requires proper system dependencies to work."
                )
            except ImportError as e:
                error_msg = str(e)
                if "DLL" in error_msg or "load failed" in error_msg.lower():
                    await update.message.reply_text(
                        "❌ **PyMuPDF DLL Load Error**\n\n"
                        "**Install Visual C++ Redistributables:**\n"
                        "https://aka.ms/vs/17/release/vc_redist.x64.exe\n\n"
                        "Then restart the bot."
                    )
                else:
                    await update.message.reply_text(
                        "❌ PDF to Image feature requires PyMuPDF library.\n\n"
                        "**Install:**\n"
                        "`python -m pip install PyMuPDF`\n\n"
                        "**If you get DLL errors:**\n"
                        "• Install Visual C++ Redistributables\n"
                        "• Or try: `python -m pip install --upgrade PyMuPDF`\n\n"
                        "💡 PyMuPDF is a fast and reliable PDF library for Python."
                    )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ PDF to Image feature error:\n\n"
                    f"`{str(e)}`\n\n"
                    "**Try:**\n"
                    "• `python -m pip install --upgrade --force-reinstall PyMuPDF`\n"
                    "• Check if Visual C++ Redistributables are installed\n"
                    "• Restart the bot after installation"
                )
        return
    
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ PDF to Image feature also requires Pillow library.\n\n"
            "Install: `pip install Pillow PyMuPDF`"
        )
        return
    
    # Check if PDF is attached or in reply
    pdf_doc = None
    
    # Priority 1: Check reply to message
    if update.message.reply_to_message:
        if update.message.reply_to_message.document:
            doc_obj = update.message.reply_to_message.document
            if doc_obj.mime_type == 'application/pdf':
                pdf_doc = doc_obj
    
    # Priority 2: Check current message
    if not pdf_doc:
        if update.message.document:
            doc_obj = update.message.document
            if doc_obj.mime_type == 'application/pdf':
                pdf_doc = doc_obj
    
    if not pdf_doc:
        await update.message.reply_text(
            "🖼️ **PDF to Image Converter**\n\n"
            "Usage: Send a PDF file or reply to a PDF with /pdftoimage\n\n"
            "**What it does:**\n"
            "• Converts each PDF page to a separate image\n"
            "• Extracts all pages as PNG images\n"
            "• Sends images in order (page 1, 2, 3...)\n\n"
            "**Examples:**\n"
            "• Send a PDF file and use /pdftoimage\n"
            "• Reply to a PDF message with /pdftoimage\n\n"
            "💡 Perfect for:\n"
            "• Extracting pages from PDFs\n"
            "• Converting PDF documents to images\n"
            "• Sharing individual PDF pages"
        )
        return
    
    try:
        processing_msg = await update.message.reply_text("🖼️ Converting PDF to images...\n⏳ Please wait...")
        
        # Download PDF file
        try:
            file = await context.bot.get_file(pdf_doc.file_id)
            
            if not file.file_path:
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ Could not get PDF file path.\n\n"
                    "Please try sending the PDF again."
                )
                return
            
            # Construct file URL
            if file.file_path.startswith('http'):
                file_url = file.file_path
            else:
                file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            
            logger.info(f"Downloading PDF from: {file_url[:100]}...")
            response = requests.get(file_url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
            
            if response.status_code != 200:
                await processing_msg.delete()
                await update.message.reply_text(
                    f"❌ Failed to download PDF: HTTP {response.status_code}\n\n"
                    "Please try again."
                )
                return
            
            pdf_data = response.content
            if len(pdf_data) == 0:
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ Downloaded PDF is empty.\n\n"
                    "Please check the PDF file and try again."
                )
                return
            
            logger.info(f"PDF downloaded: {len(pdf_data)} bytes")
            
        except Exception as e:
            await processing_msg.delete()
            logger.error(f"Error downloading PDF: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Error downloading PDF: {str(e)}\n\n"
                "Please try again."
            )
            return
        
        # Convert PDF to images
        loop = asyncio.get_event_loop()
        
        def convert_pdf_to_images(pdf_bytes):
            try:
                # Import fitz inside the function to avoid scope issues
                import fitz as fitz_module
                # Open PDF with PyMuPDF
                pdf_buffer = io.BytesIO(pdf_bytes)
                pdf_document = fitz_module.open(stream=pdf_buffer, filetype="pdf")
                
                images = []
                total_pages = len(pdf_document)
                
                logger.info(f"Converting PDF with {total_pages} pages to images...")
                
                for page_num in range(total_pages):
                    try:
                        # Get page
                        page = pdf_document[page_num]
                        
                        # Convert page to image (zoom factor 2 for better quality)
                        zoom = 2.0
                        mat = fitz_module.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=mat)
                        
                        # Convert to PIL Image
                        img_data = pix.tobytes("png")
                        img = Image.open(io.BytesIO(img_data))
                        
                        # Convert to RGB if needed
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Save to buffer
                        img_buffer = io.BytesIO()
                        img.save(img_buffer, format='PNG')
                        img_buffer.seek(0)
                        
                        images.append({
                            'buffer': img_buffer,
                            'page_num': page_num + 1,
                            'size': len(img_data)
                        })
                        
                        logger.info(f"Converted page {page_num + 1}/{total_pages}")
                        
                    except Exception as e:
                        logger.warning(f"Error converting page {page_num + 1}: {e}")
                        continue
                
                pdf_document.close()
                
                if not images:
                    return None
                
                return images
                
            except Exception as e:
                logger.error(f"PDF conversion error: {e}", exc_info=True)
                return None
        
        # Convert PDF to images
        images = await loop.run_in_executor(None, convert_pdf_to_images, pdf_data)
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        if not images:
            await update.message.reply_text(
                "❌ **Failed to convert PDF to images**\n\n"
                "💡 **Possible reasons:**\n"
                "• PDF file is corrupted\n"
                "• PDF format is not supported\n"
                "• PDF is password protected\n"
                "• Try with a different PDF file"
            )
            return
        
        # Send images
        total_pages = len(images)
        sent_count = 0
        
        await update.message.reply_text(
            f"✅ **PDF Converted Successfully!**\n\n"
            f"📄 Total pages: {total_pages}\n"
            f"🖼️ Sending images...\n\n"
            f"⏳ This may take a moment..."
        )
        
        for img_info in images:
            try:
                img_buffer = img_info['buffer']
                page_num = img_info['page_num']
                
                img_buffer.seek(0)
                
                # Check file size (Telegram limit is ~10MB for photos)
                file_size = img_info['size']
                max_size = 10 * 1024 * 1024  # 10MB
                
                if file_size > max_size:
                    # If too large, send as document
                    img_buffer.seek(0)
                    await update.message.reply_document(
                        document=img_buffer,
                        filename=f"page_{page_num}.png",
                        caption=f"📄 Page {page_num}/{total_pages}"
                    )
                else:
                    # Send as photo
                    img_buffer.seek(0)
                    await update.message.reply_photo(
                        photo=img_buffer,
                        caption=f"📄 Page {page_num}/{total_pages}"
                    )
                
                sent_count += 1
                logger.info(f"Sent page {page_num}/{total_pages}")
                
                # Small delay between sends to avoid rate limiting
                if sent_count < total_pages:
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Error sending page {page_num}: {e}")
                continue
        
        if sent_count > 0:
            await update.message.reply_text(
                f"✅ **Conversion Complete!**\n\n"
                f"📊 Successfully sent {sent_count}/{total_pages} pages"
            )
            logger.info(f"PDF to image conversion successful - {sent_count}/{total_pages} pages sent")
        else:
            await update.message.reply_text(
                "❌ **Failed to send images**\n\n"
                "Please try again or check the PDF file."
            )
    
    except Exception as e:
        logger.error(f"PDF to Image command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e)
        if "password" in error_msg.lower() or "encrypted" in error_msg.lower():
            detailed_msg = (
                "❌ **PDF is Password Protected**\n\n"
                "This PDF requires a password to open.\n\n"
                "💡 **Please:**\n"
                "• Remove password protection from the PDF\n"
                "• Or use an unprotected PDF file"
            )
        elif "corrupted" in error_msg.lower() or "invalid" in error_msg.lower():
            detailed_msg = (
                "❌ **PDF File is Corrupted or Invalid**\n\n"
                "The PDF file cannot be read.\n\n"
                "💡 **Please:**\n"
                "• Check if the PDF file is valid\n"
                "• Try with a different PDF file\n"
                "• Make sure the PDF is not corrupted"
            )
        else:
            detailed_msg = (
                f"❌ **Error converting PDF**\n\n"
                f"Error: {error_msg}\n\n"
                "💡 **Try:**\n"
                "• Make sure the PDF file is valid\n"
                "• Try with a different PDF\n"
                "• Ensure PyMuPDF is installed: `pip install PyMuPDF`"
            )
        
        await update.message.reply_text(detailed_msg)

async def textonimage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create image with text written on it."""
    if not context.args:
        await update.message.reply_text(
            "📝 **Text on Image**\n\n"
            "Usage: /textonimage <your text>\n\n"
            "**Examples:**\n"
            "• /textonimage Hello World\n"
            "• /textonimage Welcome to my channel\n"
            "• /textonimage Good Morning\n\n"
            "💡 Creates a beautiful image with your text written on it!"
        )
        return
    
    if not PIL_AVAILABLE:
        await update.message.reply_text(
            "❌ Text on image feature requires Pillow library.\n"
            "Install: `pip install Pillow`"
        )
        return
    
    if not IMAGEDRAW_AVAILABLE or ImageDraw is None:
        # Use alternative method: Generate image using online API with text
        text = ' '.join(context.args)
        processing_msg = await update.message.reply_text(
            "📝 Creating image with text using alternative method...\n"
            "⏳ This may take a moment..."
        )
        
        try:
            # Use image generation API with text prompt
            encoded_text = quote(text)
            image_url = f"https://image.pollinations.ai/prompt/a%20beautiful%20image%20with%20text%20that%20says%20{encoded_text}?width=800&height=400&enhance=true"
            
            loop = asyncio.get_event_loop()
            
            def download_image():
                response = requests.get(image_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code == 200:
                    img_buffer = io.BytesIO(response.content)
                    img_buffer.seek(0)
                    return img_buffer
                raise Exception("Failed to generate image")
            
            image_buffer = await loop.run_in_executor(None, download_image)
            
            try:
                await processing_msg.delete()
            except:
                pass
            
            await update.message.reply_photo(
                photo=image_buffer,
                caption=f"📝 **Text on Image**\n\n`{text}`",
                parse_mode='Markdown'
            )
            return
        except Exception as e:
            try:
                await processing_msg.delete()
            except:
                pass
            await update.message.reply_text(
                f"❌ **Error:** {str(e)}\n\n"
                "💡 ImageDraw is not available. Please install Pillow:\n"
                "`pip install Pillow`\n\n"
                "Or try using `/generate {text}` to create an image with text."
            )
            return
    
    text = ' '.join(context.args)
    
    if len(text) > 200:
        await update.message.reply_text(
            "❌ Text is too long! Please keep it under 200 characters."
        )
        return
    
    processing_msg = await update.message.reply_text("📝 Creating image with text...")
    
    try:
        loop = asyncio.get_event_loop()
        
        def create_text_image():
            try:
                if not PIL_AVAILABLE or not IMAGEDRAW_AVAILABLE or ImageDraw is None:
                    raise ImportError("ImageDraw not available")
                
                logger.info(f"Creating text image with text: {text[:50]}")
                
                # Create image dimensions
                width = 800
                height = 400
                
                # Create a beautiful background gradient
                img = Image.new('RGB', (width, height), color='#2c3e50')
                
                draw = ImageDraw.Draw(img)
                logger.info("ImageDraw created successfully")
                
                # Create gradient background (simplified for speed)
                # Use a simpler gradient approach
                for y in range(0, height, 2):  # Step by 2 for faster rendering
                    # Gradient from dark blue to lighter blue
                    r = int(44 + (y / height) * 30)
                    g = int(62 + (y / height) * 40)
                    b = int(80 + (y / height) * 50)
                    color = (r, g, b)
                    draw.line([(0, y), (width, y)], fill=color)
                    # Fill the next line with same color for speed
                    if y + 1 < height:
                        draw.line([(0, y + 1), (width, y + 1)], fill=color)
                
                logger.info("Background gradient created")
                
                # Calculate text size and position
                font_size = 60
                font = None
                
                try:
                    # Try to load default font first (fastest)
                    font = ImageFont.load_default()
                    logger.info("Using default font")
                except:
                    try:
                        # Try system fonts
                        font_paths = [
                            "C:/Windows/Fonts/arial.ttf",
                            "C:/Windows/Fonts/Arial.ttf",
                            "C:/Windows/Fonts/calibri.ttf",
                            "C:/Windows/Fonts/Calibri.ttf",
                        ]
                        for font_path in font_paths:
                            try:
                                font = ImageFont.truetype(font_path, font_size)
                                logger.info(f"Loaded font from {font_path}")
                                break
                            except:
                                continue
                    except Exception as e:
                        logger.warning(f"Font loading failed: {e}")
                        font = None
                
                if font is None:
                    logger.warning("No font available, using basic text rendering")
                
                # Split text into lines if too long (simplified approach)
                max_chars_per_line = 30
                words = text.split()
                lines = []
                current_line = ""
                
                for word in words:
                    if len(current_line) + len(word) + 1 <= max_chars_per_line:
                        if current_line:
                            current_line += " " + word
                        else:
                            current_line = word
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
                
                if current_line:
                    lines.append(current_line)
                
                # Limit to 3 lines
                if len(lines) > 3:
                    lines = lines[:3]
                
                logger.info(f"Text split into {len(lines)} lines")
                
                # Calculate total text height
                line_height = font_size + 20
                total_text_height = len(lines) * line_height
                
                # Center text vertically
                start_y = (height - total_text_height) // 2
                
                # Draw text with shadow for better visibility
                text_color = (255, 255, 255)  # White
                shadow_color = (0, 0, 0)  # Black shadow
                
                # Draw text lines
                for i, line in enumerate(lines):
                    y_pos = start_y + i * line_height
                    
                    # Get text width (simplified)
                    try:
                        if font:
                            # Use textbbox for Pillow 10+
                            bbox = draw.textbbox((0, 0), line, font=font)
                            text_width = bbox[2] - bbox[0]
                        else:
                            text_width = len(line) * 30
                    except Exception as e:
                        logger.warning(f"Text width calculation failed: {e}, using estimate")
                        text_width = len(line) * (font_size // 2)
                    
                    # Center horizontally
                    x_pos = (width - text_width) // 2
                    
                    # Draw text with shadow
                    try:
                        if font:
                            # Draw shadow first
                            draw.text((x_pos + 2, y_pos + 2), line, font=font, fill=shadow_color)
                            # Draw main text
                            draw.text((x_pos, y_pos), line, font=font, fill=text_color)
                        else:
                            # Basic text without font
                            draw.text((x_pos + 2, y_pos + 2), line, fill=shadow_color)
                            draw.text((x_pos, y_pos), line, fill=text_color)
                    except Exception as e:
                        logger.error(f"Error drawing text line {i}: {e}")
                        raise
                
                logger.info("Text drawn successfully")
                
                # Save to buffer
                output_buffer = io.BytesIO()
                img.save(output_buffer, format='PNG')  # PNG doesn't support quality parameter
                output_buffer.seek(0)
                
                # Verify buffer has content
                if len(output_buffer.getvalue()) == 0:
                    raise Exception("Failed to save image to buffer")
                
                return output_buffer
            
            except Exception as e:
                logger.error(f"Text on image creation error: {e}", exc_info=True)
                raise
        
        try:
            image_buffer = await asyncio.wait_for(
                loop.run_in_executor(None, create_text_image),
                timeout=30.0  # 30 second timeout
            )
        except asyncio.TimeoutError:
            try:
                await processing_msg.delete()
            except:
                pass
            await update.message.reply_text(
                "❌ **Timeout:** Image creation took too long.\n\n"
                "💡 Try using shorter text or try again."
            )
            return
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Verify buffer has content
        image_buffer.seek(0, 2)
        buffer_size = image_buffer.tell()
        image_buffer.seek(0)
        
        if buffer_size == 0:
            raise Exception("Created image buffer is empty")
        
        await update.message.reply_photo(
            photo=image_buffer,
            caption=f"📝 **Text on Image**\n\n`{text}`",
            parse_mode='Markdown'
        )
    
    except Exception as e:
        logger.error(f"Text on image command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"❌ **Error creating text image:**\n\n{str(e)}\n\n"
            "💡 **Try:**\n"
            "• Make sure Pillow is installed: `pip install Pillow`\n"
            "• Use shorter text\n"
            "• Try again"
        )

async def tiktok_download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download TikTok video from URL."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        await update.message.reply_text(
            "🎵 **TikTok Video Download**\n\n"
            "Usage: /tiktok <TikTok URL> or /tt <TikTok URL>\n\n"
            "**Examples:**\n"
            "• /tiktok https://www.tiktok.com/@username/video/1234567890\n"
            "• /tt https://vm.tiktok.com/xxxxx/\n"
            "• /tiktok https://tiktok.com/t/xxxxx/\n\n"
            "💡 Just send the TikTok video URL and I'll download it for you!"
        )
        return
    
    url = ' '.join(context.args)
    
    # Extract TikTok URL from message
    if not url.startswith('http'):
        # Check if it's in the message text
        url_pattern = r'(https?://(?:www\.)?(?:tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/[^\s]+)'
        match = re.search(url_pattern, url)
        if match:
            url = match.group(1)
        else:
            await update.message.reply_text(
                "❌ Please provide a valid TikTok URL!\n\n"
                "Example: /tiktok https://www.tiktok.com/@username/video/1234567890"
            )
            return
    
    processing_msg = await update.message.reply_text("🎵 Downloading TikTok video...\n⏳ Please wait...")
    
    try:
        loop = asyncio.get_event_loop()
        
        def download_tiktok_video(video_url):
            try:
                # Try multiple TikTok download APIs
                api_urls = [
                    f"https://api.tiklydown.eu.org/api/download?url={quote(video_url)}",
                    f"https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/feed/?aweme_id={video_url.split('/')[-1]}",
                ]
                
                # Method 1: Try Tiklydown API (free, no API key)
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'application/json',
                        'Referer': 'https://tiklydown.eu.org/'
                    }
                    
                    response = requests.get(api_urls[0], headers=headers, timeout=30, allow_redirects=True)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            
                            # Check different response formats
                            if isinstance(data, dict):
                                # Try different response structures
                                video_url = None
                                video_info = None
                                
                                # Format 1: {video: {url: ...}, ...}
                                if 'video' in data and isinstance(data['video'], dict):
                                    video_url = data['video'].get('url') or data['video'].get('download')
                                    video_info = data.get('video', {})
                                
                                # Format 2: {data: {play: ...}, ...}
                                elif 'data' in data and isinstance(data['data'], dict):
                                    video_url = data['data'].get('play') or data['data'].get('url')
                                    video_info = data.get('data', {})
                                
                                # Format 3: Direct url field
                                elif 'url' in data:
                                    video_url = data['url']
                                    video_info = data
                                
                                # Format 4: {result: {video: {url: ...}}}
                                elif 'result' in data and isinstance(data['result'], dict):
                                    result = data['result']
                                    if 'video' in result:
                                        video_url = result['video'].get('url') or result['video'].get('download')
                                        video_info = result.get('video', {})
                                    else:
                                        video_url = result.get('url') or result.get('play')
                                        video_info = result
                                
                                if video_url:
                                    # Download the video
                                    video_response = requests.get(video_url, headers=headers, timeout=60, stream=True)
                                    
                                    if video_response.status_code == 200:
                                        video_buffer = io.BytesIO()
                                        for chunk in video_response.iter_content(chunk_size=8192):
                                            if chunk:
                                                video_buffer.write(chunk)
                                        video_buffer.seek(0)
                                        
                                        # Get video info
                                        author = video_info.get('author', {}).get('nickname') if isinstance(video_info, dict) else None
                                        description = video_info.get('desc') or video_info.get('description') or video_info.get('title', '')
                                        
                                        return {
                                            'video': video_buffer,
                                            'author': author,
                                            'description': description[:200] if description else None
                                        }
                        except Exception as json_error:
                            logger.warning(f"JSON parsing failed: {json_error}, trying alternative method")
                
                except Exception as api_error:
                    logger.warning(f"Tiklydown API failed: {api_error}")
                
                # Method 2: Try alternative API
                try:
                    alt_api = f"https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/feed/?aweme_id={video_url}"
                    headers = {
                        'User-Agent': 'com.ss.android.ugc.trill/494 (Linux; U; Android 10; en_US; Pixel 4; Build/QQ3A.200805.001; Cronet/58.0.2991.0)',
                        'Accept': 'application/json',
                    }
                    response = requests.get(alt_api, headers=headers, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        # Parse TikTok API response
                        if 'aweme_list' in data and len(data['aweme_list']) > 0:
                            aweme = data['aweme_list'][0]
                            video_url = aweme.get('video', {}).get('play_addr', {}).get('url_list', [])
                            if video_url:
                                video_response = requests.get(video_url[0], headers=headers, timeout=60, stream=True)
                                if video_response.status_code == 200:
                                    video_buffer = io.BytesIO()
                                    for chunk in video_response.iter_content(chunk_size=8192):
                                        if chunk:
                                            video_buffer.write(chunk)
                                    video_buffer.seek(0)
                                    
                                    author = aweme.get('author', {}).get('nickname', '')
                                    description = aweme.get('desc', '')
                                    
                                    return {
                                        'video': video_buffer,
                                        'author': author,
                                        'description': description[:200] if description else None
                                    }
                except Exception as alt_error:
                    logger.warning(f"Alternative API failed: {alt_error}")
                
                # Method 3: Try TikTok downloader API (another service)
                try:
                    downloader_api = f"https://tikwm.com/api/?url={quote(video_url)}&hd=1"
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json',
                    }
                    response = requests.get(downloader_api, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('code') == 0 and 'data' in data:
                            video_data = data['data']
                            video_url = video_data.get('hdplay') or video_data.get('play') or video_data.get('wmplay')
                            
                            if video_url:
                                video_response = requests.get(video_url, headers=headers, timeout=60, stream=True)
                                if video_response.status_code == 200:
                                    video_buffer = io.BytesIO()
                                    for chunk in video_response.iter_content(chunk_size=8192):
                                        if chunk:
                                            video_buffer.write(chunk)
                                    video_buffer.seek(0)
                                    
                                    author = video_data.get('author', {}).get('nickname', '')
                                    description = video_data.get('desc', '')
                                    
                                    return {
                                        'video': video_buffer,
                                        'author': author,
                                        'description': description[:200] if description else None
                                    }
                except Exception as tikwm_error:
                    logger.warning(f"TikWM API failed: {tikwm_error}")
                
                # All methods failed
                raise Exception("Could not download video. The URL might be invalid or the video is unavailable.")
            
            except Exception as e:
                logger.error(f"TikTok download error: {e}", exc_info=True)
                raise
        
        # Download video in executor
        result = await asyncio.wait_for(
            loop.run_in_executor(None, download_tiktok_video, url),
            timeout=120.0  # 2 minute timeout
        )
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Prepare caption
        caption = "🎵 **TikTok Video Downloaded**"
        if result.get('author'):
            caption += f"\n👤 Author: {result['author']}"
        if result.get('description'):
            caption += f"\n📝 {result['description']}"
        
        # Send video
        video_buffer = result['video']
        video_buffer.seek(0, 2)
        file_size = video_buffer.tell()
        video_buffer.seek(0)
        
        # Check file size (Telegram limit is ~50MB)
        if file_size > 50 * 1024 * 1024:
            await update.message.reply_text(
                "❌ Video is too large (>50MB). Telegram cannot send files larger than 50MB."
            )
            return
        
        await update.message.reply_video(
            video=video_buffer,
            caption=caption,
            parse_mode='Markdown',
            supports_streaming=True
        )
        
        logger.info(f"TikTok video downloaded successfully: {url}")
    
    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ **Timeout:** Download took too long.\n\n"
            "💡 The video might be very large or the service is busy. Please try again."
        )
    except Exception as e:
        logger.error(f"TikTok download command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e)
        if "Could not download" in error_msg:
            error_msg = "Could not download the video. Please check the URL and try again."
        elif "timeout" in error_msg.lower():
            error_msg = "Download timed out. Please try again."
        
        await update.message.reply_text(
            f"❌ **Error downloading TikTok video:**\n\n{error_msg}\n\n"
            "💡 **Try:**\n"
            "• Make sure the TikTok URL is valid\n"
            "• Copy the full URL from TikTok app/website\n"
            "• Try again in a few moments"
        )

async def youtube_download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download YouTube video from URL."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        await update.message.reply_text(
            "📺 **YouTube Video Download**\n\n"
            "Usage: /yt <YouTube URL> [quality]\n"
            "       /youtube <YouTube URL> [quality]\n\n"
            "**Quality options:**\n"
            "• `360` - Standard quality (default, recommended for fast uploads)\n"
            "• `480` - Good quality\n"
            "• `720` - HD quality\n"
            "• `1024` - Full HD quality (larger file, may take longer)\n\n"
            "**Examples:**\n"
            "• /yt https://www.youtube.com/watch?v=VIDEO_ID\n"
            "• /yt https://www.youtube.com/watch?v=VIDEO_ID 1024\n"
            "• /youtube https://youtu.be/VIDEO_ID 720\n"
            "• /yt https://www.youtube.com/shorts/VIDEO_ID 480\n\n"
            "💡 Higher quality = larger file size. Default is 360p for reliable uploads."
        )
        return

    # Parse arguments - check for quality parameter
    args = context.args
    url = None
    quality = None
    
    # Look for quality parameter (number at the end or as separate arg)
    for i, arg in enumerate(args):
        if arg.isdigit():
            quality = int(arg)
            # Remove quality from args
            args = args[:i] + args[i+1:]
            break
    
    # Join remaining args as URL
    url = ' '.join(args)
    
    # Extract YouTube URL
    if not url.startswith('http'):
        url_pattern = r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s]+)'
        match = re.search(url_pattern, url)
        if match:
            url = match.group(1)
        else:
            await update.message.reply_text(
                "❌ Please provide a valid YouTube URL!\n\n"
                "Example: /yt https://www.youtube.com/watch?v=VIDEO_ID"
            )
            return
    
    processing_msg = await update.message.reply_text("📺 Downloading YouTube video...\n⏳ Please wait...")
    
    try:
        loop = asyncio.get_event_loop()
        
        def download_youtube_video(video_url, requested_quality=None):
            import tempfile
            import os as os_module
            tmp_path = None
            
            # Initialize max_file_size_mb early to avoid UnboundLocalError
            # Set default value first, then adjust based on requested quality
            max_file_size_mb = 30  # Default: 30MB for lower quality (better upload reliability)
            if requested_quality and requested_quality >= 1024:
                max_file_size_mb = 50  # Allow up to 50MB for 1024p+ videos
            elif requested_quality and requested_quality >= 720:
                max_file_size_mb = 40  # Allow up to 40MB for 720p videos
            
            try:
                logger.info(f"Attempting to download YouTube video: {video_url}, requested quality: {requested_quality}")

                # Use yt-dlp for reliable downloading
                video_buffer = io.BytesIO()

                def progress_hook(d):
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes', 0)
                        speed = d.get('speed', 0)
                        if total:
                            pct = downloaded / total * 100
                            downloaded_mb = downloaded / (1024 * 1024)
                            total_mb = total / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0
                            logger.info(f"Downloading... {pct:.2f}% ({downloaded_mb:.2f}/{total_mb:.2f} MB) at {speed_mb:.2f} MB/s")
                        else:
                            downloaded_mb = downloaded / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0
                            logger.info(f"Downloading... {downloaded_mb:.2f} MB at {speed_mb:.2f} MB/s")
                    elif d['status'] == 'finished':
                        logger.info("Download completed, processing file...")

                # Get video info first to check size and get metadata
                info_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'socket_timeout': 30,  # Socket timeout in seconds
                }
                
                title = None
                duration_str = ''
                
                try:
                    with YoutubeDL(info_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                        title = info.get('title', '')[:200] if info.get('title') else None
                        duration = info.get('duration', 0)
                        if duration:
                            duration_str = f"{duration // 60}:{duration % 60:02d}"
                        
                        # Check file size and suggest quality
                        filesize = info.get('filesize') or info.get('filesize_approx', 0)
                        max_size_mb = 30  # Reduced to 30MB for reliable uploads
                        max_size = max_size_mb * 1024 * 1024
                        suggested_quality = None
                        
                        if filesize:
                            logger.info(f"Video estimated size: {filesize / (1024*1024):.2f} MB")
                            # Suggest quality based on estimated size (conservative to ensure upload success)
                            if filesize > max_size * 1.5:  # Much larger than 30MB
                                suggested_quality = 240  # Very low quality
                            elif filesize > max_size * 1.2:  # 20% larger than 30MB
                                suggested_quality = 360  # Low quality
                            elif filesize > max_size:
                                suggested_quality = 360  # Low quality
                            else:
                                suggested_quality = 360  # Keep it low for reliable uploads
                        
                        logger.info(f"Video info retrieved: {title}, duration: {duration_str}, size: {filesize} bytes, suggested quality: {suggested_quality}p")
                except Exception as info_error:
                    logger.warning(f"Could not get video info: {info_error}, will try to download anyway")

                # Create temporary file for download - yt-dlp will add extension
                temp_dir = tempfile.gettempdir()
                base_name = f"yt_download_{os_module.getpid()}"
                tmp_path_pattern = os_module.path.join(temp_dir, base_name + ".%(ext)s")
                
                logger.info(f"Downloading to temp file pattern: {tmp_path_pattern}")
                
                # Determine starting quality
                # If user requested specific quality, use it (but warn about file size)
                # Otherwise use estimated quality or default to 360p
                if requested_quality:
                    start_quality = requested_quality
                    logger.info(f"Using requested quality: {start_quality}p (file may be larger)")
                else:
                    # Use suggested quality based on file size, or default to 360p
                    start_quality = suggested_quality if suggested_quality else 360
                    if start_quality > 360:
                        start_quality = 360  # Default to 360p to ensure smaller file size and faster uploads
                    logger.info(f"Using auto-selected quality: {start_quality}p")
                
                # Download options - use single combined format (no FFmpeg needed)
                # Format selector: start with requested/selected quality
                # max_file_size_mb was already set at the beginning of the function
                ydl_opts = {
                    'format': f'best[height<={start_quality}][ext=mp4]/best[height<={start_quality}]/best[ext=mp4]/best',
                    'outtmpl': tmp_path_pattern,
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [progress_hook],
                    'noplaylist': True,
                    'max_filesize': max_file_size_mb * 1024 * 1024,  # 30MB limit for reliable uploads
                    'socket_timeout': 30,  # Socket timeout in seconds
                    'retries': 3,  # Number of retries for fragments
                    'fragment_retries': 3,  # Number of retries for fragments
                }

                # Download video with progressive quality fallback
                download_success = False
                last_error = None
                # Quality fallback levels - only fallback if not user-requested quality
                if requested_quality:
                    # If user requested specific quality, try that and one level below, then fallback
                    if requested_quality >= 1024:
                        quality_levels = [start_quality, 720, 480, 360]
                    elif requested_quality >= 720:
                        quality_levels = [start_quality, 480, 360, 240]
                    else:
                        quality_levels = [start_quality, 240, 144, 'worst']
                else:
                    # Auto-selected quality - more aggressive fallback
                    quality_levels = [start_quality, 240, 144, 'worst']
                current_quality_index = 0
                
                while not download_success and current_quality_index < len(quality_levels):
                    try:
                        quality = quality_levels[current_quality_index]
                        if isinstance(quality, int):
                            ydl_opts['format'] = f'best[height<={quality}][ext=mp4]/best[height<={quality}]/best[ext=mp4]/best'
                            logger.info(f"Trying download with quality: {quality}p")
                        else:
                            ydl_opts['format'] = 'worst[ext=mp4]/worst'  # Last resort - lowest quality
                            logger.info(f"Trying download with lowest quality available")
                        
                        with YoutubeDL(ydl_opts) as ydl:
                            ydl.download([video_url])
                        download_success = True
                        logger.info(f"Download successful with quality: {quality_levels[current_quality_index]}")
                    except Exception as download_err:
                        last_error = download_err
                        logger.warning(f"Download failed with quality {quality_levels[current_quality_index]}: {download_err}")
                        current_quality_index += 1
                        if current_quality_index < len(quality_levels):
                            logger.info(f"Trying next quality level...")
                
                if not download_success:
                    raise Exception(f"Download failed after trying all quality levels: {last_error}")
                
                # Find the actual downloaded file (yt-dlp replaces %(ext)s with actual extension)
                actual_file = None
                # Try common extensions
                possible_extensions = ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']
                for ext in possible_extensions:
                    test_path = os_module.path.join(temp_dir, base_name + ext)
                    if os_module.path.exists(test_path):
                        actual_file = test_path
                        tmp_path = test_path  # Update tmp_path for cleanup
                        logger.info(f"Found downloaded file: {actual_file}")
                        break
                
                if not actual_file:
                    # Try to find any file with the base name
                    import glob
                    pattern = os_module.path.join(temp_dir, base_name + ".*")
                    matches = glob.glob(pattern)
                    if matches:
                        actual_file = matches[0]
                        tmp_path = actual_file
                        logger.info(f"Found downloaded file via glob: {actual_file}")
                    else:
                        raise Exception(f"Downloaded file not found. Searched for pattern: {base_name}.* in {temp_dir}")
                
                # Read the file into buffer and check size
                file_size = os_module.path.getsize(actual_file)
                # Use the max_file_size_mb that was determined earlier
                max_size = max_file_size_mb * 1024 * 1024
                file_size_mb = file_size / (1024 * 1024)
                logger.info(f"Downloaded file size: {file_size_mb:.2f} MB ({file_size} bytes), limit: {max_file_size_mb}MB")
                
                if file_size > max_size:
                    raise Exception(f"Video file too large ({file_size_mb:.2f} MB). Limit is {max_file_size_mb}MB. Please try a shorter video or lower quality.")
                
                with open(actual_file, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        video_buffer.write(chunk)
                
                video_buffer.seek(0)
                
                logger.info(f"Successfully downloaded video ({file_size} bytes)")
                return {
                    'video': video_buffer,
                    'title': title,
                    'duration': duration_str
                }
                    
            except Exception as e:
                logger.error(f"YouTube download error: {e}", exc_info=True)
                error_msg = str(e)
                if "Video file too large" in error_msg:
                    raise Exception("Video file too large (>50MB). Please try a shorter video or lower quality.")
                elif "unavailable" in error_msg.lower() or "private" in error_msg.lower():
                    raise Exception("Could not download video. The video might be private, unavailable, or restricted.")
                else:
                    raise Exception(f"Could not download video: {error_msg}")
            finally:
                # Clean up temp file
                if tmp_path and os_module.path.exists(tmp_path):
                    try:
                        os_module.unlink(tmp_path)
                        logger.info(f"Cleaned up temp file: {tmp_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Could not delete temp file: {cleanup_error}")
        
        # Download video with longer timeout for larger files
        # Timeout increased to 10 minutes (600 seconds) to handle slower connections and larger files
        result = await asyncio.wait_for(
            loop.run_in_executor(None, download_youtube_video, url, quality),
            timeout=600.0
        )
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Prepare caption
        caption = "📺 **YouTube Video Downloaded**"
        if result.get('title'):
            caption += f"\n📝 {result['title']}"
        if result.get('duration'):
            caption += f"\n⏱ Duration: {result['duration']}"

        # Send video
        video_buffer = result['video']
        video_buffer.seek(0, 2)
        file_size = video_buffer.tell()
        video_buffer.seek(0)

        # Dynamic limit based on requested quality
        max_allowed_mb = 50 if quality and quality >= 1024 else (40 if quality and quality >= 720 else 30)
        if file_size > max_allowed_mb * 1024 * 1024:
            await update.message.reply_text(
                f"❌ Video is too large ({file_size / (1024*1024):.2f}MB). Limit is {max_allowed_mb}MB.\n\n"
                "**To ensure successful uploads:**\n"
                "• Try a shorter video (under 2-3 minutes)\n"
                "• Try lower quality (e.g., /yt <URL> 720 or /yt <URL> 480)\n"
                "• Smaller files upload much faster and more reliably\n\n"
                f"💡 **Tip:** Videos under {max_allowed_mb-10}MB work best for {quality}p quality!"
            )
            return

        # Send video with retry logic for Telegram API timeouts
        from telegram.error import TimedOut, NetworkError
        max_retries = 3
        retry_count = 0
        sent = False
        
        while not sent and retry_count < max_retries:
            try:
                # Reset buffer position for retry
                video_buffer.seek(0)
                
                await update.message.reply_video(
                    video=video_buffer,
                    caption=caption,
                    parse_mode='Markdown',
                    supports_streaming=True
                )
                sent = True
                logger.info(f"Video sent successfully to Telegram ({file_size / (1024*1024):.2f} MB)")
            except (TimedOut, NetworkError) as tg_error:
                retry_count += 1
                logger.warning(f"Telegram API timeout/error (attempt {retry_count}/{max_retries}): {tg_error}")
                if retry_count < max_retries:
                    # Wait before retry (exponential backoff)
                    wait_time = retry_count * 2
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    # All retries failed - show user-friendly message
                    logger.error(f"Failed to upload video to Telegram after {max_retries} attempts")
                    await update.message.reply_text(
                        "❌ **Upload Failed:** Could not upload video to Telegram after multiple attempts.\n\n"
                        "**The video file is likely too large or your connection is too slow.**\n\n"
                        "**What you can try:**\n"
                        "• Try a much shorter video (under 2-3 minutes)\n"
                        "• Check your internet upload speed\n"
                        "• Try again when you have a faster connection\n"
                        "• The video quality will be automatically reduced to fit under 50MB\n\n"
                        "💡 **Tip:** Videos under 20MB upload much faster and more reliably.\n"
                        "   Very long videos may need to be split into parts."
                    )
                    return
            except Exception as send_error:
                # Other errors, don't retry
                logger.error(f"Error sending video to Telegram: {send_error}")
                raise

        logger.info(f"YouTube video downloaded successfully: {url}")

    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ **Timeout Error:** Download took too long (10 minutes limit).\n\n"
            "**Possible reasons:**\n"
            "• Your internet connection is slow\n"
            "• The video is very large or long\n"
            "• YouTube servers are slow or busy\n\n"
            "**What you can try:**\n"
            "• Check your internet connection\n"
            "• Try a shorter video (under 5-10 minutes)\n"
            "• Try again later when network conditions are better\n"
            "• Use a video with lower quality\n\n"
            "💡 **Tip:** Shorter videos download faster and are more likely to stay under the 30MB limit for reliable uploads."
        )
    except Exception as e:
        logger.error(f"YouTube download command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass

        error_msg = str(e)
        # Check for Telegram API timeout errors
        from telegram.error import TimedOut as TelegramTimedOut
        if isinstance(e, TelegramTimedOut) or "Timed out" in error_msg or "TimedOut" in error_msg:
            await update.message.reply_text(
                "❌ **Upload Timeout:** Failed to upload video to Telegram.\n\n"
                "**Possible reasons:**\n"
                "• Your internet connection is too slow for upload\n"
                "• The video file is too large to upload in time\n"
                "• Telegram servers are busy\n\n"
                "**What you can try:**\n"
                "• Check your internet connection (upload speed)\n"
                "• Try a shorter video (under 3-5 minutes)\n"
                "• Try again later\n"
                "• Download in lower quality (smaller file size)\n\n"
                "💡 **Tip:** Videos under 30MB upload much faster and more reliably."
            )
            return
        elif "Could not download" in error_msg or "unavailable" in error_msg.lower():
            detailed_msg = (
                "❌ **Could not download YouTube video.**\n\n"
                "**Possible reasons:**\n"
                "• YouTube has blocked download services\n"
                "• The video URL format is not supported\n"
                "• The video might be private or restricted\n"
                "• Download services are temporarily down\n\n"
                "**What you can try:**\n"
                "• Make sure the video is public and accessible\n"
                "• Use the full YouTube URL\n"
                "• Format: `https://www.youtube.com/watch?v=VIDEO_ID`\n"
                "• Or: `https://youtu.be/VIDEO_ID`\n"
                "• Wait a few minutes and try again\n\n"
                "**Note:** YouTube frequently updates their API, which can break download services."
            )
        elif "timeout" in error_msg.lower():
            detailed_msg = "Download timed out. The video might be very large. Please try again."
        elif "too large" in error_msg.lower():
            detailed_msg = "Video is too large (>50MB). Telegram cannot send files larger than 50MB. Try a shorter video."
        else:
            detailed_msg = f"Error: {error_msg}\n\nPlease try again or use a different video URL."
        
        await update.message.reply_text(detailed_msg)

async def facebook_download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download Facebook video from URL."""
    if not context.args:
        await update.message.reply_text(
            "📘 **Facebook Video Download**\n\n"
            "Usage: /fb <Facebook URL> or /facebook <Facebook URL>\n\n"
            "**Examples:**\n"
            "• /fb https://www.facebook.com/watch/?v=1234567890\n"
            "• /facebook https://fb.watch/xxxxx/\n"
            "• /fb https://www.facebook.com/username/videos/1234567890\n"
            "• /fb https://m.facebook.com/watch/?v=1234567890\n\n"
            "💡 Just send the Facebook video URL and I'll download it for you!"
        )
        return
    
    url = ' '.join(context.args)
    
    # Extract Facebook URL from message
    if not url.startswith('http'):
        # Check if it's in the message text
        url_pattern = r'(https?://(?:www\.|m\.)?(?:facebook\.com|fb\.com|fb\.watch)/[^\s]+)'
        match = re.search(url_pattern, url)
        if match:
            url = match.group(1)
        else:
            await update.message.reply_text(
                "❌ Please provide a valid Facebook URL!\n\n"
                "Example: /fb https://www.facebook.com/watch/?v=1234567890"
            )
            return
    
    processing_msg = await update.message.reply_text("📘 Downloading Facebook video...\n⏳ Please wait...")
    
    try:
        loop = asyncio.get_event_loop()
        
        def download_facebook_video(video_url):
            import tempfile
            import os as os_module
            tmp_path = None
            
            # Initialize max_file_size_mb early to avoid UnboundLocalError
            max_file_size_mb = 30  # Default: 30MB for reliable uploads
            
            try:
                logger.info(f"Attempting to download Facebook video: {video_url}")
                
                # Use yt-dlp for reliable downloading (supports Facebook)
                video_buffer = io.BytesIO()
                
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes', 0)
                        speed = d.get('speed', 0)
                        if total:
                            pct = downloaded / total * 100
                            downloaded_mb = downloaded / (1024 * 1024)
                            total_mb = total / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0
                            logger.info(f"Downloading... {pct:.2f}% ({downloaded_mb:.2f}/{total_mb:.2f} MB) at {speed_mb:.2f} MB/s")
                        else:
                            downloaded_mb = downloaded / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0
                            logger.info(f"Downloading... {downloaded_mb:.2f} MB at {speed_mb:.2f} MB/s")
                    elif d['status'] == 'finished':
                        logger.info("Download completed, processing file...")
                
                # Get video info first
                info_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'socket_timeout': 30,
                }
                
                title = None
                duration_str = ''
                
                try:
                    with YoutubeDL(info_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                        title = info.get('title', '')[:200] if info.get('title') else None
                        duration = info.get('duration', 0)
                        if duration:
                            duration_str = f"{duration // 60}:{duration % 60:02d}"
                        logger.info(f"Facebook video info retrieved: {title}, duration: {duration_str}")
                except Exception as info_error:
                    logger.warning(f"Could not get video info: {info_error}, will try to download anyway")
                
                # Create temporary file for download
                temp_dir = tempfile.gettempdir()
                base_name = f"fb_download_{os_module.getpid()}"
                tmp_path_pattern = os_module.path.join(temp_dir, base_name + ".%(ext)s")
                
                logger.info(f"Downloading to temp file pattern: {tmp_path_pattern}")
                
                # Download options - use best quality but limit file size
                ydl_opts = {
                    'format': 'best[ext=mp4]/best[height<=720]/best',
                    'outtmpl': tmp_path_pattern,
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [progress_hook],
                    'noplaylist': True,
                    'max_filesize': max_file_size_mb * 1024 * 1024,
                    'socket_timeout': 30,
                    'retries': 3,
                    'fragment_retries': 3,
                }
                
                # Download video
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([video_url])
                
                # Find the actual downloaded file
                actual_file = None
                possible_extensions = ['.mp4', '.webm', '.mkv']
                for ext in possible_extensions:
                    test_path = os_module.path.join(temp_dir, base_name + ext)
                    if os_module.path.exists(test_path):
                        actual_file = test_path
                        tmp_path = test_path
                        logger.info(f"Found downloaded file: {actual_file}")
                        break
                
                if not actual_file:
                    import glob
                    pattern = os_module.path.join(temp_dir, base_name + ".*")
                    matches = glob.glob(pattern)
                    if matches:
                        actual_file = matches[0]
                        tmp_path = actual_file
                        logger.info(f"Found downloaded file via glob: {actual_file}")
                    else:
                        raise Exception(f"Downloaded file not found. Searched for pattern: {base_name}.* in {temp_dir}")
                
                # Read the file into buffer and check size
                file_size = os_module.path.getsize(actual_file)
                max_size = max_file_size_mb * 1024 * 1024
                file_size_mb = file_size / (1024 * 1024)
                logger.info(f"Downloaded file size: {file_size_mb:.2f} MB ({file_size} bytes), limit: {max_file_size_mb}MB")
                
                if file_size > max_size:
                    raise Exception(f"Video file too large ({file_size_mb:.2f} MB). Limit is {max_file_size_mb}MB. Please try a shorter video.")
                
                with open(actual_file, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        video_buffer.write(chunk)
                
                video_buffer.seek(0)
                
                logger.info(f"Successfully downloaded Facebook video ({file_size} bytes)")
                return {
                    'video': video_buffer,
                    'title': title,
                    'duration': duration_str
                }
            
            except Exception as e:
                logger.error(f"Facebook download error: {e}", exc_info=True)
                error_msg = str(e)
                if "Video file too large" in error_msg:
                    raise Exception("Video file too large (>30MB). Please try a shorter video.")
                elif "unavailable" in error_msg.lower() or "private" in error_msg.lower() or "access" in error_msg.lower():
                    raise Exception("Could not download video. The video might be private, unavailable, or restricted.")
                else:
                    raise Exception(f"Could not download video: {error_msg}")
            finally:
                # Clean up temp file
                if tmp_path and os_module.path.exists(tmp_path):
                    try:
                        os_module.unlink(tmp_path)
                        logger.info(f"Cleaned up temp file: {tmp_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Could not delete temp file: {cleanup_error}")
        
        # Download video with timeout (600 seconds for larger files)
        result = await asyncio.wait_for(
            loop.run_in_executor(None, download_facebook_video, url),
            timeout=600.0
        )
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Prepare caption
        caption = "📘 **Facebook Video Downloaded**"
        if result.get('title'):
            caption += f"\n📝 {result['title']}"
        if result.get('duration'):
            caption += f"\n⏱ Duration: {result['duration']}"
        
        # Send video
        video_buffer = result['video']
        video_buffer.seek(0, 2)
        file_size = video_buffer.tell()
        video_buffer.seek(0)
        
        # Check file size (Telegram limit is ~50MB)
        max_allowed_mb = 30
        if file_size > max_allowed_mb * 1024 * 1024:
            await update.message.reply_text(
                f"❌ Video is too large ({file_size / (1024*1024):.2f}MB). Limit is {max_allowed_mb}MB.\n\n"
                "**To ensure successful uploads:**\n"
                "• Try a shorter video (under 2-3 minutes)\n"
                "• Smaller files upload much faster and more reliably\n\n"
                "💡 **Tip:** Videos under 20MB work best for reliable uploads!"
            )
            return
        
        # Send video with retry logic for Telegram API timeouts
        from telegram.error import TimedOut, NetworkError
        max_retries = 3
        retry_count = 0
        sent = False
        
        while not sent and retry_count < max_retries:
            try:
                # Reset buffer position for retry
                video_buffer.seek(0)
                
                await update.message.reply_video(
                    video=video_buffer,
                    caption=caption,
                    parse_mode='Markdown',
                    supports_streaming=True
                )
                sent = True
                logger.info(f"Facebook video sent successfully to Telegram ({file_size / (1024*1024):.2f} MB)")
            except (TimedOut, NetworkError) as tg_error:
                retry_count += 1
                logger.warning(f"Telegram API timeout/error (attempt {retry_count}/{max_retries}): {tg_error}")
                if retry_count < max_retries:
                    wait_time = retry_count * 2
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to upload Facebook video to Telegram after {max_retries} attempts")
                    await update.message.reply_text(
                        "❌ **Upload Failed:** Could not upload video to Telegram after multiple attempts.\n\n"
                        "**The video file is likely too large or your connection is too slow.**\n\n"
                        "**What you can try:**\n"
                        "• Try a much shorter video (under 2-3 minutes)\n"
                        "• Check your internet upload speed\n"
                        "• Try again when you have a faster connection\n\n"
                        "💡 **Tip:** Videos under 20MB upload much faster and more reliably."
                    )
                    return
            except Exception as send_error:
                logger.error(f"Error sending Facebook video to Telegram: {send_error}")
                raise
        
        logger.info(f"Facebook video downloaded successfully: {url}")
    
    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ **Timeout Error:** Download took too long (10 minutes limit).\n\n"
            "**Possible reasons:**\n"
            "• Your internet connection is slow\n"
            "• The video is very large or long\n"
            "• Facebook servers are slow or busy\n\n"
            "**What you can try:**\n"
            "• Check your internet connection\n"
            "• Try a shorter video (under 5-10 minutes)\n"
            "• Try again later when network conditions are better\n\n"
            "💡 **Tip:** Shorter videos download faster and are more likely to stay under the 30MB limit."
        )
    except Exception as e:
        logger.error(f"Facebook download command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e)
        detailed_msg = ""
        
        if "Could not download" in error_msg or "unavailable" in error_msg.lower():
            detailed_msg = (
                "❌ **Could not download Facebook video.**\n\n"
                "**Possible reasons:**\n"
                "• The video is private or restricted\n"
                "• The video URL format is not supported\n"
                "• Facebook has blocked the download\n"
                "• Download services are temporarily down\n\n"
                "**What you can try:**\n"
                "• Make sure the video is public and accessible\n"
                "• Use the full Facebook URL\n"
                "• Format: `https://www.facebook.com/watch/?v=VIDEO_ID`\n"
                "• Or: `https://www.facebook.com/username/videos/VIDEO_ID`\n"
                "• Or: `https://fb.watch/xxxxx/`\n"
                "• Wait a few minutes and try again\n\n"
                "**Note:** Facebook frequently updates their API, which can affect downloads."
            )
        elif "timeout" in error_msg.lower():
            detailed_msg = "Download timed out. The video might be very large. Please try again."
        elif "too large" in error_msg.lower():
            detailed_msg = "Video is too large (>30MB). Telegram cannot send files larger than 50MB. Try a shorter video."
        elif "private" in error_msg.lower():
            detailed_msg = "This video is private or unavailable. Only public videos can be downloaded."
        else:
            detailed_msg = f"Error: {error_msg}\n\nPlease try again or use a different video URL."
        
        await update.message.reply_text(detailed_msg)

# Old API-based code removed - now using yt-dlp for Facebook downloads

async def instagram_download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download Instagram video/image from URL using yt-dlp."""
    if not context.args:
        await update.message.reply_text(
            "📷 **Instagram Video/Image Download**\n\n"
            "Usage: /ig <Instagram URL> or /instagram <Instagram URL>\n\n"
            "**Examples:**\n"
            "• /ig https://www.instagram.com/p/ABC123xyz/\n"
            "• /instagram https://www.instagram.com/reel/ABC123xyz/\n"
            "• /ig https://www.instagram.com/tv/ABC123xyz/\n\n"
            "💡 Just send the Instagram post/reel URL and I'll download it for you!"
        )
        return
    
    url = ' '.join(context.args)
    
    # Extract Instagram URL from message
    if not url.startswith('http'):
        url_pattern = r'(https?://(?:www\.)?instagram\.com/[^\s]+)'
        match = re.search(url_pattern, url)
        if match:
            url = match.group(1)
        else:
            await update.message.reply_text(
                "❌ Please provide a valid Instagram URL!\n\n"
                "Example: /ig https://www.instagram.com/p/ABC123xyz/"
            )
            return
    
    processing_msg = await update.message.reply_text("📷 Downloading Instagram media...\n⏳ Please wait...")
    
    try:
        loop = asyncio.get_event_loop()
        
        def download_instagram_media(media_url):
            import tempfile
            import os as os_module
            tmp_path = None
            
            # Initialize max_file_size_mb early
            max_file_size_mb = 30  # Default: 30MB for reliable uploads
            
            try:
                logger.info(f"Attempting to download Instagram media: {media_url}")
                
                # Use yt-dlp for reliable downloading (supports Instagram)
                media_buffer = io.BytesIO()
                
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes', 0)
                        speed = d.get('speed', 0)
                        if total:
                            pct = downloaded / total * 100
                            downloaded_mb = downloaded / (1024 * 1024)
                            total_mb = total / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0
                            logger.info(f"Downloading... {pct:.2f}% ({downloaded_mb:.2f}/{total_mb:.2f} MB) at {speed_mb:.2f} MB/s")
                        else:
                            downloaded_mb = downloaded / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0
                            logger.info(f"Downloading... {downloaded_mb:.2f} MB at {speed_mb:.2f} MB/s")
                    elif d['status'] == 'finished':
                        logger.info("Download completed, processing file...")
                
                # Get media info first
                info_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'socket_timeout': 30,
                }
                
                title = None
                duration_str = ''
                is_video = False
                
                try:
                    with YoutubeDL(info_opts) as ydl:
                        info = ydl.extract_info(media_url, download=False)
                        title = info.get('title', '')[:200] if info.get('title') else None
                        duration = info.get('duration', 0)
                        if duration:
                            duration_str = f"{duration // 60}:{duration % 60:02d}"
                        
                        # Check if it's a video
                        ext = info.get('ext', '')
                        if ext in ['mp4', 'webm', 'mkv'] or info.get('vcodec') != 'none':
                                        is_video = True
                                    
                        logger.info(f"Instagram media info retrieved: {title}, duration: {duration_str}, is_video: {is_video}")
                except Exception as info_error:
                    logger.warning(f"Could not get media info: {info_error}, will try to download anyway")
                
                # Create temporary file for download
                temp_dir = tempfile.gettempdir()
                base_name = f"ig_download_{os_module.getpid()}"
                tmp_path_pattern = os_module.path.join(temp_dir, base_name + ".%(ext)s")
                
                logger.info(f"Downloading to temp file pattern: {tmp_path_pattern}")
                
                # Download options - use best quality but limit file size
                ydl_opts = {
                    'format': 'best[ext=mp4]/best[ext=webm]/best',
                    'outtmpl': tmp_path_pattern,
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [progress_hook],
                    'noplaylist': True,
                    'max_filesize': max_file_size_mb * 1024 * 1024,
                    'socket_timeout': 30,
                    'retries': 3,
                    'fragment_retries': 3,
                }
                
                # Download media
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([media_url])
                
                # Find the actual downloaded file
                actual_file = None
                possible_extensions = ['.mp4', '.webm', '.mkv', '.jpg', '.jpeg', '.png']
                for ext in possible_extensions:
                    test_path = os_module.path.join(temp_dir, base_name + ext)
                    if os_module.path.exists(test_path):
                        actual_file = test_path
                        tmp_path = test_path
                        logger.info(f"Found downloaded file: {actual_file}")
                        # Check if it's a video based on extension
                        if ext in ['.mp4', '.webm', '.mkv']:
                            is_video = True
                        break
                
                if not actual_file:
                    import glob
                    pattern = os_module.path.join(temp_dir, base_name + ".*")
                    matches = glob.glob(pattern)
                    if matches:
                        actual_file = matches[0]
                        tmp_path = actual_file
                        ext = os_module.path.splitext(actual_file)[1].lower()
                        if ext in ['.mp4', '.webm', '.mkv']:
                            is_video = True
                        logger.info(f"Found downloaded file via glob: {actual_file}")
                    else:
                        raise Exception(f"Downloaded file not found. Searched for pattern: {base_name}.* in {temp_dir}")
                
                # Read the file into buffer and check size
                file_size = os_module.path.getsize(actual_file)
                max_size = max_file_size_mb * 1024 * 1024
                file_size_mb = file_size / (1024 * 1024)
                logger.info(f"Downloaded file size: {file_size_mb:.2f} MB ({file_size} bytes), limit: {max_file_size_mb}MB")
                
                if file_size > max_size:
                    raise Exception(f"Media file too large ({file_size_mb:.2f} MB). Limit is {max_file_size_mb}MB. Please try a shorter video.")
                
                with open(actual_file, 'rb') as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        media_buffer.write(chunk)
                
                media_buffer.seek(0)
                
                logger.info(f"Successfully downloaded Instagram media ({file_size} bytes, is_video: {is_video})")
                return {
                    'media': media_buffer,
                    'is_video': is_video,
                    'title': title,
                    'duration': duration_str
                }
            
            except Exception as e:
                logger.error(f"Instagram download error: {e}", exc_info=True)
                error_msg = str(e)
                if "Media file too large" in error_msg:
                    raise Exception("Media file too large (>30MB). Please try a shorter video.")
                elif "empty media response" in error_msg.lower() or "authentication" in error_msg.lower() or "cookies" in error_msg.lower():
                    raise Exception("INSTAGRAM_AUTH_REQUIRED: Instagram requires authentication. This post may be private or require login.")
                elif "unavailable" in error_msg.lower() or "private" in error_msg.lower() or "access" in error_msg.lower() or "restricted" in error_msg.lower():
                    raise Exception("Could not download media. The post might be private, unavailable, or restricted.")
                else:
                    raise Exception(f"Could not download media: {error_msg}")
            finally:
                # Clean up temp file
                if tmp_path and os_module.path.exists(tmp_path):
                    try:
                        os_module.unlink(tmp_path)
                        logger.info(f"Cleaned up temp file: {tmp_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Could not delete temp file: {cleanup_error}")
        
        # Download media with timeout (600 seconds for larger files)
        result = await asyncio.wait_for(
            loop.run_in_executor(None, download_instagram_media, url),
            timeout=600.0
        )
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Prepare caption
        caption = "📷 **Instagram Media Downloaded**"
        if result.get('title'):
            caption += f"\n📝 {result['title']}"
        if result.get('duration'):
            caption += f"\n⏱ Duration: {result['duration']}"
        
        # Send media
        media_buffer = result['media']
        media_buffer.seek(0, 2)
        file_size = media_buffer.tell()
        media_buffer.seek(0)
        
        # Check file size (Telegram limit is ~50MB)
        max_allowed_mb = 30
        if file_size > max_allowed_mb * 1024 * 1024:
            await update.message.reply_text(
                f"❌ Media is too large ({file_size / (1024*1024):.2f}MB). Limit is {max_allowed_mb}MB.\n\n"
                "**To ensure successful uploads:**\n"
                "• Try a shorter video (under 2-3 minutes)\n"
                "• Smaller files upload much faster and more reliably\n\n"
                "💡 **Tip:** Videos under 20MB work best for reliable uploads!"
            )
            return
        
        # Send video or photo with retry logic
        from telegram.error import TimedOut, NetworkError
        max_retries = 3
        retry_count = 0
        sent = False
        
        while not sent and retry_count < max_retries:
            try:
                media_buffer.seek(0)
                
                if result.get('is_video'):
                    await update.message.reply_video(
                        video=media_buffer,
                        caption=caption,
                        parse_mode='Markdown',
                        supports_streaming=True
                    )
                else:
                    await update.message.reply_photo(
                        photo=media_buffer,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                sent = True
                logger.info(f"Instagram media sent successfully to Telegram ({file_size / (1024*1024):.2f} MB)")
            except (TimedOut, NetworkError) as tg_error:
                retry_count += 1
                logger.warning(f"Telegram API timeout/error (attempt {retry_count}/{max_retries}): {tg_error}")
                if retry_count < max_retries:
                    wait_time = retry_count * 2
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Failed to upload Instagram media to Telegram after {max_retries} attempts")
                    await update.message.reply_text(
                        "❌ **Upload Failed:** Could not upload media to Telegram after multiple attempts.\n\n"
                        "**What you can try:**\n"
                        "• Try a much shorter video (under 2-3 minutes)\n"
                        "• Check your internet upload speed\n"
                        "• Try again when you have a faster connection\n\n"
                        "💡 **Tip:** Videos under 20MB upload much faster and more reliably."
                    )
                    return
            except Exception as send_error:
                logger.error(f"Error sending Instagram media to Telegram: {send_error}")
                raise
        
        logger.info(f"Instagram media downloaded successfully: {url}")
    
    except asyncio.TimeoutError:
        try:
            await processing_msg.delete()
        except:
            pass
        await update.message.reply_text(
            "❌ **Timeout Error:** Download took too long (10 minutes limit).\n\n"
            "**Possible reasons:**\n"
            "• Your internet connection is slow\n"
            "• The media is very large or long\n"
            "• Instagram servers are slow or busy\n\n"
            "**What you can try:**\n"
            "• Check your internet connection\n"
            "• Try a shorter video (under 5-10 minutes)\n"
            "• Try again later when network conditions are better\n\n"
            "💡 **Tip:** Shorter videos download faster and are more likely to stay under the 30MB limit."
        )
    except Exception as e:
        logger.error(f"Instagram download command error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e)
        detailed_msg = ""
        
        if "INSTAGRAM_AUTH_REQUIRED" in error_msg:
            detailed_msg = (
                "❌ **Instagram Authentication Required**\n\n"
                "**This Instagram post requires login to access.**\n\n"
                "**Possible reasons:**\n"
                "• The post is private or from a private account\n"
                "• Instagram requires authentication for this content\n"
                "• The post might be restricted or age-restricted\n\n"
                "**What you can try:**\n"
                "• Make sure the post is from a public account\n"
                "• Try downloading a different public post\n"
                "• Check if the post is accessible without login in your browser\n"
                "• Only public posts can be downloaded without authentication\n\n"
                "**Note:** Instagram frequently requires authentication for downloads.\n"
                "Private posts and posts from private accounts cannot be downloaded."
            )
        elif "Could not download" in error_msg or "unavailable" in error_msg.lower():
            detailed_msg = (
                "❌ **Could not download Instagram media.**\n\n"
                "**Possible reasons:**\n"
                "• The post is private or restricted\n"
                "• Instagram has blocked the download\n"
                "• The URL format is not supported\n"
                "• Download services are temporarily unavailable\n\n"
                "**What you can try:**\n"
                "• Make sure the post is public and accessible\n"
                "• Try copying the URL directly from Instagram\n"
                "• Use format: `https://www.instagram.com/p/ABC123xyz/`\n"
                "• Or: `https://www.instagram.com/reel/ABC123xyz/`\n"
                "• Wait a few minutes and try again\n\n"
                "**Note:** Instagram frequently changes their API, which can affect downloads.\n"
                "If this continues, the post may not be downloadable."
            )
        elif "timeout" in error_msg.lower():
            detailed_msg = "Download timed out. The media might be very large. Please try again."
        elif "private" in error_msg.lower() or "restricted" in error_msg.lower():
            detailed_msg = "This post is private or unavailable. Only public posts can be downloaded."
        elif "too large" in error_msg.lower():
            detailed_msg = "Media is too large (>30MB). Please try a shorter video."
        else:
            detailed_msg = f"Error: {error_msg}\n\nPlease try again or use a different Instagram URL."
        
        await update.message.reply_text(detailed_msg)

# Old Instagram download function removed - now using yt-dlp based implementation above

async def clone_website_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clone a website by downloading HTML, CSS, JS, and images."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        help_text = (
            "🌐 **Website Cloning Tool**\n\n"
            "**Usage:** `/clone <URL>`\n\n"
            "**Example:**\n"
            "• `/clone https://example.com`\n"
            "• `/clone https://www.google.com`\n\n"
            "**Features:**\n"
            "• Downloads complete website HTML\n"
            "• Extracts and combines all CSS into one file\n"
            "• Extracts and combines all JavaScript into one file\n"
            "• Sends 3 separate files: HTML, CSS, JS\n"
            "• Works with most static websites\n\n"
            "**Note:**\n"
            "• Some websites may block automated downloads\n"
            "• Dynamic/JavaScript-heavy sites may not clone perfectly\n"
            "• Large websites may take time to process"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    url = ' '.join(context.args)
    
    # Validate URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Validate URL format
    import re
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    if not url_pattern.match(url):
        await update.message.reply_text(
            "❌ **Invalid URL format**\n\n"
            "Please provide a valid URL.\n"
            "Example: `https://example.com`"
        )
        return
    
    processing_msg = await update.message.reply_text(
        f"🌐 Cloning website...\n"
        f"📥 URL: `{url}`\n"
        f"⏳ This may take a moment...",
        parse_mode='Markdown'
    )
    
    try:
        loop = asyncio.get_event_loop()
        
        def clone_website(website_url):
            """Clone website and extract HTML, CSS, JS as separate files."""
            from urllib.parse import urljoin, urlparse
            import os
            
            temp_dir = None
            
            try:
                # Create temporary directory
                temp_dir = tempfile.mkdtemp()
                
                # Headers to mimic a browser
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                # Download main HTML page
                logger.info(f"Downloading main page: {website_url}")
                try:
                    response = requests.get(website_url, headers=headers, timeout=30, allow_redirects=True)
                    response.raise_for_status()
                    html_content = response.text
                    final_url = response.url  # Get final URL after redirects
                except Exception as e:
                    raise Exception(f"Failed to download website: {str(e)}")
                
                # Parse URL to get domain
                parsed_url = urlparse(final_url)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
                domain_name = parsed_url.netloc.replace('www.', '').split('.')[0] or 'website'
                
                # Extract and download resources using regex
                import re as re_module
                
                # Find CSS files
                css_pattern = r'href=["\']([^"\']*\.css[^"\']*)["\']'
                css_urls = re_module.findall(css_pattern, html_content, re_module.IGNORECASE)
                
                # Find inline CSS in <style> tags
                inline_css_pattern = r'<style[^>]*>(.*?)</style>'
                inline_css = re_module.findall(inline_css_pattern, html_content, re_module.IGNORECASE | re_module.DOTALL)
                
                # Find JS files
                js_pattern = r'src=["\']([^"\']*\.js[^"\']*)["\']'
                js_urls = re_module.findall(js_pattern, html_content, re_module.IGNORECASE)
                
                # Find inline JS in <script> tags
                inline_js_pattern = r'<script[^>]*>(.*?)</script>'
                inline_js = re_module.findall(inline_js_pattern, html_content, re_module.IGNORECASE | re_module.DOTALL)
                
                # Combine all CSS
                combined_css = []
                css_count = 0
                
                # Add inline CSS first
                for css in inline_css:
                    combined_css.append(f"/* Inline CSS */\n{css}\n")
                    css_count += 1
                
                # Download external CSS files
                for css_url in css_urls:
                    try:
                        if css_url.startswith('//'):
                            css_url = 'https:' + css_url
                        elif css_url.startswith('/'):
                            css_url = base_url + css_url
                        elif not css_url.startswith('http'):
                            css_url = urljoin(final_url, css_url)
                        
                        parsed_css = urlparse(css_url)
                        if parsed_css.netloc != parsed_url.netloc:
                            continue  # Skip external CSS
                        
                        css_response = requests.get(css_url, headers=headers, timeout=10, allow_redirects=True)
                        if css_response.status_code == 200:
                            combined_css.append(f"/* CSS from {css_url} */\n{css_response.text}\n")
                            css_count += 1
                            logger.info(f"Downloaded CSS: {css_url}")
                    except Exception as e:
                        logger.warning(f"Failed to download CSS {css_url}: {e}")
                        continue
                
                # Combine all JS
                combined_js = []
                js_count = 0
                
                # Add inline JS first
                for js in inline_js:
                    combined_js.append(f"// Inline JavaScript\n{js}\n")
                    js_count += 1
                
                # Download external JS files
                for js_url in js_urls:
                    try:
                        if js_url.startswith('//'):
                            js_url = 'https:' + js_url
                        elif js_url.startswith('/'):
                            js_url = base_url + js_url
                        elif not js_url.startswith('http'):
                            js_url = urljoin(final_url, js_url)
                        
                        parsed_js = urlparse(js_url)
                        if parsed_js.netloc != parsed_url.netloc:
                            continue  # Skip external JS
                        
                        js_response = requests.get(js_url, headers=headers, timeout=10, allow_redirects=True)
                        if js_response.status_code == 200:
                            combined_js.append(f"// JavaScript from {js_url}\n{js_response.text}\n")
                            js_count += 1
                            logger.info(f"Downloaded JS: {js_url}")
                    except Exception as e:
                        logger.warning(f"Failed to download JS {js_url}: {e}")
                        continue
                
                # Create clean HTML (remove external CSS/JS links and inline styles/scripts)
                clean_html = html_content
                
                # Remove external CSS links
                clean_html = re_module.sub(r'<link[^>]*href=["\'][^"\']*\.css[^"\']*["\'][^>]*>', '', clean_html, flags=re_module.IGNORECASE)
                
                # Remove external JS script tags
                clean_html = re_module.sub(r'<script[^>]*src=["\'][^"\']*\.js[^"\']*["\'][^>]*></script>', '', clean_html, flags=re_module.IGNORECASE)
                
                # Remove inline style tags
                clean_html = re_module.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re_module.IGNORECASE | re_module.DOTALL)
                
                # Remove inline script tags
                clean_html = re_module.sub(r'<script[^>]*>.*?</script>', '', clean_html, flags=re_module.IGNORECASE | re_module.DOTALL)
                
                # Add links to external CSS and JS files
                css_link = '<link rel="stylesheet" href="style.css">'
                js_link = '<script src="script.js"></script>'
                
                # Insert CSS link in <head> or at the beginning
                if '<head>' in clean_html:
                    clean_html = clean_html.replace('<head>', f'<head>\n{css_link}')
                elif '</head>' in clean_html:
                    clean_html = clean_html.replace('</head>', f'{css_link}\n</head>')
                else:
                    clean_html = f'{css_link}\n{clean_html}'
                
                # Insert JS link before </body> or at the end
                if '</body>' in clean_html:
                    clean_html = clean_html.replace('</body>', f'{js_link}\n</body>')
                else:
                    clean_html = f'{clean_html}\n{js_link}'
                
                # Prepare file contents
                html_content_final = clean_html.encode('utf-8')
                css_content_final = '\n'.join(combined_css).encode('utf-8') if combined_css else b'/* No CSS found */'
                js_content_final = '\n'.join(combined_js).encode('utf-8') if combined_js else b'// No JavaScript found'
                
                logger.info(f"Website cloned successfully: HTML={len(html_content_final)} bytes, CSS={len(css_content_final)} bytes, JS={len(js_content_final)} bytes")
                
                return {
                    'html': html_content_final,
                    'css': css_content_final,
                    'js': js_content_final,
                    'html_size': len(html_content_final),
                    'css_size': len(css_content_final),
                    'js_size': len(js_content_final),
                    'css_count': css_count,
                    'js_count': js_count,
                    'domain': domain_name
                }
                
            except Exception as e:
                logger.error(f"Website cloning error: {e}", exc_info=True)
                raise
            finally:
                # Cleanup
                try:
                    if temp_dir and os.path.exists(temp_dir):
                        import shutil
                        shutil.rmtree(temp_dir)
                except Exception as cleanup_error:
                    logger.warning(f"Error cleaning up temp directory: {cleanup_error}")
        
        # Run cloning in executor
        result = await loop.run_in_executor(None, clone_website, url)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Check file sizes (Telegram limit is ~50MB per file)
        max_size = 50 * 1024 * 1024
        if result['html_size'] > max_size or result['css_size'] > max_size or result['js_size'] > max_size:
            await update.message.reply_text(
                f"❌ **File too large**\n\n"
                f"One or more files exceed Telegram's 50MB limit.\n\n"
                f"**File sizes:**\n"
                f"• HTML: {result['html_size'] / (1024*1024):.1f} MB\n"
                f"• CSS: {result['css_size'] / (1024*1024):.1f} MB\n"
                f"• JS: {result['js_size'] / (1024*1024):.1f} MB\n\n"
                f"Try cloning a smaller website or a specific page."
            )
            return
        
        # Send HTML file
        html_buffer = io.BytesIO(result['html'])
        html_buffer.name = f"{result['domain']}.html"
        
        html_msg = await update.message.reply_document(
            document=html_buffer,
            filename=html_buffer.name,
            caption=(
                f"✅ **Website Cloned Successfully!**\n\n"
                f"🌐 **URL:** `{url}`\n\n"
                f"📄 **HTML File** ({result['html_size'] / 1024:.1f} KB)\n"
                f"📊 **CSS Files:** {result['css_count']} found\n"
                f"📊 **JS Files:** {result['js_count']} found\n\n"
                f"📎 Sending CSS and JS files..."
            ),
            parse_mode='Markdown'
        )
        
        # Send CSS file
        css_buffer = io.BytesIO(result['css'])
        css_buffer.name = "style.css"
        
        await update.message.reply_document(
            document=css_buffer,
            filename=css_buffer.name,
            caption=f"📄 **CSS File** ({result['css_size'] / 1024:.1f} KB)",
            parse_mode='Markdown'
        )
        
        # Send JS file
        js_buffer = io.BytesIO(result['js'])
        js_buffer.name = "script.js"
        
        await update.message.reply_document(
            document=js_buffer,
            filename=js_buffer.name,
            caption=(
                f"📄 **JavaScript File** ({result['js_size'] / 1024:.1f} KB)\n\n"
                f"💡 **Tip:** Save all 3 files in the same folder and open the HTML file to view the website."
            ),
            parse_mode='Markdown'
        )
        
        logger.info(f"Website cloned and sent successfully: {url}")
        
    except Exception as e:
        logger.error(f"Website cloning error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "timeout" in error_msg:
            detailed_msg = (
                "❌ **Download Timeout**\n\n"
                "The website took too long to respond.\n\n"
                "**Possible reasons:**\n"
                "• Website is slow or unavailable\n"
                "• Network connection issues\n"
                "• Website blocks automated requests\n\n"
                "**What you can try:**\n"
                "• Check if the website is accessible in your browser\n"
                "• Try again in a few moments\n"
                "• Use a different URL"
            )
        elif "404" in error_msg or "not found" in error_msg:
            detailed_msg = (
                "❌ **Website Not Found**\n\n"
                "The URL you provided returned a 404 error.\n\n"
                "**What you can try:**\n"
                "• Check if the URL is correct\n"
                "• Make sure the website is accessible\n"
                "• Try copying the URL from your browser"
            )
        elif "ssl" in error_msg or "certificate" in error_msg:
            detailed_msg = (
                "❌ **SSL Certificate Error**\n\n"
                "There was an issue with the website's security certificate.\n\n"
                "**What you can try:**\n"
                "• Make sure the URL uses HTTPS correctly\n"
                "• Try the HTTP version if available\n"
                "• The website may have certificate issues"
            )
        elif "connection" in error_msg or "refused" in error_msg:
            detailed_msg = (
                "❌ **Connection Error**\n\n"
                "Could not connect to the website.\n\n"
                "**Possible reasons:**\n"
                "• Website is down or unreachable\n"
                "• Network connection issues\n"
                "• Website blocks automated access\n\n"
                "**What you can try:**\n"
                "• Check your internet connection\n"
                "• Verify the website is accessible in your browser\n"
                "• Try again later"
            )
        else:
            detailed_msg = (
                f"❌ **Error Cloning Website**\n\n"
                f"Error: {str(e)}\n\n"
                "**Possible reasons:**\n"
                "• Website blocks automated downloads\n"
                "• Website requires authentication\n"
                "• Website uses complex JavaScript\n"
                "• Network or server issues\n\n"
                "**What you can try:**\n"
                "• Make sure the website is publicly accessible\n"
                "• Try a different URL\n"
                "• Check if the website works in your browser"
            )
        
        await update.message.reply_text(detailed_msg)

async def build_website_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Build a ready-made website from user prompt using AI."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        help_text = (
            "🌐 **Build My Website** - AI Website Generator\n\n"
            "**Usage:** `/build <your website description>`\n\n"
            "**Examples:**\n"
            "• `/build a portfolio website for a photographer`\n"
            "• `/build a restaurant menu website`\n"
            "• `/build a landing page for a tech startup`\n"
            "• `/build a personal blog website`\n"
            "• `/build a business card website`\n\n"
            "**Features:**\n"
            "• Generates complete HTML, CSS, and JS files\n"
            "• Modern, responsive design\n"
            "• Ready to use immediately\n"
            "• Uses free AI API (no API key needed)\n\n"
            "💡 **Tip:** Be specific about what you want!\n"
            "Example: `/build a portfolio site with dark theme, gallery, and contact form`"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    prompt = ' '.join(context.args)
    
    if len(prompt) > 500:
        await update.message.reply_text(
            "❌ Prompt is too long! Please keep it under 500 characters.\n\n"
            "💡 Try to be concise but descriptive."
        )
        return
    
    processing_msg = await update.message.reply_text(
        f"🌐 Building your website...\n"
        f"📝 Description: `{prompt[:100]}{'...' if len(prompt) > 100 else ''}`\n"
        f"⏳ This may take 10-20 seconds...",
        parse_mode='Markdown'
    )
    
    try:
        loop = asyncio.get_event_loop()
        
        def generate_website(website_prompt):
            """Generate HTML, CSS, JS from prompt using AI."""
            try:
                # Use Hugging Face Inference API (free tier) for code generation
                # Fallback to template-based generation if API fails
                
                # Try Hugging Face API first (free, no key needed for some models)
                try:
                    import json
                    
                    # Use a free code generation model
                    api_url = "https://api-inference.huggingface.co/models/bigcode/starcoder"
                    
                    # Create a prompt for website generation
                    code_prompt = f"""Generate a complete, modern website with HTML, CSS, and JavaScript based on this description: {website_prompt}

Requirements:
1. Create a single HTML file with embedded CSS and JavaScript
2. Modern, responsive design
3. Clean and professional
4. Include proper structure (header, main content, footer)
5. Make it visually appealing

Generate the HTML code:"""
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0'
                    }
                    
                    payload = {
                        "inputs": code_prompt,
                        "parameters": {
                            "max_new_tokens": 2000,
                            "temperature": 0.7,
                            "return_full_text": False
                        }
                    }
                    
                    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if isinstance(result, list) and len(result) > 0:
                            generated_code = result[0].get('generated_text', '')
                            if generated_code and len(generated_code) > 100:
                                # Extract HTML from generated code
                                html_content = generated_code
                                
                                # Try to extract HTML, CSS, JS
                                html_match = re.search(r'<html[^>]*>.*?</html>', html_content, re.DOTALL | re.IGNORECASE)
                                if html_match:
                                    full_html = html_match.group(0)
                                    
                                    # Extract CSS
                                    css_match = re.search(r'<style[^>]*>(.*?)</style>', full_html, re.DOTALL | re.IGNORECASE)
                                    css_content = css_match.group(1) if css_match else ""
                                    
                                    # Extract JS
                                    js_match = re.search(r'<script[^>]*>(.*?)</script>', full_html, re.DOTALL | re.IGNORECASE)
                                    js_content = js_match.group(1) if js_match else ""
                                    
                                    # Clean HTML (remove style and script tags)
                                    clean_html = re.sub(r'<style[^>]*>.*?</style>', '', full_html, flags=re.DOTALL | re.IGNORECASE)
                                    clean_html = re.sub(r'<script[^>]*>.*?</script>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
                                    
                                    # Add links to external files
                                    if '<head>' in clean_html:
                                        clean_html = clean_html.replace('<head>', f'<head>\n<link rel="stylesheet" href="style.css">')
                                    else:
                                        clean_html = f'<link rel="stylesheet" href="style.css">\n{clean_html}'
                                    
                                    if '</body>' in clean_html:
                                        clean_html = clean_html.replace('</body>', f'<script src="script.js"></script>\n</body>')
                                    else:
                                        clean_html = f'{clean_html}\n<script src="script.js"></script>'
                                    
                                    return {
                                        'html': clean_html.encode('utf-8'),
                                        'css': css_content.encode('utf-8') if css_content else b'/* Generated CSS */\nbody { margin: 0; padding: 20px; font-family: Arial, sans-serif; }',
                                        'js': js_content.encode('utf-8') if js_content else b'// Generated JavaScript\nconsole.log("Website loaded!");',
                                        'method': 'ai'
                                    }
                except Exception as api_error:
                    logger.warning(f"Hugging Face API failed, using template method: {api_error}")
                
                # Fallback: Template-based generation with smart parsing
                return generate_website_from_template(website_prompt)
                
            except Exception as e:
                logger.error(f"Website generation error: {e}", exc_info=True)
                # Fallback to template
                return generate_website_from_template(website_prompt)
        
        def generate_website_from_template(prompt):
            """Generate website from templates based on prompt keywords - dynamic content generation."""
            import random
            prompt_lower = prompt.lower()
            
            # Extract key words from prompt for dynamic content
            words = prompt.split()
            key_words = [w for w in words if len(w) > 3][:5]  # Get meaningful words
            site_name = ' '.join(words[:3]).title() if len(words) >= 3 else "My Website"
            
            # Determine website type and theme with more variations
            website_type = "general"
            theme = "light"
            colors = {"primary": "#3498db", "secondary": "#2ecc71", "text": "#333", "bg": "#ffffff"}
            
            # Color palettes for different types
            color_palettes = {
                "portfolio": [("#e74c3c", "#c0392b"), ("#16a085", "#27ae60"), ("#8e44ad", "#9b59b6")],
                "restaurant": [("#d35400", "#e67e22"), ("#c0392b", "#e74c3c"), ("#f39c12", "#e67e22")],
                "blog": [("#9b59b6", "#8e44ad"), ("#3498db", "#2980b9"), ("#e74c3c", "#c0392b")],
                "business": [("#34495e", "#2c3e50"), ("#7f8c8d", "#95a5a6"), ("#2c3e50", "#34495e")],
                "landing": [("#3498db", "#2980b9"), ("#1abc9c", "#16a085"), ("#9b59b6", "#8e44ad")],
                "general": [("#3498db", "#2ecc71"), ("#e74c3c", "#c0392b"), ("#9b59b6", "#8e44ad")]
            }
            
            # Detect website type with more keywords
            type_keywords = {
                "portfolio": ["portfolio", "photographer", "designer", "artist", "creative", "gallery", "showcase"],
                "restaurant": ["restaurant", "menu", "food", "cafe", "dining", "cuisine", "chef", "kitchen"],
                "blog": ["blog", "blogger", "writer", "article", "post", "journal", "diary"],
                "business": ["business", "corporate", "company", "enterprise", "professional", "corporate"],
                "landing": ["landing", "startup", "tech", "saas", "product", "app", "software"]
            }
            
            for site_type, keywords in type_keywords.items():
                if any(word in prompt_lower for word in keywords):
                    website_type = site_type
                    palette = random.choice(color_palettes[site_type])
                    colors = {"primary": palette[0], "secondary": palette[1], "text": "#2c3e50", "bg": "#ffffff"}
                    break
            
            # If no specific type found, use hash of prompt to select colors
            if website_type == "general":
                prompt_hash = hash(prompt) % len(color_palettes["general"])
                palette = color_palettes["general"][prompt_hash]
                colors = {"primary": palette[0], "secondary": palette[1], "text": "#2c3e50", "bg": "#ffffff"}
            
            # Detect theme
            if any(word in prompt_lower for word in ["dark", "black", "night", "dark mode"]):
                theme = "dark"
                colors["text"] = "#ecf0f1"
                colors["bg"] = "#2c3e50"
            elif any(word in prompt_lower for word in ["light", "white", "bright"]):
                theme = "light"
            
            # Generate dynamic content based on prompt
            def generate_sections():
                """Generate sections based on prompt keywords."""
                sections = []
                
                # Hero section content
                hero_title_options = [
                    f"Welcome to {site_name}",
                    f"Discover {site_name}",
                    f"Experience {site_name}",
                    f"{site_name} - Your Vision",
                    f"Transform with {site_name}"
                ]
                hero_title = random.choice(hero_title_options)
                
                # About section
                about_content = f"Based on your vision: {prompt}. We're here to bring your ideas to life with innovative solutions and creative excellence."
                
                # Services/Features - generate based on prompt words
                services = []
                if "portfolio" in website_type:
                    services = ["Creative Design", "Visual Art", "Project Showcase", "Portfolio Display"]
                elif "restaurant" in website_type:
                    services = ["Fine Dining", "Catering Services", "Private Events", "Menu Selection"]
                elif "blog" in website_type:
                    services = ["Latest Articles", "Featured Posts", "Categories", "Newsletter"]
                elif "business" in website_type:
                    services = ["Consulting", "Solutions", "Services", "Support"]
                else:
                    # Generate from prompt words
                    if len(key_words) >= 3:
                        services = [f"{key_words[0].title()} Solutions", f"{key_words[1].title()} Services", 
                                   f"{key_words[2].title()} Expertise", "Professional Support"]
                    else:
                        services = ["Premium Service", "Expert Solutions", "Quality Work", "Professional Support"]
                
                return hero_title, about_content, services
            
            hero_title, about_content, services = generate_sections()
            
            # Generate dynamic navigation based on website type
            nav_items = ["Home", "About", "Services", "Contact"]
            if website_type == "blog":
                nav_items = ["Home", "Blog", "Categories", "About", "Contact"]
            elif website_type == "restaurant":
                nav_items = ["Home", "Menu", "About", "Gallery", "Contact"]
            elif website_type == "portfolio":
                nav_items = ["Home", "Portfolio", "About", "Services", "Contact"]
            
            nav_html = "\n                ".join([f'<li><a href="#{item.lower()}">{item}</a></li>' for item in nav_items])
            
            # Generate service cards dynamically
            service_cards_html = ""
            for i, service in enumerate(services[:4], 1):  # Limit to 4 services
                descriptions = [
                    f"Explore our {service.lower()} offerings designed to meet your needs.",
                    f"Professional {service.lower()} solutions tailored for you.",
                    f"Experience excellence in {service.lower()} with our expert team.",
                    f"Quality {service.lower()} services that exceed expectations."
                ]
                desc = random.choice(descriptions) if i <= len(descriptions) else f"Premium {service.lower()} service."
                service_cards_html += f'''
                <div class="service-card">
                    <h3>{service}</h3>
                    <p>{desc}</p>
                </div>'''
            
            # Generate HTML with dynamic content
            html_template = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{site_name} - {prompt[:40]}...</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header>
        <nav>
            <div class="logo">{site_name}</div>
            <ul class="nav-links">
                {nav_html}
            </ul>
        </nav>
    </header>
    
    <main>
        <section id="home" class="hero">
            <div class="hero-content">
                <h1>{hero_title}</h1>
                <p>{prompt}</p>
                <div class="hero-buttons">
                    <a href="#contact" class="btn btn-primary">Get Started</a>
                    <a href="#about" class="btn btn-secondary">Learn More</a>
                </div>
            </div>
        </section>
        
        <section id="about" class="about">
            <div class="container">
                <h2>About {site_name}</h2>
                <p>{about_content}</p>
                <div class="features">
                    <div class="feature-item">
                        <h3>✨ Quality</h3>
                        <p>We deliver exceptional quality in everything we do</p>
                    </div>
                    <div class="feature-item">
                        <h3>🚀 Innovation</h3>
                        <p>Cutting-edge solutions for modern challenges</p>
                    </div>
                    <div class="feature-item">
                        <h3>💼 Experience</h3>
                        <p>Years of expertise in our field</p>
                    </div>
                </div>
            </div>
        </section>
        
        <section id="services" class="services">
            <div class="container">
                <h2>Our {random.choice(["Services", "Offerings", "Solutions", "Features"])}</h2>
                <div class="service-grid">
                    {service_cards_html}
                </div>
            </div>
        </section>
        
        <section id="contact" class="contact">
            <div class="container">
                <h2>Get In Touch</h2>
                <p>We'd love to hear from you. Send us a message and we'll respond as soon as possible.</p>
                <form id="contactForm">
                    <input type="text" placeholder="Your Name" required>
                    <input type="email" placeholder="Your Email" required>
                    <input type="text" placeholder="Subject" required>
                    <textarea placeholder="Your Message" rows="5" required></textarea>
                    <button type="submit" class="btn btn-primary">Send Message</button>
                </form>
            </div>
        </section>
    </main>
    
    <footer>
        <div class="container">
            <p>&copy; 2024 {site_name}. All rights reserved.</p>
            <p>Website generated from: "{prompt[:60]}{'...' if len(prompt) > 60 else ''}"</p>
        </div>
    </footer>
    
    <script src="script.js"></script>
</body>
</html>'''
            
            # Generate CSS
            css_template = f'''/* Generated CSS for {prompt[:50]} */
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
    color: {colors["text"]};
    background-color: {colors["bg"]};
}}

header {{
    background: linear-gradient(135deg, {colors["primary"]}, {colors["secondary"]});
    color: white;
    padding: 1rem 0;
    position: sticky;
    top: 0;
    z-index: 1000;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}}

nav {{
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 2rem;
}}

.logo {{
    font-size: 1.5rem;
    font-weight: bold;
}}

.nav-links {{
    display: flex;
    list-style: none;
    gap: 2rem;
}}

.nav-links a {{
    color: white;
    text-decoration: none;
    transition: opacity 0.3s;
}}

.nav-links a:hover {{
    opacity: 0.8;
}}

main {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 2rem;
}}

.hero {{
    text-align: center;
    padding: 4rem 2rem;
    background: linear-gradient(135deg, {colors["primary"]}22, {colors["secondary"]}22);
    border-radius: 10px;
    margin-bottom: 3rem;
}}

.hero h1 {{
    font-size: 3rem;
    margin-bottom: 1rem;
    color: {colors["primary"]};
}}

.hero p {{
    font-size: 1.2rem;
    margin-bottom: 2rem;
    color: {colors["text"]};
    max-width: 700px;
    margin-left: auto;
    margin-right: auto;
}}

.hero-buttons {{
    display: flex;
    gap: 1rem;
    justify-content: center;
    flex-wrap: wrap;
}}

.btn {{
    display: inline-block;
    padding: 1rem 2rem;
    background: {colors["primary"]};
    color: white;
    text-decoration: none;
    border-radius: 5px;
    transition: transform 0.3s, box-shadow 0.3s;
    border: none;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 600;
}}

.btn:hover {{
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.2);
}}

.btn-primary {{
    background: {colors["primary"]};
}}

.btn-secondary {{
    background: {colors["secondary"]};
}}

.container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 2rem;
}}

section {{
    margin-bottom: 4rem;
    padding: 2rem 0;
}}

h2 {{
    font-size: 2.5rem;
    margin-bottom: 2rem;
    color: {colors["primary"]};
    text-align: center;
}}

.service-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
    margin-top: 2rem;
}}

.service-card {{
    background: white;
    padding: 2rem;
    border-radius: 10px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    transition: transform 0.3s;
}}

.service-card:hover {{
    transform: translateY(-5px);
}}

.service-card h3 {{
    color: {colors["primary"]};
    margin-bottom: 1rem;
    font-size: 1.5rem;
}}

.features {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 2rem;
    margin-top: 3rem;
}}

.feature-item {{
    text-align: center;
    padding: 2rem;
    background: {colors["bg"]};
    border-radius: 10px;
    box-shadow: 0 3px 10px rgba(0,0,0,0.1);
    transition: transform 0.3s;
}}

.feature-item:hover {{
    transform: translateY(-5px);
}}

.feature-item h3 {{
    color: {colors["primary"]};
    margin-bottom: 1rem;
    font-size: 1.3rem;
}}

.contact form {{
    max-width: 600px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
}}

.contact input,
.contact textarea {{
    padding: 1rem;
    border: 2px solid {colors["primary"]}44;
    border-radius: 5px;
    font-size: 1rem;
    font-family: inherit;
}}

.contact input:focus,
.contact textarea:focus {{
    outline: none;
    border-color: {colors["primary"]};
}}

.contact textarea {{
    resize: vertical;
    min-height: 150px;
}}

footer {{
    background: {colors["text"]};
    color: white;
    text-align: center;
    padding: 2rem;
    margin-top: 4rem;
}}

footer .container {{
    max-width: 1200px;
    margin: 0 auto;
}}

footer p {{
    margin: 0.5rem 0;
    opacity: 0.9;
}}

@media (max-width: 768px) {{
    .nav-links {{
        flex-direction: column;
        gap: 1rem;
    }}
    
    .hero h1 {{
        font-size: 2rem;
    }}
    
    .service-grid {{
        grid-template-columns: 1fr;
    }}
}}'''
            
            # Generate JavaScript with variations
            js_variations = [
                f'''// Generated JavaScript for {site_name}
console.log("{site_name} website loaded successfully!");

// Smooth scrolling navigation
document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
    anchor.addEventListener('click', function (e) {{
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {{
            target.scrollIntoView({{
                behavior: 'smooth',
                block: 'start'
            }});
        }}
    }});
}});

// Contact form handling
const contactForm = document.getElementById('contactForm');
if (contactForm) {{
    contactForm.addEventListener('submit', function(e) {{
        e.preventDefault();
        alert('Thank you for your message! We will get back to you soon.');
        this.reset();
    }});
}}

// Scroll animations with Intersection Observer
const observerOptions = {{
    threshold: 0.15,
    rootMargin: '0px 0px -50px 0px'
}};

const observer = new IntersectionObserver(function(entries) {{
    entries.forEach(entry => {{
        if (entry.isIntersecting) {{
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }}
    }});
}}, observerOptions);

// Animate sections on scroll
document.querySelectorAll('section').forEach((section, index) => {{
    section.style.opacity = '0';
    section.style.transform = 'translateY(30px)';
    const delay = index * 0.1;
    section.style.transition = 'opacity 0.8s ease ' + delay + 's, transform 0.8s ease ' + delay + 's';
    observer.observe(section);
}});

// Add hover effects to service cards
document.querySelectorAll('.service-card').forEach(card => {{
    card.addEventListener('mouseenter', function() {{
        this.style.boxShadow = '0 10px 25px rgba(0,0,0,0.15)';
    }});
    card.addEventListener('mouseleave', function() {{
        this.style.boxShadow = '0 5px 15px rgba(0,0,0,0.1)';
    }});
}});''',
                
                f'''// Generated JavaScript for {prompt[:30]}
console.log("Website initialized - {site_name}");

// Enhanced smooth scrolling
document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
    anchor.addEventListener('click', function (e) {{
        e.preventDefault();
        const href = this.getAttribute('href');
        const target = document.querySelector(href);
        if (target) {{
            const offset = 80;
            const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({{
                top: targetPosition,
                behavior: 'smooth'
            }});
        }}
    }});
}});

// Form validation and submission
const contactForm = document.getElementById('contactForm');
if (contactForm) {{
    contactForm.addEventListener('submit', function(e) {{
        e.preventDefault();
        const formData = new FormData(this);
        const name = this.querySelector('input[type="text"]').value;
        const email = this.querySelector('input[type="email"]').value;
        
        if (name && email) {{
            alert('Thank you ' + name + '! We received your message and will contact you at ' + email + '.');
            this.reset();
        }}
    }});
}}

// Scroll-triggered animations
const animateOnScroll = () => {{
    const elements = document.querySelectorAll('section, .service-card, .feature-item');
    elements.forEach(el => {{
        const elementTop = el.getBoundingClientRect().top;
        const elementVisible = 150;
        
        if (elementTop < window.innerHeight - elementVisible) {{
            el.style.opacity = '1';
            el.style.transform = 'translateY(0)';
        }}
    }});
}};

// Initialize animations
document.querySelectorAll('section, .service-card, .feature-item').forEach(el => {{
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s, transform 0.6s';
}});

window.addEventListener('scroll', animateOnScroll);
animateOnScroll(); // Run once on load'''
            ]
            
            # Select JS variation based on prompt hash
            js_index = hash(prompt) % len(js_variations)
            js_template = js_variations[js_index]
            
            return {
                'html': html_template.encode('utf-8'),
                'css': css_template.encode('utf-8'),
                'js': js_template.encode('utf-8'),
                'method': 'template'
            }
        
        # Generate website
        result = await loop.run_in_executor(None, generate_website, prompt)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Check file sizes
        max_size = 50 * 1024 * 1024
        html_size = len(result['html'])
        css_size = len(result['css'])
        js_size = len(result['js'])
        
        if html_size > max_size or css_size > max_size or js_size > max_size:
            await update.message.reply_text(
                f"❌ **File too large**\n\n"
                f"One or more files exceed Telegram's 50MB limit.\n\n"
                f"Try a simpler website description."
            )
            return
        
        # Send HTML file
        html_buffer = io.BytesIO(result['html'])
        html_buffer.name = "index.html"
        
        html_msg = await update.message.reply_document(
            document=html_buffer,
            filename=html_buffer.name,
            caption=(
                f"✅ **Website Generated Successfully!**\n\n"
                f"🌐 **Description:** `{prompt[:100]}{'...' if len(prompt) > 100 else ''}`\n\n"
                f"📄 **HTML File** ({html_size / 1024:.1f} KB)\n"
                f"🔧 **Method:** {result.get('method', 'template').upper()}\n\n"
                f"📎 Sending CSS and JS files..."
            ),
            parse_mode='Markdown'
        )
        
        # Send CSS file
        css_buffer = io.BytesIO(result['css'])
        css_buffer.name = "style.css"
        
        await update.message.reply_document(
            document=css_buffer,
            filename=css_buffer.name,
            caption=f"📄 **CSS File** ({css_size / 1024:.1f} KB)",
            parse_mode='Markdown'
        )
        
        # Send JS file
        js_buffer = io.BytesIO(result['js'])
        js_buffer.name = "script.js"
        
        await update.message.reply_document(
            document=js_buffer,
            filename=js_buffer.name,
            caption=(
                f"📄 **JavaScript File** ({js_size / 1024:.1f} KB)\n\n"
                f"💡 **Tip:** Save all 3 files in the same folder and open `index.html` in your browser to view your website!"
            ),
            parse_mode='Markdown'
        )
        
        logger.info(f"Website built and sent successfully: {prompt}")
        
    except Exception as e:
        logger.error(f"Website building error: {e}", exc_info=True)
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "timeout" in error_msg:
            detailed_msg = (
                "❌ **Generation Timeout**\n\n"
                "Website generation took too long.\n\n"
                "**What you can try:**\n"
                "• Try a simpler description\n"
                "• Wait a moment and try again\n"
                "• Use more specific keywords"
            )
        else:
            detailed_msg = (
                f"❌ **Error Building Website**\n\n"
                f"Error: {str(e)}\n\n"
                "**What you can try:**\n"
                "• Check your internet connection\n"
                "• Try a different description\n"
                "• Make sure the prompt is clear and specific"
            )
        
        await update.message.reply_text(detailed_msg)

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get cryptocurrency price information."""
    # Check if user is blocked
    if await check_user_blocked(update, context):
        return
    
    if not context.args:
        help_text = (
            "💰 **Crypto Price Checker**\n\n"
            "**Usage:** `/crypto <coin>` or `/crypto <coin> <currency>`\n\n"
            "**Examples:**\n"
            "• `/crypto bitcoin` - Bitcoin price in USD\n"
            "• `/crypto ethereum` - Ethereum price\n"
            "• `/crypto btc inr` - Bitcoin price in INR\n"
            "• `/crypto doge` - Dogecoin price\n"
            "• `/crypto solana bdt` - Solana price in BDT\n\n"
            "**Popular Coins (200+ supported):**\n"
            "• bitcoin, btc - Bitcoin\n"
            "• ethereum, eth - Ethereum\n"
            "• binancecoin, bnb - Binance Coin\n"
            "• solana, sol - Solana\n"
            "• cardano, ada - Cardano\n"
            "• dogecoin, doge - Dogecoin\n"
            "• ripple, xrp - Ripple\n"
            "• polkadot, dot - Polkadot\n"
            "• polygon, matic - Polygon\n"
            "• litecoin, ltc - Litecoin\n"
            "• shiba-inu, shib - Shiba Inu\n"
            "• avalanche, avax - Avalanche\n"
            "• chainlink, link - Chainlink\n"
            "• cosmos, atom - Cosmos\n"
            "• uniswap, uni - Uniswap\n"
            "• tether, usdt - Tether\n"
            "• usd-coin, usdc - USD Coin\n"
            "• arbitrum, arb - Arbitrum\n"
            "• optimism, op - Optimism\n"
            "• aptos, apt - Aptos\n"
            "• sui - Sui\n"
            "• pepe - Pepe\n"
            "• bonk - Bonk\n"
            "• fetch-ai, fet - Fetch AI\n"
            "• render, rndr - Render\n"
            "• apecoin, ape - ApeCoin\n"
            "• ton, toncoin - The Open Network (TON)\n\n"
            "💡 **Tip:** Use symbol (btc) or full name (bitcoin)\n"
            "💡 **Tip:** Supports 200+ cryptocurrencies!\n\n"
            "**Supported Currencies:**\n"
            "usd, eur, gbp, inr, bdt, jpy, cad, aud, and more\n\n"
            "💡 **Tip:** Use coin symbol or full name!"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    coin_input = context.args[0].lower()
    
    # Default currency is USD, but check if user specified another
    currency = 'usd'
    if len(context.args) >= 2:
        # Check if second argument is a currency (common patterns)
        currency_input = context.args[1].lower()
        if currency_input in ['in', 'inr', 'bdt', 'eur', 'gbp', 'jpy', 'cad', 'aud', 'cny', 'sgd', 'hkd', 'nzd', 'brl', 'mxn', 'krw', 'try', 'rub', 'pln', 'thb', 'idr', 'php', 'zar', 'sek', 'nok', 'dkk', 'chf', 'myr', 'vnd', 'pkr', 'egp', 'aed', 'sar', 'ils', 'clp', 'cop', 'ars', 'pen', 'nzd']:
            currency = currency_input
        elif currency_input == 'in':
            currency = 'inr'
    
    # Coin name mapping (common aliases) - Expanded list with 100+ tokens
    coin_mapping = {
        # Top 20 Major Cryptocurrencies
        'btc': 'bitcoin',
        'bitcoin': 'bitcoin',
        'eth': 'ethereum',
        'ethereum': 'ethereum',
        'bnb': 'binancecoin',
        'binance': 'binancecoin',
        'binancecoin': 'binancecoin',
        'sol': 'solana',
        'solana': 'solana',
        'ada': 'cardano',
        'cardano': 'cardano',
        'xrp': 'ripple',
        'ripple': 'ripple',
        'doge': 'dogecoin',
        'dogecoin': 'dogecoin',
        'dot': 'polkadot',
        'polkadot': 'polkadot',
        'matic': 'matic-network',
        'polygon': 'matic-network',
        'ltc': 'litecoin',
        'litecoin': 'litecoin',
        'trx': 'tron',
        'tron': 'tron',
        'shib': 'shiba-inu',
        'shiba': 'shiba-inu',
        'shibainu': 'shiba-inu',
        'avax': 'avalanche-2',
        'avalanche': 'avalanche-2',
        'link': 'chainlink',
        'chainlink': 'chainlink',
        'atom': 'cosmos',
        'cosmos': 'cosmos',
        'xlm': 'stellar',
        'stellar': 'stellar',
        'etc': 'ethereum-classic',
        'ethereumclassic': 'ethereum-classic',
        'icp': 'internet-computer',
        'internetcomputer': 'internet-computer',
        'near': 'near',
        'nearprotocol': 'near',
        'hbar': 'hedera-hashgraph',
        'hedera': 'hedera-hashgraph',
        'fil': 'filecoin',
        'filecoin': 'filecoin',
        'algo': 'algorand',
        'algorand': 'algorand',
        'xtz': 'tezos',
        'tezos': 'tezos',
        'vet': 'vechain',
        'vechain': 'vechain',
        'theta': 'theta-token',
        'thetatoken': 'theta-token',
        'ftm': 'fantom',
        'fantom': 'fantom',
        'eos': 'eos',
        'xmr': 'monero',
        'monero': 'monero',
        'zec': 'zcash',
        'zcash': 'zcash',
        'dash': 'dash',
        
        # Stablecoins
        'usdt': 'tether',
        'tether': 'tether',
        'usdc': 'usd-coin',
        'usdcoin': 'usd-coin',
        'busd': 'binance-usd',
        'binanceusd': 'binance-usd',
        'dai': 'dai',
        'tusd': 'true-usd',
        'trueusd': 'true-usd',
        'usdp': 'paxos-standard',
        'pax': 'paxos-standard',
        
        # DeFi Tokens
        'aave': 'aave',
        'uni': 'uniswap',
        'uniswap': 'uniswap',
        'sushi': 'sushi',
        'sushiswap': 'sushi',
        'comp': 'compound-governance-token',
        'compound': 'compound-governance-token',
        'mkr': 'maker',
        'maker': 'maker',
        'cake': 'pancakeswap-token',
        'pancakeswap': 'pancakeswap-token',
        'crv': 'curve-dao-token',
        'curve': 'curve-dao-token',
        'snx': 'havven',
        'synthetix': 'havven',
        'yfi': 'yearn-finance',
        'yearn': 'yearn-finance',
        '1inch': '1inch',
        '1inch-network': '1inch',
        'bal': 'balancer',
        'balancer': 'balancer',
        'ren': 'republic-protocol',
        'renbtc': 'renbtc',
        'knc': 'kyber-network-crystal',
        'kyber': 'kyber-network-crystal',
        'zrx': '0x',
        '0x': '0x',
        
        # Layer 2 & Scaling Solutions
        'arb': 'arbitrum',
        'arbitrum': 'arbitrum',
        'op': 'optimism',
        'optimism': 'optimism',
        'loopring': 'loopring',
        'lrc': 'loopring',
        'imx': 'immutable-x',
        'immutablex': 'immutable-x',
        'metis': 'metis-token',
        
        # Gaming & NFT Tokens
        'mana': 'decentraland',
        'decentraland': 'decentraland',
        'sand': 'the-sandbox',
        'sandbox': 'the-sandbox',
        'axs': 'axie-infinity',
        'axie': 'axie-infinity',
        'gala': 'gala',
        'enj': 'enjincoin',
        'enjin': 'enjincoin',
        'flow': 'flow',
        'illuvium': 'illuvium',
        'ilv': 'illuvium',
        'gmt': 'stepn',
        'stepn': 'stepn',
        'ape': 'apecoin',
        'apecoin': 'apecoin',
        'immutable': 'immutable-x',
        
        # Exchange Tokens
        'ftt': 'ftx-token',
        'ftx': 'ftx-token',
        'gt': 'gatechain-token',
        'gate': 'gatechain-token',
        'kcs': 'kucoin-shares',
        'kucoin': 'kucoin-shares',
        'ht': 'huobi-token',
        'huobi': 'huobi-token',
        'okb': 'okb',
        'okex': 'okb',
        'leo': 'leo-token',
        'bitfinex': 'leo-token',
        'crypto': 'crypto-com-chain',
        'cro': 'crypto-com-chain',
        'cel': 'celsius-degree-token',
        'celsius': 'celsius-degree-token',
        
        # Meme Coins
        'floki': 'floki',
        'flokinu': 'floki',
        'pepe': 'pepe',
        'bonk': 'bonk',
        'babydoge': 'baby-doge-coin',
        'babydogecoin': 'baby-doge-coin',
        'dogelon': 'dogelon-mars',
        'elon': 'dogelon-mars',
        'shibarium': 'shibarium',
        
        # AI & Big Data
        'fet': 'fetch-ai',
        'fetch': 'fetch-ai',
        'fetchai': 'fetch-ai',
        'ocean': 'ocean-protocol',
        'oceanprotocol': 'ocean-protocol',
        'grt': 'the-graph',
        'graph': 'the-graph',
        'rndr': 'render-token',
        'render': 'render-token',
        
        # Infrastructure & Cloud
        'rune': 'thorchain',
        'thorchain': 'thorchain',
        'kava': 'kava',
        'terra': 'terra-luna',
        'luna': 'terra-luna',
        'lunc': 'terra-luna-2',
        'luna2': 'terra-luna-2',
        'inj': 'injective-protocol',
        'injective': 'injective-protocol',
        
        # Privacy Coins
        'zec': 'zcash',
        'dash': 'dash',
        'xmr': 'monero',
        'zcoin': 'firo',
        'firo': 'firo',
        
        # Smart Contract Platforms
        'avax': 'avalanche-2',
        'ftm': 'fantom',
        'matic': 'matic-network',
        'dot': 'polkadot',
        'atom': 'cosmos',
        'sol': 'solana',
        'ada': 'cardano',
        'algo': 'algorand',
        'egld': 'elrond-erd-2',
        'elrond': 'elrond-erd-2',
        'multiversx': 'elrond-erd-2',
        'hbar': 'hedera-hashgraph',
        'icp': 'internet-computer',
        'apt': 'aptos',
        'aptos': 'aptos',
        'sui': 'sui',
        'sei': 'sei-network',
        'seinetwork': 'sei-network',
        'tia': 'celestia',
        'celestia': 'celestia',
        
        # Oracle & Data
        'link': 'chainlink',
        'band': 'band-protocol',
        'bandprotocol': 'band-protocol',
        'nest': 'nest-protocol',
        'nestprotocol': 'nest-protocol',
        
        # Social & Content
        'bat': 'basic-attention-token',
        'battoken': 'basic-attention-token',
        'rss3': 'rss3',
        'mask': 'mask-network',
        'masknetwork': 'mask-network',
        
        # Metaverse & VR
        'mana': 'decentraland',
        'sand': 'the-sandbox',
        'somnium': 'somnium-space-cubes',
        'vr': 'somnium-space-cubes',
        
        # Additional Popular Tokens
        'qnt': 'quant-network',
        'quant': 'quant-network',
        'xym': 'symbol',
        'symbol': 'symbol',
        'xdc': 'xdce-crowd-sale',
        'xdcnetwork': 'xdce-crowd-sale',
        'hnt': 'helium',
        'helium': 'helium',
        'iotex': 'iotex',
        'iotx': 'iotex',
        'one': 'harmony',
        'harmony': 'harmony',
        'rose': 'oasis-network',
        'oasis': 'oasis-network',
        'celo': 'celo',
        'celodollar': 'celo',
        'omg': 'omisego',
        'omisego': 'omisego',
        'zil': 'zilliqa',
        'zilliqa': 'zilliqa',
        'wax': 'wax',
        'waxp': 'wax',
        'hive': 'hive',
        'hiveblockchain': 'hive',
        'waves': 'waves',
        'nano': 'nano',
        'xno': 'nano',
        'iota': 'iota',
        'miota': 'iota',
        'xem': 'nem',
        'nem': 'nem',
        'qtum': 'qtum',
        'ont': 'ontology',
        'ontology': 'ontology',
        'zcn': '0chain',
        '0chain': '0chain',
        'sc': 'siacoin',
        'siacoin': 'siacoin',
        'stx': 'blockstack',
        'blockstack': 'blockstack',
        'stacks': 'blockstack',
        
        # The Open Network (TON)
        'ton': 'the-open-network',
        'toncoin': 'the-open-network',
        'the-open-network': 'the-open-network',
        'telegram-open-network': 'the-open-network',
    }
    
    # Get coin ID from mapping or use input as-is
    coin_id = coin_mapping.get(coin_input, coin_input)
    
    processing_msg = await update.message.reply_text(
        f"💰 Fetching {coin_input.upper()} price...\n"
        f"⏳ Please wait..."
    )
    
    try:
        def get_crypto_price(coin, curr):
            """Fetch cryptocurrency price from CoinGecko API."""
            try:
                # CoinGecko free API (no key needed)
                # Always include USD for market cap and volume, plus requested currency
                currencies = 'usd,' + curr if curr != 'usd' else 'usd'
                
                api_url = f"https://api.coingecko.com/api/v3/simple/price"
                params = {
                    'ids': coin,
                    'vs_currencies': currencies,
                    'include_market_cap': 'true',
                    'include_24hr_change': 'true',
                    'include_24hr_vol': 'true',
                    'include_last_updated_at': 'true'
                }
                
                response = requests.get(api_url, params=params, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if coin in data:
                        return data[coin]
                    else:
                        raise Exception(f"Coin '{coin}' not found")
                elif response.status_code == 404:
                    raise Exception(f"Coin '{coin}' not found. Try: bitcoin, ethereum, dogecoin, etc.")
                else:
                    raise Exception(f"API returned status {response.status_code}")
            except requests.exceptions.Timeout:
                raise Exception("Request timeout. Please try again.")
            except requests.exceptions.RequestException as e:
                raise Exception(f"Network error: {str(e)}")
            except Exception as e:
                logger.error(f"Crypto price error: {e}")
                raise
        
        loop = asyncio.get_event_loop()
        price_data = await loop.run_in_executor(None, get_crypto_price, coin_id, currency)
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        # Format price data
        price_key = currency
        price_value = price_data.get(price_key, 0)
        # Handle both dict and number formats
        if isinstance(price_value, dict):
            current_price = price_value.get('value', 0)
        else:
            current_price = price_value
        
        # Currency symbols
        currency_symbols = {
            'usd': '$', 'eur': '€', 'gbp': '£', 'jpy': '¥', 'inr': '₹', 'bdt': '৳',
            'cad': 'C$', 'aud': 'A$', 'cny': '¥', 'sgd': 'S$', 'hkd': 'HK$', 'nzd': 'NZ$',
            'brl': 'R$', 'mxn': 'Mex$', 'krw': '₩', 'try': '₺', 'rub': '₽', 'pln': 'zł',
            'thb': '฿', 'idr': 'Rp', 'php': '₱', 'zar': 'R', 'sek': 'kr', 'nok': 'kr',
            'dkk': 'kr', 'chf': 'CHF', 'myr': 'RM', 'vnd': '₫', 'pkr': '₨', 'egp': 'E£',
            'aed': 'د.إ', 'sar': '﷼', 'ils': '₪', 'clp': '$', 'cop': '$', 'ars': '$', 'pen': 'S/'
        }
        
        symbol = currency_symbols.get(currency, currency.upper())
        
        # Format price with appropriate decimal places
        if current_price >= 1000:
            price_str = f"{symbol}{current_price:,.2f}"
        elif current_price >= 1:
            price_str = f"{symbol}{current_price:,.4f}"
        elif current_price >= 0.01:
            price_str = f"{symbol}{current_price:,.6f}"
        else:
            price_str = f"{symbol}{current_price:.10f}"
        
        # Get market cap (always in USD for global comparison)
        market_cap_key = "usd_market_cap"
        market_cap = price_data.get(market_cap_key, 0)
        market_cap_str = f"${market_cap:,.0f}" if market_cap else "N/A"
        
        # Get 24h change
        change_24h_key = f"{price_key}_24h_change"
        change_24h = price_data.get(change_24h_key, 0)
        change_emoji = "📈" if change_24h >= 0 else "📉"
        change_str = f"{change_24h:+.2f}%"
        
        # Get 24h volume (always in USD for global comparison)
        volume_24h_key = "usd_24h_vol"
        volume_24h = price_data.get(volume_24h_key, 0)
        volume_str = f"${volume_24h:,.0f}" if volume_24h else "N/A"
        
        # Get last updated time
        last_updated = price_data.get('last_updated_at', 0)
        if last_updated:
            from datetime import datetime
            update_time = datetime.fromtimestamp(last_updated)
            time_str = update_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            time_str = "N/A"
        
        # Format response
        coin_display = coin_input.upper()
        currency_display = currency.upper()
        
        response_text = (
            f"💰 **{coin_display} Price**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💵 **Current Price:**\n"
            f"   {price_str}\n\n"
            f"{change_emoji} **24h Change:**\n"
            f"   {change_str}\n\n"
            f"📊 **Market Cap:**\n"
            f"   {market_cap_str}\n\n"
            f"📈 **24h Volume:**\n"
            f"   {volume_str}\n\n"
            f"🕐 **Last Updated:**\n"
            f"   {time_str}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 Use `/crypto {coin_input} <currency>` for other currencies"
        )
        
        await update.message.reply_text(response_text, parse_mode='Markdown')
        
    except Exception as e:
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        error_msg = str(e).lower()
        if "not found" in error_msg:
            detailed_msg = (
                f"❌ **Coin Not Found**\n\n"
                f"Could not find '{coin_input}'.\n\n"
                "**Try these popular coins:**\n"
                "• `/crypto bitcoin` or `/crypto btc`\n"
                "• `/crypto ethereum` or `/crypto eth`\n"
                "• `/crypto dogecoin` or `/crypto doge`\n"
                "• `/crypto solana` or `/crypto sol`\n"
                "• `/crypto cardano` or `/crypto ada`\n\n"
                "💡 Use coin symbol (btc, eth) or full name (bitcoin, ethereum)"
            )
        elif "timeout" in error_msg:
            detailed_msg = (
                "❌ **Request Timeout**\n\n"
                "The API took too long to respond.\n\n"
                "**What you can try:**\n"
                "• Wait a moment and try again\n"
                "• Check your internet connection"
            )
        else:
            detailed_msg = (
                f"❌ **Error Fetching Price**\n\n"
                f"Error: {str(e)}\n\n"
                "**What you can try:**\n"
                "• Check your internet connection\n"
                "• Verify the coin name is correct\n"
                "• Try again in a few moments"
            )
        
        await update.message.reply_text(detailed_msg)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors gracefully."""
    try:
        error = context.error
        
        # Check if it's a Conflict error (multiple bot instances)
        if isinstance(error, Conflict):
            error_msg = str(error)
            if "terminated by other getUpdates" in error_msg or "Conflict" in error_msg:
                logger.error("❌ Another bot instance is already running!")
                logger.error("Please stop all other bot instances and try again.")
                logger.error("You can use stop_bot.bat to stop all instances.")
                print("\n" + "="*60)
                print("❌ ERROR: Another bot instance is running!")
                print("="*60)
                print("\n🔧 To fix this:")
                print("   1. Run 'stop_bot.bat' in this folder")
                print("   2. Or press Ctrl+C to stop this instance")
                print("   3. Close all Python/Py processes from Task Manager")
                print("   4. Wait 5 seconds")
                print("   5. Then start the bot again\n")
                print("💡 Tip: Make sure only ONE bot instance is running!")
                print("="*60 + "\n")
                # Don't try to stop here, let the main function handle it
                # The error will propagate and be caught by the try-except in main()
                return
        
        # Log other errors but don't crash
        logger.error(f"Exception while handling an update: {error}", exc_info=error)
        
    except Exception as e:
        logger.error(f"Error in error handler: {e}", exc_info=True)

def main():
    """Start the bot."""
    try:
        import os
        os.environ.setdefault('PYTHONASYNCIODEBUG', '1')
        
        # Log Pillow status at startup
        logger.info(f"PIL_AVAILABLE: {PIL_AVAILABLE}")
        logger.info(f"IMAGEDRAW_AVAILABLE: {IMAGEDRAW_AVAILABLE}")
        logger.info(f"IMAGEFONT_AVAILABLE: {IMAGEFONT_AVAILABLE}")
        if not PIL_AVAILABLE:
            logger.error("Pillow is not available! Please install: pip install Pillow")
        else:
            logger.info("Pillow is available and ready to use!")
        
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Register error handler first to catch all errors
        application.add_error_handler(error_handler)
        
        # Register handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
        application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
        application.add_handler(CommandHandler("help", help_command))
        
        # Admin panel handlers
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("admin_stats", admin_stats_command))
        application.add_handler(CommandHandler("admin_users", admin_users_command))
        application.add_handler(CommandHandler("admin_broadcast", admin_broadcast_command))
        application.add_handler(CommandHandler("admin_referrals", admin_referrals_command))
        application.add_handler(CommandHandler("admin_add", admin_add_command))
        application.add_handler(CommandHandler("admin_remove", admin_remove_command))
        application.add_handler(CommandHandler("admin_list", admin_list_command))
        application.add_handler(CommandHandler("admin_block", admin_block_command))
        application.add_handler(CommandHandler("admin_unblock", admin_unblock_command))
        application.add_handler(CommandHandler("admin_blocked", admin_blocked_command))
        application.add_handler(CommandHandler("admin_delete_user", admin_delete_user_command))
        
        application.add_handler(CommandHandler("time", time_command))
        application.add_handler(CommandHandler("date", date_command))
        application.add_handler(CommandHandler("calendar", calendar_command))
        application.add_handler(CommandHandler("alarm", alarm_command))
        application.add_handler(CommandHandler("alarms", alarms_command))
        application.add_handler(CommandHandler("deletealarm", deletealarm_command))
        application.add_handler(CommandHandler("removealarm", deletealarm_command))  # Alias
        application.add_handler(CommandHandler("cal", calendar_command))  # Alias
        application.add_handler(CommandHandler("calender", calendar_command))  # Alias (common misspelling)
        application.add_handler(CommandHandler("testpillow", test_pillow_command))
        application.add_handler(CommandHandler("calc", calc_command))
        application.add_handler(CommandHandler("solve", solve_command))
        application.add_handler(CommandHandler("equation", solve_command))  # Alias
        application.add_handler(CommandHandler("convert", convert_command))
        application.add_handler(CommandHandler("unit", convert_command))  # Alias
        application.add_handler(CommandHandler("percent", percent_command))
        application.add_handler(CommandHandler("percentage", percent_command))  # Alias
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("statistics", stats_command))  # Alias
        application.add_handler(CommandHandler("bin", bin_command))
        application.add_handler(CommandHandler("binary", bin_command))  # Alias
        application.add_handler(CommandHandler("hex", hex_command))
        application.add_handler(CommandHandler("hexadecimal", hex_command))  # Alias
        application.add_handler(CommandHandler("oct", oct_command))
        application.add_handler(CommandHandler("octal", oct_command))  # Alias
        application.add_handler(CommandHandler("birthday", birthday_command))
        application.add_handler(CommandHandler("bday", birthday_command))  # Alias
        application.add_handler(CommandHandler("bd", birthday_command))  # Alias
        application.add_handler(CommandHandler("leapyear", leapyear_command))
        application.add_handler(CommandHandler("leap", leapyear_command))  # Alias
        application.add_handler(CommandHandler("ly", leapyear_command))  # Alias
        application.add_handler(CommandHandler("refer", refer_command))
        application.add_handler(CommandHandler("referral", refer_command))  # Alias
        application.add_handler(CommandHandler("ref", refer_command))  # Alias
        application.add_handler(CommandHandler("myref", refer_command))  # Alias
        application.add_handler(CommandHandler("wiki", wiki_command))
        application.add_handler(CommandHandler("qr", qr_command))
        application.add_handler(CommandHandler("password", password_command))
        application.add_handler(CommandHandler("pass", password_command))  # Alias
        application.add_handler(CommandHandler("genpass", password_command))  # Alias
        application.add_handler(CommandHandler("pwd", password_command))  # Alias
        application.add_handler(CommandHandler("deviceinfo", deviceinfo_command))
        application.add_handler(CommandHandler("device", deviceinfo_command))  # Alias
        application.add_handler(CommandHandler("devinfo", deviceinfo_command))  # Alias
        application.add_handler(CommandHandler("sysinfo", deviceinfo_command))  # Alias
        application.add_handler(CommandHandler("fancyfont", fancyfont_command))
        application.add_handler(CommandHandler("font", fancyfont_command))  # Alias
        application.add_handler(CommandHandler("fancy", fancyfont_command))  # Alias
        application.add_handler(CommandHandler("textfont", fancyfont_command))  # Alias
        application.add_handler(CommandHandler("texttoemoji", texttoemoji_command))
        application.add_handler(CommandHandler("emoji", texttoemoji_command))  # Alias
        application.add_handler(CommandHandler("textemoji", texttoemoji_command))  # Alias
        application.add_handler(CommandHandler("wordtoemoji", texttoemoji_command))  # Alias
        application.add_handler(CommandHandler("mp4tomp3", mp4tomp3_command))
        application.add_handler(CommandHandler("videotomp3", mp4tomp3_command))  # Alias
        application.add_handler(CommandHandler("v2a", mp4tomp3_command))  # Alias
        application.add_handler(CommandHandler("video2audio", mp4tomp3_command))  # Alias
        application.add_handler(CommandHandler("repeat", repeat_command))
        application.add_handler(CommandHandler("repeator", repeat_command))  # Alias
        application.add_handler(CommandHandler("textrepeat", repeat_command))  # Alias
        application.add_handler(CommandHandler("removeduplicates", removeduplicates_command))
        application.add_handler(CommandHandler("removedup", removeduplicates_command))  # Alias
        application.add_handler(CommandHandler("dedup", removeduplicates_command))  # Alias
        application.add_handler(CommandHandler("rmdup", removeduplicates_command))  # Alias
        application.add_handler(CommandHandler("hash", hash_command))
        application.add_handler(CommandHandler("md5", hash_command))  # Alias
        application.add_handler(CommandHandler("sha1", hash_command))  # Alias
        application.add_handler(CommandHandler("sha256", hash_command))  # Alias
        application.add_handler(CommandHandler("sha512", hash_command))  # Alias
        application.add_handler(CommandHandler("shorturl", shorturl_command))
        application.add_handler(CommandHandler("short", shorturl_command))  # Alias
        application.add_handler(CommandHandler("url", shorturl_command))  # Alias
        application.add_handler(CommandHandler("screenshot", screenshot_command))
        application.add_handler(CommandHandler("ss", screenshot_command))  # Alias
        application.add_handler(CommandHandler("webss", screenshot_command))  # Alias
        application.add_handler(CommandHandler("iplookup", ip_lookup_command))
        application.add_handler(CommandHandler("ip", ip_lookup_command))  # Alias
        application.add_handler(CommandHandler("ipinfo", ip_lookup_command))  # Alias
        application.add_handler(CommandHandler("crypto", crypto_command))
        application.add_handler(CommandHandler("cryptoprice", crypto_command))  # Alias
        application.add_handler(CommandHandler("coin", crypto_command))  # Alias
        application.add_handler(CommandHandler("price", crypto_command))  # Alias
        application.add_handler(CommandHandler("audiototext", audio_to_text_command))
        application.add_handler(CommandHandler("speech", audio_to_text_command))  # Alias
        application.add_handler(CommandHandler("voice", audio_to_text_command))  # Alias
        # Handle voice messages automatically
        application.add_handler(MessageHandler(filters.VOICE, audio_to_text_command))
        application.add_handler(MessageHandler(filters.AUDIO, audio_to_text_command))
        application.add_handler(CommandHandler("generate", generate_command))
        application.add_handler(CommandHandler("create", generate_command))  # Alias
        application.add_handler(CommandHandler("image", generate_command))  # Alias
        application.add_handler(CommandHandler("texttoimage", generate_command))  # Alias
        application.add_handler(CommandHandler("t2i", generate_command))  # Alias
        application.add_handler(CommandHandler("txt2img", generate_command))  # Alias
        application.add_handler(CommandHandler("textonimage", textonimage_command))
        application.add_handler(CommandHandler("textimg", textonimage_command))  # Alias
        application.add_handler(CommandHandler("txtimg", textonimage_command))  # Alias
        application.add_handler(CommandHandler("translate", translate_command))
        application.add_handler(CommandHandler("trans", translate_command))  # Alias
        application.add_handler(CommandHandler("tr", translate_command))  # Alias
        application.add_handler(CommandHandler("ocr", ocr_command))
        application.add_handler(CommandHandler("ocrsetup", ocrsetup_command))
        application.add_handler(CommandHandler("text", ocr_command))  # Alias
        application.add_handler(CommandHandler("extract", ocr_command))  # Alias
        application.add_handler(CommandHandler("imagetopdf", imagetopdf_command))
        application.add_handler(CommandHandler("imgtopdf", imagetopdf_command))  # Alias
        application.add_handler(CommandHandler("image2pdf", imagetopdf_command))  # Alias
        application.add_handler(CommandHandler("itp", imagetopdf_command))  # Alias
        application.add_handler(CommandHandler("pdftoimage", pdftoimage_command))
        application.add_handler(CommandHandler("pdftoimg", pdftoimage_command))  # Alias
        application.add_handler(CommandHandler("pdf2image", pdftoimage_command))  # Alias
        application.add_handler(CommandHandler("pti", pdftoimage_command))  # Alias
        application.add_handler(CommandHandler("blur", blur_command))
        application.add_handler(CommandHandler("bgblur", bgblur_command))
        application.add_handler(CommandHandler("watermark", watermark_command))
        application.add_handler(CommandHandler("wm", watermark_command))  # Alias
        application.add_handler(CommandHandler("addwatermark", watermark_command))  # Alias
        application.add_handler(CommandHandler("filter", filter_command))
        application.add_handler(CommandHandler("filters", filter_command))  # Alias
        application.add_handler(CommandHandler("imgfilter", filter_command))  # Alias
        application.add_handler(CommandHandler("enhance", enhance_command))
        application.add_handler(CommandHandler("resize", resize_command))
        application.add_handler(CommandHandler("tojpg", tojpg_command))
        application.add_handler(CommandHandler("jpg", tojpg_command))  # Alias
        application.add_handler(CommandHandler("sticker", sticker_command))
        application.add_handler(CommandHandler("stick", sticker_command))  # Alias
        application.add_handler(CommandHandler("img2sticker", sticker_command))  # Alias
        application.add_handler(CommandHandler("tiktok", tiktok_download_command))
        application.add_handler(CommandHandler("tt", tiktok_download_command))  # Alias
        application.add_handler(CommandHandler("tiktokdl", tiktok_download_command))  # Alias
        application.add_handler(CommandHandler("yt", youtube_download_command))
        application.add_handler(CommandHandler("youtube", youtube_download_command))  # Alias
        application.add_handler(CommandHandler("ytdl", youtube_download_command))  # Alias
        application.add_handler(CommandHandler("fb", facebook_download_command))
        application.add_handler(CommandHandler("facebook", facebook_download_command))  # Alias
        application.add_handler(CommandHandler("fbdl", facebook_download_command))  # Alias
        application.add_handler(CommandHandler("ig", instagram_download_command))
        application.add_handler(CommandHandler("instagram", instagram_download_command))  # Alias
        application.add_handler(CommandHandler("igdl", instagram_download_command))  # Alias
        application.add_handler(CommandHandler("clone", clone_website_command))
        application.add_handler(CommandHandler("website", clone_website_command))  # Alias
        application.add_handler(CommandHandler("webclone", clone_website_command))  # Alias
        application.add_handler(CommandHandler("wclone", clone_website_command))  # Alias
        application.add_handler(CommandHandler("build", build_website_command))
        application.add_handler(CommandHandler("buildwebsite", build_website_command))  # Alias
        application.add_handler(CommandHandler("createwebsite", build_website_command))  # Alias
        application.add_handler(CommandHandler("makewebsite", build_website_command))  # Alias
        # Handle video files for MP4 to MP3 conversion
        application.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, mp4tomp3_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_to_speech))
        
        # Start the bot
        logger.info("Bot is starting...")
        
        # Start background alarm checking task
        # Use a one-time handler to start the alarm task when bot receives first update
        alarm_task_started = False
        
        async def start_alarm_on_first_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Start alarm task when bot receives first update."""
            nonlocal alarm_task_started
            if not alarm_task_started:
                alarm_task_started = True
                logger.info("Starting alarm checking task...")
                asyncio.create_task(check_alarms_loop(context.bot))
                # Return None to allow other handlers to process the update
                return
        
        # Add temporary handler for first update (will run on first message/update)
        first_update_handler = MessageHandler(filters.ALL, start_alarm_on_first_update)
        application.add_handler(first_update_handler, group=-1)  # Add with high priority
        
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES, 
                drop_pending_updates=True,
                close_loop=False
            )
        except Conflict as conflict_error:
            # Handle Conflict error specifically
            error_str = str(conflict_error)
            logger.error("❌ Another bot instance is already running!")
            logger.error("Please stop all other bot instances and try again.")
            logger.error("You can use stop_bot.bat to stop all instances.")
            print("\n" + "="*60)
            print("❌ ERROR: Another bot instance is running!")
            print("="*60)
            print("\n🔧 To fix this:")
            print("   1. Run 'stop_bot.bat' in this folder")
            print("   2. Or press Ctrl+C to stop this instance")
            print("   3. Close all Python/Py processes from Task Manager")
            print("   4. Wait 5 seconds")
            print("   5. Then start the bot again\n")
            print("💡 Tip: Make sure only ONE bot instance is running!")
            print("="*60 + "\n")
            import sys
            sys.exit(1)
        except Exception as polling_error:
            error_str = str(polling_error)
            if "Conflict" in error_str or "getUpdates" in error_str or "terminated by other" in error_str:
                logger.error("❌ Another bot instance is already running!")
                logger.error("Please stop all other bot instances and try again.")
                logger.error("You can use stop_bot.bat to stop all instances.")
                print("\n" + "="*60)
                print("❌ ERROR: Another bot instance is running!")
                print("="*60)
                print("\n🔧 To fix this:")
                print("   1. Run 'stop_bot.bat' in this folder")
                print("   2. Or press Ctrl+C to stop this instance")
                print("   3. Close all Python/Py processes from Task Manager")
                print("   4. Wait 5 seconds")
                print("   5. Then start the bot again\n")
                print("💡 Tip: Make sure only ONE bot instance is running!")
                print("="*60 + "\n")
                # Exit gracefully instead of raising
                import sys
                sys.exit(1)
            else:
                raise
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
