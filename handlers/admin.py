"""
Обработчики для администрирования (админ панель, рассылки)
"""
import re
from html import unescape
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest, NetworkError
from core.database import db
from core.models import AdminBroadcastState, BroadcastResult
from core.config import ADMIN_CHAT_IDS

# Глобальный словарь для хранения состояний админов при создании рассылки
admin_broadcast_states = {}


def _plain_preview(html_text: str, max_length: int = 100) -> str:
    """HTML → plain text для превью подтверждения рассылки."""
    plain = unescape(re.sub(r"<[^>]+>", "", html_text or ""))
    if len(plain) <= max_length:
        return plain
    return plain[:max_length] + "..."


def is_admin(chat_id: str) -> bool:
    """Проверка, является ли пользователь администратором"""
    # Преобразуем chat_id в строку для корректного сравнения
    chat_id_str = str(chat_id)
    
    # Отладочная информация
    print(f"🔍 Проверка админки для chat_id: {chat_id_str}")
    print(f"🔍 Доступные админские ID: {ADMIN_CHAT_IDS}")
    print(f"🔍 Результат проверки: {chat_id_str in ADMIN_CHAT_IDS}")
    
    return chat_id_str in ADMIN_CHAT_IDS


async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда открытия админ панели"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    print(f"🔧 Попытка доступа к админ панели от chat_id: {chat_id}")
    print(f"🔧 Пользователь: {user.first_name} {user.last_name} (@{user.username})")
    
    if not is_admin(chat_id):
        print(f"❌ Отказано в доступе для chat_id: {chat_id}")
        await update.message.reply_text("❌ У вас нет доступа к админ панели.")
        return
    
    print(f"✅ Доступ разрешен для chat_id: {chat_id}")
    
    # Получаем статистику
    all_users = db.get_all_users()
    total_users = len(all_users)
    
    keyboard = [
        [InlineKeyboardButton("📢 Массовая рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")]
    ]
    
    await update.message.reply_text(
        f"🔧 *Админ панель*\n\n"
        f"👥 Всего пользователей: {total_users}\n\n"
        f"Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания рассылки"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    if not is_admin(chat_id):
        await query.answer("❌ У вас нет доступа к этой функции.")
        return
    
    # Инициализируем состояние рассылки
    admin_broadcast_states[chat_id] = AdminBroadcastState()
    
    await query.edit_message_text(
        "📢 *Массовая рассылка*\n\n"
        "Отправьте сообщение, которое хотите разослать всем пользователям.\n"
        "Поддерживаются: текст, фото, видео, документы, аудио, голосовые, стикеры.\n\n"
        "Для отмены используйте команду /cancel",
        parse_mode='Markdown'
    )


async def handle_admin_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка контента для рассылки"""
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in admin_broadcast_states:
        return
    
    state = admin_broadcast_states[chat_id]
    
    if state.step == "waiting_content":
        # Сохраняем контент сообщения
        message = update.message
        
        # Сохраняем HTML-версию текста/подписи, чтобы сохранить bold/italic и text_link
        if message.text:
            state.content = message.text_html
            state.media_type = None
        elif message.photo:
            state.media_type = "photo"
            state.media_file_id = message.photo[-1].file_id
            state.caption = message.caption_html
        elif message.video:
            state.media_type = "video"
            state.media_file_id = message.video.file_id
            state.caption = message.caption_html
        elif message.document:
            state.media_type = "document"
            state.media_file_id = message.document.file_id
            state.caption = message.caption_html
        elif message.audio:
            state.media_type = "audio"
            state.media_file_id = message.audio.file_id
            state.caption = message.caption_html
        elif message.voice:
            state.media_type = "voice"
            state.media_file_id = message.voice.file_id
        elif message.sticker:
            state.media_type = "sticker"
            state.media_file_id = message.sticker.file_id
        else:
            await message.reply_text("❌ Неподдерживаемый тип сообщения.")
            return
        
        # Переходим к подтверждению
        state.step = "confirming"
        await handle_admin_broadcast_confirmation(update, context)


async def handle_admin_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение рассылки"""
    chat_id = str(update.effective_chat.id)
    state = admin_broadcast_states[chat_id]
    
    # Получаем количество пользователей
    all_users = db.get_all_users()
    user_count = len(all_users)
    
    # Формируем превью сообщения (plain text — без HTML-тегов)
    preview = ""
    if state.content:
        preview = f"📝 Текст: {_plain_preview(state.content)}"
    elif state.media_type:
        preview = f"📎 {state.media_type.upper()}"
        if state.caption:
            preview += f"\n📝 Подпись: {_plain_preview(state.caption)}"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Отправить", callback_data="broadcast_confirm_yes"),
            InlineKeyboardButton("❌ Отмена", callback_data="broadcast_confirm_no")
        ]
    ]
    
    await update.message.reply_text(
        f"📢 Подтверждение рассылки\n\n"
        f"👥 Получателей: {user_count} пользователей\n\n"
        f"📋 Превью:\n{preview}\n\n"
        f"Точно отправить?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_broadcast_confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение рассылки"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in admin_broadcast_states:
        await query.answer("❌ Состояние рассылки не найдено.")
        return
    
    state = admin_broadcast_states[chat_id]
    
    # Получаем всех пользователей
    all_users = db.get_all_users()
    
    await query.edit_message_text(
        f"📢 *Рассылка запущена*\n\n"
        f"📊 Отправляю сообщение {len(all_users)} пользователям...",
        parse_mode='Markdown'
    )
    
    # Выполняем рассылку
    result = await send_broadcast_message_content(context, all_users, state)
    
    # Очищаем состояние
    del admin_broadcast_states[chat_id]
    
    # Отправляем отчет
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"📢 *Рассылка завершена*\n\n"
            f"✅ Успешно отправлено: {result.total_sent}\n"
            f"❌ Ошибки отправки: {result.total_failed}\n"
            f"🚫 Заблокировали бота: {len(result.forbidden)}\n"
            f"📊 Успешность: {result.success_rate:.1f}%"
        ),
        parse_mode='Markdown'
    )


