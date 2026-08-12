"""
Обработчики для астрологического толкования снов
"""
import logging
from datetime import datetime, timezone, timedelta
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest

from core.utils import cleanup_astrological_interface, cleanup_astrological_interface_by_ids, remove_message_buttons_by_id, log_error_and_notify

logger = logging.getLogger(__name__)

MAX_TELEGRAM_MESSAGE_LEN = 4000


def _truncate_for_telegram(text: str, reserve: int = 120) -> str:
    """Ограничивает длину текста под лимит Telegram."""
    if not text:
        return text
    limit = max(1000, MAX_TELEGRAM_MESSAGE_LEN - reserve)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


async def _safe_answer_callback(query, text: str):
    """Безопасный ответ на callback: игнорирует протухший query."""
    try:
        await query.answer(text)
    except BadRequest as e:
        err = str(e)
        if "Query is too old" in err or "query id is invalid" in err:
            logger.info("Callback query expired before answer")
            return
        raise


async def _safe_edit_markdown(message, text: str, reply_markup=None):
    """Редактирует сообщение с fallback для длинных/сломанных markdown ответов."""
    try:
        return await message.edit_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    except BadRequest as e:
        err = str(e)
        if "Message_too_long" in err:
            shortened = _truncate_for_telegram(text)
            try:
                return await message.edit_text(shortened, parse_mode='Markdown', reply_markup=reply_markup)
            except BadRequest:
                return await message.edit_text(shortened, reply_markup=reply_markup)
        if "Can't parse entities" in err:
            try:
                return await message.edit_text(text, reply_markup=reply_markup)
            except BadRequest as e2:
                if "Message_too_long" in str(e2):
                    shortened = _truncate_for_telegram(text)
                    return await message.edit_text(shortened, reply_markup=reply_markup)
        raise


async def handle_astrological_callback(update, context, callback_data):
    """Обработчик кнопки 'Астрологическое толкование'"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Получаем данные сна из временного хранилища в БД
        from core.database import db
        pending_dream = db.get_pending_dream(chat_id)
        if not pending_dream:
            await _safe_answer_callback(query, "❌ Данные сна не найдены. Попробуйте еще раз.")
            return
        
        # Извлекаем source_type из callback_data
        source_type = callback_data.split(":")[1]
        logger.info(f"🔍 DEBUG: handle_astrological_callback - callback_data = {callback_data}, source_type = {source_type}")
        
        # Показываем уточнение даты
        await _safe_answer_callback(query, "🔮 Уточняю дату сна...")
        
        # Отправляем сообщение с выбором даты
        date_msg = await query.message.reply_text(
            "Когда тебе приснился этот сон?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Сегодня", callback_data=f"astrological_date:today:{source_type}")],
                [InlineKeyboardButton("Вчера", callback_data=f"astrological_date:yesterday:{source_type}")],
                [InlineKeyboardButton("Ввести дату", callback_data=f"astrological_date:custom:{source_type}")]
            ])
        )
        
        # Сохраняем ID сообщений для последующего удаления
        context.user_data['date_selection_msg_id'] = date_msg.message_id
        # Используем ID сообщения с толкованием из предыдущего шага
        original_message_id = context.user_data.get('dream_interpretation_msg_id', query.message.message_id)
        context.user_data['original_message_id'] = original_message_id
        
    except Exception as e:
        await _safe_answer_callback(query, "❌ Произошла ошибка при выборе даты.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_date_error", str(e))


async def handle_astrological_date_callback(update, context, callback_data):
    """Обработчик выбора даты для астрологического толкования"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Парсим callback_data: astrological_date:date_type:source_type
        parts = callback_data.split(":")
        date_type = parts[1]
        source_type = parts[2]
        
        # Получаем данные сна из временного хранилища в БД
        from core.database import db
        pending_dream = db.get_pending_dream(chat_id)
        if not pending_dream:
            await _safe_answer_callback(query, "❌ Данные сна не найдены. Попробуйте еще раз.")
            return
        
        # Определяем дату в зависимости от выбора
        today = datetime.now(timezone.utc)
        
        if date_type == "today":
            selected_date = today
            date_str = today.strftime("%Y-%m-%d")
        elif date_type == "yesterday":
            selected_date = today - timedelta(days=1)
            date_str = selected_date.strftime("%Y-%m-%d")
        elif date_type == "custom":
            # Запрашиваем ввод даты
            await _safe_answer_callback(query, "Введи дату в формате ДД.ММ.ГГГГ")
            
            # Устанавливаем состояние ожидания даты
            context.user_data['waiting_for_date'] = True
            context.user_data['pending_astrological'] = {
                'source_type': source_type,
                'pending_dream': pending_dream
            }
            
            # Редактируем сообщение с инструкцией
            await query.message.edit_text(
                "Введи дату в формате ДД.ММ.ГГГГ\n\nНапример: 15.01.2024",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Отмена", callback_data="cancel_date_input")]
                ])
            )
            return
        else:
            await _safe_answer_callback(query, "❌ Неизвестный тип даты.")
            return
        
        # Запускаем астрологический анализ с выбранной датой
        await perform_astrological_analysis(update, context, pending_dream, source_type, date_str)
        
    except Exception as e:
        await _safe_answer_callback(query, "❌ Произошла ошибка при выборе даты.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_date_error", str(e))


