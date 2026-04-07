import aiosqlite

DB_PATH = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            referred_by INTEGER,
            referral_count INTEGER DEFAULT 0,
            is_vip BOOLEAN DEFAULT 0
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            price INTEGER,
            content_id TEXT,
            content_type TEXT,
            is_vip_only BOOLEAN DEFAULT 0
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS purchases (
            user_id INTEGER,
            course_id INTEGER
        )''')
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def add_user(user_id, referrer_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referrer_id))
        if referrer_id:
            await db.execute("UPDATE users SET balance = balance + 10, referral_count = referral_count + 1 WHERE user_id = ?", (referrer_id,))
        await db.commit()

async def get_top_referrers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, referral_count FROM users ORDER BY referral_count DESC LIMIT 3") as cursor:
            return await cursor.fetchall()
