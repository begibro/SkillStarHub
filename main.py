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
from aiogram.exceptions import TelegramBadRequest

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
            file_type TEXT DEFAULT 'document')''') # Fayl turini saqlash uchun ustun qo'shildi
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

async def send_course_file(chat_id, file_id, file_type, caption):
    """Faylni turiga qarab yuboruvchi yordamchi funksiya"""
    try:
        if file_type == "photo":
            await bot.send_photo(chat_id, file_id, caption=caption)
        elif file_type == "video":
            await bot.send_video(chat_id, file_id, caption=caption)
        elif file_type == "audio":
            await bot.send_audio(chat_id, file_id, caption=caption)
        else:
            await bot.send_document(chat_id, file_id, caption=caption)
    except Exception as e:
        logging.error(f"Fayl yuborishda xato: {e}")
        await bot.send_message(chat_id, f"❌ Faylni yuborishda xatolik yuz berdi: {caption}")

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

@dp.callback_query(F.data == "recheck")
async def recheck_callback(call: types.CallbackQuery, state: FSMContext):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await start_cmd(call.message, state)
    else:
        await call.answer("❌ Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

@dp.callback_query(F.data == "profile")
async def profile_callback(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        u = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (call.from_user.id,))).fetchone()
        text = (f"👤 **Sizning Kabinetingiz**\n\n"
                f"🆔 ID: `{u['user_id']}`\n"
                f"💰 Balans: {u['balance']} ball\n"
                f"👥 Takliflar: {u['referral_count']} ta\n"
                f"🌟 VIP Status: {'✅ Faol' if u['is_vip'] else '❌ Faol emas'}\n"
                f"📅 Ro'yxatdan o'tdingiz: {u['join_date']}")
        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=main_menu_kb(u['is_vip']))

@dp.callback_query(F.data == "referrals")
async def referrals_callback(call: types.CallbackQuery):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={call.from_user.id}"
    text = (f"🔗 **Taklif havolangiz:**\n`{link}`\n\n"
            f"Har bir taklif qilgan do'stingiz uchun **{config.REFERRAL_REWARD} ball** olasiz!")
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data="profile")
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.as_markup())

# --- COURSE SYSTEM ---
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
        
        price = course['price']
        if user['is_vip']: price = int(price * 0.5)

        kb = InlineKeyboardBuilder()
        kb.button(text=f"💳 Sotib olish ({price} ball)", callback_data=f"buy_{cid}")
        kb.button(text="🔙 Orqaga", callback_data="view_courses")
        
        await call.message.edit_text(f"📖 Kurs: {course['title']}\n💰 Narxi: {price} ball\n\nSotib olmoqchimisiz?", reply_markup=kb.adjust(1).as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy_course(call: types.CallbackQuery):
    data_parts = call.data.split("_")
    if not data_parts[1].isdigit(): return

    cid = int(data_parts[1])
    uid = call.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        course = await (await db.execute("SELECT * FROM courses WHERE id = ?", (cid,))).fetchone()
        user = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        if not course:
            return await call.answer("Kurs topilmadi!")

        final_price = course['price']
        if user['is_vip']: final_price = int(final_price * 0.5)

        purchased = await (await db.execute("SELECT * FROM purchases WHERE user_id = ? AND course_id = ?", (uid, cid))).fetchone()
        
        if purchased:
            await call.answer("Sizda bu kurs bor!", show_alert=True)
            return await send_course_file(uid, course['file_id'], course.get('file_type', 'document'), f"📘 {course['title']}")

        if user['balance'] >= final_price:
            await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (final_price, uid))
            await db.execute("INSERT INTO purchases VALUES (?, ?)", (uid, cid))
            await db.commit()
            await call.message.delete()
            await bot.send_message(uid, f"🎉 Muvaffaqiyatli sotib olindi!")
            await send_course_file(uid, course['file_id'], course.get('file_type', 'document'), f"📘 {course['title']}")
        else:
            await call.answer("❌ Ball yetarli emas!", show_alert=True)

@dp.callback_query(F.data == "vip_pay")
async def buy_vip_process(call: types.CallbackQuery):
    uid = call.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        user = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))).fetchone()
        
        if user['is_vip']:
            return await call.answer("Sizda allaqachon VIP bor!", show_alert=True)
        
        if user['balance'] >= config.VIP_PRICE:
            await db.execute("UPDATE users SET balance = balance - ?, is_vip = 1 WHERE user_id = ?", (config.VIP_PRICE, uid))
            await db.commit()
            await call.message.edit_text(f"🌟 VIP Faollashtirildi!", reply_markup=main_menu_kb(True))
        else:
            await call.answer(f"❌ Ball yetarli emas! VIP narxi: {config.VIP_PRICE}", show_alert=True)

# --- ADMIN PANEL ---
@dp.message(Command("admin"), F.from_user.id.in_(config.ADMIN_IDS))
async def admin_cmd(message: types.Message):
    await message.answer("🛠 **Admin Panelga xush kelibsiz**", reply_markup=admin_menu_kb())

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
    await message.answer("📁 Kurs faylini yuboring (Video, Fayl yoki Rasm):")

# TUG'IRLANGAN QISMI: Barcha turdagi mediani qabul qiladi
@dp.message(AdminStates.c_content)
async def adm_c_f(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = None
    file_type = "document"

    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    
    if not file_id:
        return await message.answer("❌ Iltimos, kurs kontenti sifatida fayl yoki video yuboring!")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO courses (title, price, file_id, file_type) VALUES (?, ?, ?, ?)", 
                         (data['ct'], data['cp'], file_id, file_type))
        await db.commit()
    
    await message.answer(f"✅ Kurs muvaffaqiyatli qo'shildi!\n📌 Nomi: {data['ct']}")
    await state.clear()

# --- QOLGAN ADMIN HANDLERLARI (O'ZGARISHSIZ) ---

@dp.callback_query(F.data == "adm_stat")
async def admin_stat(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        users = (await (await db.execute("SELECT count(*) FROM users")).fetchone())[0]
        courses = (await (await db.execute("SELECT count(*) FROM courses")).fetchone())[0]
        purchases = (await (await db.execute("SELECT count(*) FROM purchases")).fetchone())[0]
        await call.message.answer(f"📊 **Statistika**\n\n👤 Foydalanuvchilar: {users}\n📚 Kurslar: {courses}\n🛒 Jami savdolar: {purchases}")

@dp.callback_query(F.data == "adm_bc")
async def adm_bc_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast)
    await call.message.answer("📢 Reklama xabarini yuboring:")

@dp.message(AdminStates.broadcast)
async def adm_bc_send(message: types.Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        users = await (await db.execute("SELECT user_id FROM users")).fetchall()
        count = 0
        for u in users:
            try:
                await message.copy_to(u[0])
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yuborildi.")

@dp.callback_query(F.data == "adm_del_course")
async def adm_c_del_list(call: types.CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        courses = await (await db.execute("SELECT * FROM courses")).fetchall()
        kb = InlineKeyboardBuilder()
        for c in courses:
            kb.button(text=f"❌ {c['title']}", callback_data=f"delc_{c['id']}")
        await call.message.edit_text("O'chirish uchun kursni tanlang:", reply_markup=kb.adjust(1).as_markup())

@dp.callback_query(F.data.startswith("delc_"))
async def adm_c_del_res(call: types.CallbackQuery):
    cid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM courses WHERE id = ?", (cid,))
        await db.commit()
    await call.answer("Kurs o'chirildi!")
    await adm_c_del_list(call)

@dp.callback_query(F.data == "adm_ch_list")
async def adm_ch_manage(call: types.CallbackQuery, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        chs = await (await db.execute("SELECT * FROM channels")).fetchall()
        text = "📡 **Kanallar ro'yxati:**\n\n"
        kb = InlineKeyboardBuilder()
        for c in chs:
            text += f"🔹 {c['channel_id']}\n"
            kb.button(text=f"❌ {c['channel_id']}", callback_data=f"delch_{c['channel_id']}")
        kb.button(text="➕ Kanal Qo'shish", callback_data="adm_add_ch")
        await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.adjust(1).as_markup())

@dp.callback_query(F.data == "adm_add_ch")
async def adm_ch_a(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.add_ch_id)
    await call.message.answer("Kanal ID (masalan: -100...):")

@dp.message(AdminStates.add_ch_id)
async def adm_ch_id(message: types.Message, state: FSMContext):
    await state.update_data(chid=message.text)
    await state.set_state(AdminStates.add_ch_url)
    await message.answer("Kanal linkini kiriting:")

@dp.message(AdminStates.add_ch_url)
async def adm_ch_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (data['chid'], message.text))
        await db.commit()
    await message.answer("✅ Kanal qo'shildi!")
    await state.clear()

@dp.callback_query(F.data.startswith("delch_"))
async def adm_ch_del(call: types.CallbackQuery):
    chid = call.data.split("_")[1]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (chid,))
        await db.commit()
    await call.answer("Kanal o'chirildi!")
    await adm_ch_manage(call, None)

@dp.callback_query(F.data == "back_home")
async def back_home(call: types.CallbackQuery, state: FSMContext):
    await start_cmd(call.message, state)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