async def perform_astrological_analysis(update, context, pending_dream, source_type, date_str):
    """Выполнение астрологического анализа с указанной датой"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Показываем "размышляет"
        await _safe_answer_callback(query, "🔮 Анализирую сон астрологически...")
        
        # Отправляем сообщение о начале астрологического анализа
        thinking_msg = await query.message.reply_text("🔮 Размышляю над астрологическим значением твоего сна...")
        
        # Получаем астрологическое толкование с датой
        from core.ai_service import ai_service
        astrological_reply = await ai_service.analyze_dream_astrologically(
            pending_dream['dream_text'], 
            pending_dream['interpretation'],
            source_type,
            date_str
        )
        
        # Логируем астрологическое толкование
        from core.database import db
        db.log_activity(user, chat_id, "astrological_interpretation", f"date:{date_str}, reply:{astrological_reply[:300]}")
        db.save_message(chat_id, "assistant", astrological_reply)
        
        # Определяем тип ответа для создания соответствующей клавиатуры
        message_type = ai_service.extract_message_type(astrological_reply)
        
        if message_type == 'dream':
            # Для астрологических толкований добавляем кнопку "Сохранить в дневник"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Сохранить в дневник снов", callback_data=f"save_dream:{source_type}")],
                [InlineKeyboardButton("💬 Уточнить детали", callback_data=f"clarify_details:{source_type}")]
            ])
            
            # Обновляем временные данные для астрологического толкования
            # Сохраняем ОБА толкования: обычное и астрологическое
            db.update_pending_dream_astrological(chat_id, astrological_reply)
            logger.info(f"🔍 DEBUG: perform_astrological_analysis - обновлен pending_dream в БД")
            
            # Убираем кнопки из обычного толкования и удаляем сообщение с выбором даты
            original_message_id = context.user_data.get('original_message_id')
            date_message_id = context.user_data.get('date_selection_msg_id')
            
            if original_message_id or date_message_id:
                # Используем надежный метод с ID сообщений
                await cleanup_astrological_interface_by_ids(context, chat_id, original_message_id, date_message_id)
            else:
                # Fallback к старому методу
                await cleanup_astrological_interface(context, chat_id, astrological_reply)
            
            # Очищаем ID сообщения с выбором даты, но оставляем ID оригинального толкования для кнопки сохранения
            context.user_data.pop('date_selection_msg_id', None)
                
        else:
            # Для других типов сообщений без кнопок
            keyboard = None
        
        # Отправляем астрологическое толкование
        if keyboard:
            await _safe_edit_markdown(thinking_msg, astrological_reply, reply_markup=keyboard)
        else:
            await _safe_edit_markdown(thinking_msg, astrological_reply)
        
    except Exception as e:
        await _safe_answer_callback(query, "❌ Произошла ошибка при астрологическом анализе.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_error", str(e))
        if 'thinking_msg' in locals():
            await thinking_msg.edit_text("❌ Не получилось сделать толкование, попробуй немного позже")


async def perform_astrological_analysis_from_date_input(update, context, pending_dream, source_type, date_str):
    """Выполнение астрологического анализа с введенной датой"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    try:
        # Показываем "размышляет"
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        thinking_msg = await update.message.reply_text("🔮 Размышляю над астрологическим значением твоего сна...")
        
        # Получаем астрологическое толкование с датой
        from core.ai_service import ai_service
        astrological_reply = await ai_service.analyze_dream_astrologically(
            pending_dream['dream_text'], 
            pending_dream['interpretation'],
            source_type,
            date_str
        )
        
        # Логируем астрологическое толкование
        from core.database import db
        db.log_activity(user, chat_id, "astrological_interpretation", f"date:{date_str}, reply:{astrological_reply[:300]}")
        db.save_message(chat_id, "assistant", astrological_reply)
        
        # Определяем тип ответа для создания соответствующей клавиатуры
        message_type = ai_service.extract_message_type(astrological_reply)
        
        if message_type == 'dream':
            # Для астрологических толкований добавляем кнопку "Сохранить в дневник"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Сохранить в дневник снов", callback_data=f"save_dream:{source_type}")],
                [InlineKeyboardButton("💬 Уточнить детали", callback_data=f"clarify_details:{source_type}")]
            ])
            
            # Обновляем временные данные для астрологического толкования
            # Сохраняем ОБА толкования: обычное и астрологическое
            db.update_pending_dream_astrological(chat_id, astrological_reply)
            
            # Убираем кнопки из исходного сообщения с толкованием и удаляем сообщение с выбором даты
            original_message_id = context.user_data.get('original_message_id')
            date_message_id = context.user_data.get('date_selection_msg_id')
            
            if original_message_id or date_message_id:
                # Используем надежный метод с ID сообщений
                await cleanup_astrological_interface_by_ids(context, chat_id, original_message_id, date_message_id)
            else:
                # Fallback к старому методу
                await cleanup_astrological_interface(context, chat_id, astrological_reply)
            
            # Очищаем ID сообщения с выбором даты, но оставляем ID оригинального толкования для кнопки сохранения
            context.user_data.pop('date_selection_msg_id', None)
            
        else:
            # Для других типов сообщений без кнопок
            keyboard = None
        
        # Отправляем астрологическое толкование
        if keyboard:
            await _safe_edit_markdown(thinking_msg, astrological_reply, reply_markup=keyboard)
        else:
            await _safe_edit_markdown(thinking_msg, astrological_reply)
        
    except Exception as e:
        from core.database import db
        log_error_and_notify(db, user, chat_id, "astrological_error", str(e))
        await thinking_msg.edit_text("❌ Не получилось сделать толкование, попробуй немного позже")