async def handle_broadcast_confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена рассылки"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    # Очищаем состояние
    if chat_id in admin_broadcast_states:
        del admin_broadcast_states[chat_id]
    
    await query.edit_message_text("❌ Рассылка отменена.")


async def send_broadcast_message_content(context, users, state: AdminBroadcastState) -> BroadcastResult:
    """Отправка контента рассылки пользователям"""
    result = BroadcastResult()
    parse_mode = state.parse_mode or "HTML"
    
    for user_chat_id in users:
        try:
            if state.content:
                # Текстовое сообщение (HTML сохраняет форматирование и text_link)
                await context.bot.send_message(
                    chat_id=user_chat_id,
                    text=state.content,
                    parse_mode=parse_mode
                )
            elif state.media_type == "photo":
                await context.bot.send_photo(
                    chat_id=user_chat_id,
                    photo=state.media_file_id,
                    caption=state.caption,
                    parse_mode=parse_mode if state.caption else None
                )
            elif state.media_type == "video":
                await context.bot.send_video(
                    chat_id=user_chat_id,
                    video=state.media_file_id,
                    caption=state.caption,
                    parse_mode=parse_mode if state.caption else None
                )
            elif state.media_type == "document":
                await context.bot.send_document(
                    chat_id=user_chat_id,
                    document=state.media_file_id,
                    caption=state.caption,
                    parse_mode=parse_mode if state.caption else None
                )
            elif state.media_type == "audio":
                await context.bot.send_audio(
                    chat_id=user_chat_id,
                    audio=state.media_file_id,
                    caption=state.caption,
                    parse_mode=parse_mode if state.caption else None
                )
            elif state.media_type == "voice":
                await context.bot.send_voice(
                    chat_id=user_chat_id,
                    voice=state.media_file_id
                )
            elif state.media_type == "sticker":
                await context.bot.send_sticker(
                    chat_id=user_chat_id,
                    sticker=state.media_file_id
                )
            
            result.successful.append(user_chat_id)
            
        except Forbidden:
            result.forbidden.append(user_chat_id)
        except (BadRequest, NetworkError, Exception) as e:
            result.failed.append(user_chat_id)
            print(f"❌ Ошибка отправки пользователю {user_chat_id}: {e}")
    
    return result


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда отмены текущего действия"""
    chat_id = str(update.effective_chat.id)
    
    if chat_id in admin_broadcast_states:
        del admin_broadcast_states[chat_id]
        await update.message.reply_text("❌ Создание рассылки отменено.")
    else:
        await update.message.reply_text("Нет активных действий для отмены.")


async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Обработка админских callback'ов"""
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    
    if not is_admin(chat_id):
        await query.answer("❌ У вас нет доступа к этой функции.")
        return
    
    if callback_data == "admin_broadcast":
        await admin_broadcast_callback(update, context)
    
    elif callback_data == "admin_stats":
        await show_admin_stats(update, context)
    
    elif callback_data == "admin_users":
        await show_admin_users(update, context)
    
    elif callback_data == "broadcast_confirm_yes":
        await handle_broadcast_confirm_yes(update, context)
    
    elif callback_data == "broadcast_confirm_no":
        await handle_broadcast_confirm_no(update, context)


