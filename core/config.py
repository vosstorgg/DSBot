"""
Конфигурация и константы для Dream Analysis Bot
"""
import os
from telegram import ReplyKeyboardMarkup

# === API КОНФИГУРАЦИЯ ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SECRET_TOKEN = os.getenv("SECRET_TOKEN", "default_secret")

# === DATABASE КОНФИГУРАЦИЯ ===
DATABASE_CONFIG = {
    "host": os.getenv("PGHOST"),
    "port": os.getenv("PGPORT"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
    "dbname": os.getenv("PGDATABASE")
}

# === AI МОДЕЛЬ НАСТРОЙКИ ===
AI_SETTINGS = {
    "model": "gpt-4o",
    "temperature": 0.45,
    "max_tokens": 1400,
    "max_history": 10
}

# === ПУТИ К ФАЙЛАМ ===
STATIC_DIR = "static"
IMAGE_PATHS = {
    "intro": f"{STATIC_DIR}/intro.png",
    "about": f"{STATIC_DIR}/about.png", 
    "donate": f"{STATIC_DIR}/donate.png",
    "quiz": f"{STATIC_DIR}/quiz.png",
    "diary": f"{STATIC_DIR}/diary.png"
}

# === ПРОМПТ ДЛЯ AI ===
DEFAULT_SYSTEM_PROMPT = (
    "#Role You are a qualified Jungian dream analyst with knowledge of astrology and esotericism. "
    "Interpret dreams as unique messages from the unconscious. Use simple clear language; Telegram Markdown and emojis. "
    "Output in Russian, informal ty. "
    "#Classification (STRICT): Begin reply with one of: 🌙 (only when user described a DREAM - something they saw while sleeping); 💭 (when NOT a dream: greeting, question about bot, general chat - answer briefly, invite to share a dream, never interpret as dream); ❓ (only for follow-up about a previous interpretation). When in doubt use 💭. "
    "#Task (when dream): Identify key images, archetypes, symbols; explain significance. If dream is brief, ask 1-3 clarifying questions. "
    "#Reply handling: For clarification questions give thorough warm answer. Maintain friendly tone."
)

# Промпт для ответа на сообщения, которые не являются описанием сна
GENERAL_RESPONSE_PROMPT = """Ты — дружелюбный бот-толкователь снов. Пользователь написал сообщение, которое НЕ является описанием сна (приветствие, вопрос о тебе, общий разговор). Ответь кратко и по-дружески. Начни с 💭. Не интерпретируй как сон. Пригласи рассказать сон, когда захочет. Русский, на «ты»."""

# === TELEGRAM МЕНЮ ===
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        ["🌙 Разобрать мой сон"],
        ["📖 Дневник снов", "💎 Донат на развитие"]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# === ADMIN КОНФИГУРАЦИЯ ===
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
if not ADMIN_CHAT_ID:
    print("⚠️ ВНИМАНИЕ: ADMIN_CHAT_ID не установлен в переменных окружения!")
    print("⚠️ Админские функции будут недоступны!")

ADMIN_CHAT_IDS = [ADMIN_CHAT_ID] if ADMIN_CHAT_ID else []

# === WHISPER НАСТРОЙКИ ===
WHISPER_SETTINGS = {
    "min_duration": 1,  # Уменьшаем минимальную длительность с 2 до 1 секунды
    "max_duration_for_phrase_filter": 3,  # Уменьшаем с 5 до 3 секунд для более мягкой фильтрации
    "suspicious_phrases": [
        # YouTube/видео артефакты (оставляем только самые явные)
        "редактор субтитров", "подписывайтесь на канал", "ставьте лайки", "всем пока",
        "спасибо за просмотр", "до свидания", "увидимся", "пока пока",
        
        # Музыкальные артефакты (убираем общие слова)
        "♪", "♫", "♬", "бит", "бас", "мелодия",
        
        # Технические тесты (оставляем только явные)
        "проверка связи", "тестирование", "один два три",
        
        # Междометия (убираем естественные для речи)
        "эм", "ммм", "хмм", "ага", "угу", "да да", "нет нет",
        "ой", "ах", "ох", "эх", "ух", "блин",
        
        # Новости и медиа (убираем общие слова)
        "новости", "сводка", "прогноз", "погода", "курс валют",
        "последние новости", "в эфире", "передача",
        
        # Имена и бренды (оставляем только явные)
        "субтитры", "ютуб", "youtube", "telegram", "whatsapp",
        "вконтакте", "фейсбук", "инстаграм", "тикток",
        
        # Соцсети и мессенджеры (оставляем только явные)
        "лайк", "репост", "шэр", "subscribe", "follow",
        "комментарий", "сториз", "селфи"
    ]
}

# === ПАГИНАЦИЯ ===
PAGINATION = {
    "dreams_per_page": 10,
    "max_message_length": 4000
}

# === ССЫЛКИ ===
LINKS = {
    "donation": "https://pay.cloudtips.ru/p/4f1dd4bf"
}