async def handle_cancel_date_input(update, context):
    """Обработчик отмены ввода даты"""
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = update.effective_user
    
    try:
        # Очищаем состояние ожидания даты
        context.user_data.pop('waiting_for_date', None)
        context.user_data.pop('pending_astrological', None)
        
        # Показываем сообщение об отмене
        await _safe_answer_callback(query, "❌ Ввод даты отменен")
        
        # Удаляем сообщение с вводом даты
        await query.message.delete()
        
    except Exception as e:
        await _safe_answer_callback(query, "❌ Ошибка при отмене ввода даты")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "cancel_date_error", str(e))


def is_valid_date_format(date_str):
    """Проверка корректности формата даты ДД.ММ.ГГГГ"""
    try:
        # Проверяем формат
        if not date_str or len(date_str) != 10 or date_str[2] != '.' or date_str[5] != '.':
            return False
        
        # Извлекаем части даты
        day = int(date_str[0:2])
        month = int(date_str[3:5])
        year = int(date_str[6:10])
        
        # Проверяем разумные пределы
        if year < 1900 or year > 2100:
            return False
        if month < 1 or month > 12:
            return False
        if day < 1 or day > 31:
            return False
        
        # Проверяем корректность дней для месяца
        try:
            datetime(year, month, day)
            return True
        except ValueError:
            return False
            
    except (ValueError, IndexError):
        return False


def convert_date_format(date_str):
    """Конвертация даты из ДД.ММ.ГГГГ в YYYY-MM-DD"""
    day = date_str[0:2]
    month = date_str[3:5]
    year = date_str[6:10]
    return f"{year}-{month}-{day}"


async def handle_date_input(update, context):
    """Обработчик ввода даты для астрологического толкования"""
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    try:
        # Получаем введенную дату
        date_input = update.message.text.strip()
        
        # Валидируем формат даты ДД.ММ.ГГГГ
        if not is_valid_date_format(date_input):
            await update.message.reply_text(
                "❌ Неверный формат даты. Используй формат ДД.ММ.ГГГГ\n\nНапример: 15.01.2024",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Отмена", callback_data="cancel_date_input")]
                ])
            )
            return
        
        # Конвертируем дату в нужный формат
        date_str = convert_date_format(date_input)
        
        # Получаем данные для астрологического анализа
        pending_astrological = context.user_data.get('pending_astrological')
        if not pending_astrological:
            await update.message.reply_text("❌ Данные для астрологического анализа не найдены.")
            return
        
        # Очищаем состояние ожидания даты
        context.user_data.pop('waiting_for_date', None)
        pending_data = context.user_data.pop('pending_astrological')
        
        # Запускаем астрологический анализ с введенной датой
        await perform_astrological_analysis_from_date_input(
            update, context, 
            pending_data['pending_dream'], 
            pending_data['source_type'], 
            date_str
        )
        
    except Exception as e:
        await update.message.reply_text("❌ Произошла ошибка при обработке даты.")
        from core.database import db
        log_error_and_notify(db, user, chat_id, "date_input_error", str(e))