async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику для админа"""
    query = update.callback_query
    
    # Получаем детальную статистику
    stats = db.get_user_stats_summary()
    
    await query.edit_message_text(
        f"📊 *Статистика бота*\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📈 Активных сегодня: {stats['active_today']}\n"
        f"📅 Активных за неделю: {stats['active_week']}\n\n"
        f"📝 Всего сообщений: {stats['total_messages']}\n"
        f"🎤 Голосовых сообщений: {stats['total_audio']}\n"
        f"💾 Снов сохранено: {stats['total_dreams_saved']}\n\n"
        f"💬 Среднее сообщений на пользователя: {stats['total_messages'] // max(stats['total_users'], 1)}\n"
        f"🌙 Средне снов на пользователя: {stats['total_dreams_saved'] // max(stats['total_users'], 1)}",
        parse_mode='Markdown'
    )


async def show_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список пользователей с детальной статистикой"""
    query = update.callback_query
    
    # Получаем детальную статистику по пользователям
    user_details = db.get_user_stats_details(limit=10)
    
    if not user_details:
        await query.edit_message_text(
            "👥 *Пользователи бота*\n\nПользователей не найдено.",
            parse_mode='Markdown'
        )
        return
    
    users_text = "👥 *Топ активных пользователей*\n\n"
    
    for i, (chat_id, username, messages, audio, dreams, last_activity, _) in enumerate(user_details, 1):
        # Форматируем время последней активности
        if last_activity:
            from datetime import datetime, timezone
            time_diff = datetime.now(timezone.utc) - last_activity
            if time_diff.days > 0:
                activity_str = f"{time_diff.days}д назад"
            elif time_diff.seconds > 3600:
                activity_str = f"{time_diff.seconds // 3600}ч назад"
            else:
                activity_str = "недавно"
        else:
            activity_str = "неизвестно"
        
        username_str = username or "без имени"
        users_text += (
            f"{i}. {username_str}\n"
            f"   💬 {messages or 0} сообщений, 🎤 {audio or 0} голосовых\n"
            f"   💾 {dreams or 0} снов, активность: {activity_str}\n\n"
        )
    
    total_users = len(db.get_all_users())
    users_text += f"📊 Всего пользователей: {total_users}"
    
    await query.edit_message_text(
        users_text,
        parse_mode='Markdown'
    )
