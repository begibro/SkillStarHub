import asyncio
import logging
import aiosqlite
import os
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# --- ENV YUKLASH ---
load_dotenv()

class config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    admin_raw = os.getenv("ADMIN_IDS", "12345678")
    ADMIN_IDS = [int(x.strip()) for x in admin_raw.split(",") if x.strip().isdigit()]
    REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", 500))
    VIP_PRICE = int(os.getenv("VIP_PRICE", 5000))

logging.basicConfig(level=logging.INFO)
DB_PATH = "bot_database.db"

if not config.BOT_TOKEN:
    raise ValueError("XATO: BOT_TOKEN topilmadi!")

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# --- DATABASE ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            balance INTEGER DEFAULT 0, 
            referral_count INTEGER DEFAULT 0, 
            is_vip BOOLEAN DEFAULT 0, 
            join_date TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, url TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            title TEXT, 
            price INTEGER, 
            file_id TEXT,
            file_type TEXT DEFAULT 'document')''')
        await db.execute('''CREATE TABLE IF NOT EXISTS purchases (user_id INTEGER, course_id INTEGER)''')
        await db.commit()

# --- STATES ---
class AdminStates(StatesGroup):
    broadcast = State()
    manage_user = State()
    edit_balance = State()
    add_ch_id = State()
    add_ch_url = State()
    c_title = State()
    c_price = State()
    c_content = State()

# --- HELPERS ---
async def check_sub(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        chs = await (await db.execute("SELECT * FROM channels")).fetchall()
        for c in chs:
            try:
                m = await bot.get_chat_member(chat_id=c['channel_id'], user_id=uid)
                if m.status in ["left", "kicked"]: return False
            except Exception: return False
        return True

async def send_course_content(chat_id, content, file_type, caption):
    """Kursni turiga qarab (fayl yoki matn) yuboruvchi funksiya"""
    try:
        if file_type == "photo":
            await bot.send_photo(chat_id, content, caption=caption)
        elif file_type == "video":
            await bot.send_video(chat_id, content, caption=caption)
        elif file_type == "audio":
            await bot.send_audio(chat_id, content, caption=caption)
        elif file_type == "text":
            # Agar bu link yoki matn bo'lsa
            await bot.send_message(chat_id, f"📘 **{caption}**\n\n🔗 Kurs linki/Ma'lumoti:\n{content}", parse_mode="Markdown")
        else:
            await bot.send_document(chat_id, content, caption=caption)
    except Exception as e:
        logging.error(f"Kurs yuborishda xato: {e}")
        await bot.send_message(chat_id, f"❌ Kursni yuborishda muammo bo'ldi. Admin bilan bog'laning.")

# --- KEYBOARDS ---
def main_menu_kb(is_vip=False):
    kb = InlineKeyboardBuilder()
    kb.button(text="📚 Kurslar", callback_data="view_courses")
    kb.button(text="👤 Kabinet", callback_data="profile")
    kb.button(text="🔗 Takliflar", callback_data="referrals")
    kb.button(text="🌟 VIP Sotib Olish" if not is_vip else "💎 VIP Status: Faol", callback_data="vip_pay")
    kb.adjust(1, 2, 1)
    return kb.as_markup()

def admin_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Kurs Qo'shish", callback_data="adm_add_course")
    kb.button(text="❌ Kursni O'chirish", callback_data="adm_del_course")
    kb.button(text="📢 Reklama", callback_data="adm_bc")
    kb.button(text="👤 Foydalanuvchini Boshqarish", callback_data="adm_user_manage")
    kb.button(text="📡 Kanallar", callback_data="adm_ch_list")
    kb.button(text="📊 Statistika", callback_data="adm_stat")
    kb.adjust(2)
    return kb.as_markup()

# --- USER HANDLERS ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        if not user:
            ref_id = None
            if message.text and len(message.text.split()) > 1:
                ref_part = message.text.split()[1]
                if ref_part.isdigit(): ref_id = int(ref_part)

            await db.execute("INSERT INTO users (user_id, join_date) VALUES (?, ?)", (uid, datetime.now().strftime("%Y-%m-%d")))
            if ref_id and ref_id != uid:
                await db.execute("UPDATE users SET balance = balance + ?, referral_count = referral_count + 1 WHERE user_id = ?", (config.REFERRAL_REWARD, ref_id))
                try: await bot.send_message(ref_id, f"✅ Sizda yangi taklif bor! +{config.REFERRAL_REWARD} ball")
                except: pass
            await db.commit()
            user = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))).fetchone()

    if not await check_sub(uid):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            chs = await (await db.execute("SELECT * FROM channels")).fetchall()
            kb = InlineKeyboardBuilder()
            for c in chs:
                kb.button(text="📢 Kanalga a'zo bo'lish", url=c['url'])
            kb.button(text="✅ Tekshirish", callback_data="recheck")
            return await message.answer("⚠️ Botdan foydalanish uchun kanallarimizga a'zo bo'ling:", reply_markup=kb.adjust(1).as_markup())

    await message.answer(f"🚀 Xush kelibsiz, {message.from_user.first_name}!", reply_markup=main_menu_kb(user['is_vip']))

@dp.callback_query(F.data == "view_courses")
async def view_courses(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        courses = await (await db.execute("SELECT * FROM courses")).fetchall()
        if not courses:
            return await call.answer("Hozircha kurslar yo'q.", show_alert=True)
        
        kb = InlineKeyboardBuilder()
        for c in courses:
            kb.button(text=f"📘 {c['title']} ({c['price']} ball)", callback_data=f"info_{c['id']}")
        kb.button(text="🔙 Bosh menyu", callback_data="back_home")
        await call.message.edit_text("📚 Mavjud kurslar ro'yxati:", reply_markup=kb.adjust(1).as_markup())

@dp.callback_query(F.data.startswith("info_"))
async def course_info(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        course = await (await db.execute("SELECT * FROM courses WHERE id = ?", (cid,))).fetchone()
        user = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (call.from_user.id,))).fetchone()
        price = int(course['price'] * 0.5) if user['is_vip'] else course['price']

        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Sotib olish ({price} ball)", callback_data=f"buy_{cid}")
        kb.button(text="🔙 Orqaga", callback_data="view_courses")
        await call.message.edit_text(f"📖 Kurs: {course['title']}\n💰 Narxi: {price} ball\n\nSotib olmoqchimisiz?", reply_markup=kb.adjust(1).as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy_course(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    uid = call.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        course = await (await db.execute("SELECT * FROM courses WHERE id = ?", (cid,))).fetchone()
        user = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        final_price = int(course['price'] * 0.5) if user['is_vip'] else course['price']
        purchased = await (await db.execute("SELECT * FROM purchases WHERE user_id = ? AND course_id = ?", (uid, cid))).fetchone()
        
        if purchased:
            await call.answer("Sizda bu kurs bor!", show_alert=True)
            return await send_course_content(uid, course['file_id'], course['file_type'], course['title'])

        if user['balance'] >= final_price:
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (final_price, uid))
            await db.execute("INSERT INTO purchases VALUES (?, ?)", (uid, cid))
            await db.commit()
            await call.message.delete()
            await bot.send_message(uid, f"🎉 Muvaffaqiyatli sotib olindi!")
            await send_course_content(uid, course['file_id'], course['file_type'], course['title'])
        else:
            await call.answer("❌ Ball yetarli emas!", show_alert=True)

# --- ADMIN COURSE ADD ---
@dp.callback_query(F.data == "adm_add_course")
async def adm_c_add(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.c_title)
    await call.message.answer("📝 Kurs nomini kiriting:")

@dp.message(AdminStates.c_title)
async def adm_c_t(message: types.Message, state: FSMContext):
    await state.update_data(ct=message.text)
    await state.set_state(AdminStates.c_price)
    await message.answer("💰 Kurs narxini kiriting (ball):")

@dp.message(AdminStates.c_price)
async def adm_c_p(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Narxni raqamda yozing!")
    await state.update_data(cp=int(message.text))
    await state.set_state(AdminStates.c_content)
    await message.answer("📁 Kurs kontentini yuboring:\n\nFayl, Video, Rasm yuborishingiz yoki kurs **LINKINI (havolasini)** yozib yuborishingiz mumkin.")

@dp.message(AdminStates.c_content)
async def adm_c_f(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = None
    file_type = "text" # Default

    if message.document:
        file_id, file_type = message.document.file_id, "document"
    elif message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.audio:
        file_id, file_type = message.audio.file_id, "audio"
    elif message.text:
        file_id, file_type = message.text, "text"
    
    if not file_id:
        return await message.answer("❌ Noto'g'ri format. Link yozing yoki fayl yuboring!")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO courses (title, price, file_id, file_type) VALUES (?, ?, ?, ?)", 
                         (data['ct'], data['cp'], file_id, file_type))
        await db.commit()
    
    await message.answer(f"✅ Kurs muvaffaqiyatli qo'shildi!\n📌 Nomi: {data['ct']}\n📂 Turi: {file_type}")
    await state.clear()

# --- QOLGAN FUNKSIYALAR ---
@dp.callback_query(F.data == "profile")
async def profile_callback(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        u = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (call.from_user.id,))).fetchone()
        text = (f"👤 **Kabinet**\n\n🆔 ID: `{u['user_id']}`\n💰 Balans: {u['balance']} ball\n🌟 VIP: {'✅' if u['is_vip'] else '❌'}")
        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu_kb(u['is_vip']))

@dp.callback_query(F.data == "adm_stat")
async def admin_stat(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        users = (await (await db.execute("SELECT count(*) FROM users")).fetchone())[0]
        await call.message.answer(f"📊 Statistika\n👤 Foydalanuvchilar: {users}")

@dp.message(Command("admin"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_cmd(message: types.Message):
    await message.answer("🛠 Admin Panel", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "back_home")
async def back_home(call: types.CallbackQuery, state: FSMContext):
    await start_cmd(call.message, state)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
