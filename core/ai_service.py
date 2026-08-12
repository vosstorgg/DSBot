"""
Модуль для работы с OpenAI API (GPT-5.6 Terra / GPT-5.4 mini и Whisper)
"""
import os
import io
import tempfile
import logging
from openai import AsyncOpenAI
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from core.config import AI_SETTINGS, DEFAULT_SYSTEM_PROMPT, GENERAL_RESPONSE_PROMPT, WHISPER_SETTINGS

logger = logging.getLogger(__name__)
MARKER_PREFIXES = ("🌙", "💭", "❓", "🔮")


def _strip_trailing_smiley(text: str) -> str:
    """Убирает 😊 в конце ответа."""
    if not text:
        return text
    return text.rstrip().removesuffix(" 😊").removesuffix("😊").rstrip() or text


class AIService:
    """Сервис для работы с OpenAI API"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def build_prompt(self, profile_info: str = "") -> str:
        """Построение персонализированного промпта"""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = DEFAULT_SYSTEM_PROMPT
        prompt += f"\n\n# Current date\nToday is {today_str}."
        prompt += f"\n\n# Length limit\nYour full reply must be <= {AI_SETTINGS['max_reply_chars']} characters."
        
        if profile_info:
            prompt += f"\n\n# User context\n{profile_info.strip()}"
        
        return prompt

    async def _fit_reply_length(self, reply: str) -> str:
        """Укладывает ответ в лимит символов через переформулировку, без обрезки."""
        if not reply:
            return reply

        max_chars = AI_SETTINGS.get("max_reply_chars", 3200)
        if len(reply) <= max_chars:
            return reply

        forced_prefix = next((p for p in MARKER_PREFIXES if reply.startswith(p)), "")
        rewrite_system = (
            "You rewrite assistant messages in Russian for Telegram. "
            f"Return a message that is <= {max_chars} characters. "
            "Do not use markdown headings (#, ##, ###). Keep short paragraphs. "
            "Preserve core meaning and supportive tone. Do not mention that you shortened text."
        )
        prefix_rule = f"Start with exactly: {forced_prefix}" if forced_prefix else "Keep the existing start marker if present."

        try:
            rewrite = await self.client.chat.completions.create(
                model=AI_SETTINGS["response_model"],
                messages=[
                    {"role": "system", "content": rewrite_system},
                    {"role": "user", "content": f"{prefix_rule}\n\nText:\n{reply}"}
                ],
                max_completion_tokens=900
            )
            rewritten = _strip_trailing_smiley(rewrite.choices[0].message.content or "")
            if rewritten and len(rewritten) <= max_chars:
                return rewritten
        except Exception:
            logger.exception("Reply length fitting failed")

        return reply
    
    def format_profile_info(self, profile: Optional[Tuple]) -> str:
        """Форматирование информации профиля"""
        if not profile:
            return ""
        
        gender, age_group, lucid = profile
        profile_parts = []
        
        if gender:
            profile_parts.append(f"User gender: {gender}")
        if age_group:
            profile_parts.append(f"User age group: {age_group}")
        if lucid:
            profile_parts.append(f"Lucid dream experience: {lucid}")
        
        return ". ".join(profile_parts) + ("." if profile_parts else "")
    
    async def analyze_dream(self, dream_text: str, history: List[Dict], profile_info: str = "") -> str:
        """Анализ сна через GPT-5.6 Terra"""
        try:
            prompt = self.build_prompt(profile_info)
            
            # Добавляем дату сна в промпт (по умолчанию сегодня)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            dream_with_date = f"Сон от {today_str}:\n{dream_text}"
            
            response = await self.client.chat.completions.create(
                model=AI_SETTINGS["dream_model"],
                messages=[{"role": "system", "content": prompt}] + history + [{"role": "user", "content": dream_with_date}],
                max_completion_tokens=AI_SETTINGS["max_tokens"]
            )
            
            reply = _strip_trailing_smiley(response.choices[0].message.content or "")
            return await self._fit_reply_length(reply)
        except Exception as e:
            logger.exception("Dream analysis request failed")
            return "❌ Не получилось сделать толкование, попробуй немного позже"
    
    async def classify_message_intent(self, user_message: str, history: Optional[List[Dict]] = None) -> str:
        """Определяет тип сообщения: dream, not_dream или clarification (ответ на вопрос бота)."""
        if not user_message or len(user_message.strip()) < 3:
            return "not_dream"

        # Clarification только когда бот задал прямой вопрос (?) и ответ короткий — без маркеров слов
        if history:
            last_msg = history[-1] if history else None
            if last_msg and last_msg.get("role") == "assistant" and "?" in (last_msg.get("content") or ""):
                if len(user_message.strip()) < 300:
                    return "clarification"

        try:
            response = await self.client.chat.completions.create(
                model=AI_SETTINGS["response_model"],
                messages=[
                    {"role": "system", "content": "You classify user messages. Answer ONLY with one word: dream (user describes something they dreamed/saw in sleep) or not_dream (greeting, question about bot, general chat, thanks, or unclear). No other text."},
                    {"role": "user", "content": user_message.strip()[:800]}
                ],
                max_completion_tokens=10
            )
            text = (response.choices[0].message.content or "").strip().lower()
            return "dream" if text.startswith("dream") else "not_dream"
        except Exception:
            return "dream"  # при ошибке отправляем в толкование

    async def respond_general(self, user_message: str, history: List[Dict]) -> str:
        """Ответ на сообщение, которое не является описанием сна (приветствие, общий вопрос)."""
        try:
            messages = [{"role": "system", "content": GENERAL_RESPONSE_PROMPT}]
            if history:
                messages += history[-4:]  # последние 2 пары для контекста
            messages.append({"role": "user", "content": user_message})
            response = await self.client.chat.completions.create(
                model=AI_SETTINGS["response_model"],
                messages=messages,
                max_completion_tokens=400
            )
            reply = _strip_trailing_smiley(response.choices[0].message.content or "")
            if not reply.strip().startswith("💭"):
                reply = "💭 " + reply.lstrip()
            return await self._fit_reply_length(reply)
        except Exception as e:
            logger.exception("General response request failed")
            return f"💭 Привет! Когда захочешь — расскажи свой сон, и я помогу его понять. ❤️"

    async def analyze_clarification_question(self, question: str, clarification_prompt: str) -> str:
        """Анализ уточняющего вопроса через GPT-5.4 mini"""
        try:
            response = await self.client.chat.completions.create(
                model=AI_SETTINGS["response_model"],
                messages=[
                    {"role": "system", "content": clarification_prompt},
                    {"role": "user", "content": question}
                ],
                max_completion_tokens=AI_SETTINGS["max_tokens"]
            )
            
            reply = _strip_trailing_smiley(response.choices[0].message.content or "")
            return await self._fit_reply_length(reply)
        except Exception as e:
            logger.exception("Clarification request failed")
            return "❌ Не получилось сделать толкование, попробуй немного позже"
    
    async def analyze_dream_astrologically(self, dream_text: str, previous_interpretation: str, source_type: str, dream_date: str = None) -> str:
        """Астрологический анализ сна с сохранением контекста и тона"""
        try:
            # Создаем специальный промпт для астрологического анализа
            date_info = f"Дата сна: {dream_date}" if dream_date else "Дата сна: не указана"
            
            astrological_prompt = f"""PROMPT = "#Role You are a male experienced astrologer; use masculine forms (готов, рад). #Task Give ONLY an astrological analysis of the dream, without repeating or retelling any previous interpretation; {date_info} USER'S DREAM: {dream_text}; #Rules Start with 🔮 emoji and immediately begin astrological analysis; use astrological approach: planets, zodiac signs, houses, aspects; link dream symbols with astrological archetypes; if dream date is given, use it; be thorough and supportive; structure analysis with emojis; NO greetings or introductory phrases; #Length Keep full reply within {AI_SETTINGS['max_reply_chars']} characters; #Usercontext End by inviting reflection/response; write in Russian using informal 'ты'."""

            response = await self.client.chat.completions.create(
                model=AI_SETTINGS["dream_model"],
                messages=[
                    {"role": "system", "content": astrological_prompt},
                    {"role": "user", "content": f"Проанализируй мой сон астрологически: {dream_text}"}
                ],
                max_completion_tokens=AI_SETTINGS["max_tokens"]
            )
            reply = _strip_trailing_smiley(response.choices[0].message.content or "")
            return await self._fit_reply_length(reply)
        except Exception as e:
            logger.exception("Astrological analysis request failed")
            return "❌ Не получилось сделать толкование, попробуй немного позже"
    
    def extract_message_type(self, ai_response: str) -> str:
        """Извлечение типа сообщения из ответа AI"""
        if ai_response.startswith('🌙') or ai_response.startswith('🔮'):
            return 'dream'
        elif ai_response.startswith('❓'):
            return 'question'
        elif ai_response.startswith('💭'):
            return 'chat'
        else:
            return 'unknown'
    
    async def transcribe_voice(self, voice_file_content: bytes, file_extension: str = "ogg") -> Optional[str]:
        """Транскрипция голосового сообщения через Whisper"""
        temp_file_path = None
        
        try:
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
                temp_file.write(voice_file_content)
                temp_file_path = temp_file.name
            
            # Транскрибируем через Whisper с улучшенными настройками
            with open(temp_file_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ru",
                    # Добавляем параметры для лучшего распознавания
                    response_format="text",
                    temperature=0.2  # Немного снижаем температуру для более точного распознавания
                )
                
                return transcript.strip()
                
        except Exception as e:
            print(f"❌ Ошибка транскрипции: {e}")
            return None
            
        finally:
            # Удаляем временный файл
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
    
    def is_transcription_suspicious(self, transcribed_text: str, voice_duration: float) -> Tuple[bool, str]:
        """Проверка транскрипции на подозрительность (галлюцинации Whisper)"""
        if not transcribed_text:
            return True, "empty_text"
        
        text_lower = transcribed_text.lower()
        words = text_lower.split()
        
        # 1. Проверка на подозрительные фразы (только для явных случаев)
        suspicious_phrases = WHISPER_SETTINGS["suspicious_phrases"]
        for phrase in suspicious_phrases:
            if phrase.lower() in text_lower:
                # Для коротких аудио отклоняем сразу, для длинных - только явные случаи
                if voice_duration < 3 or phrase in ["редактор субтитров", "подписывайтесь на канал", "ставьте лайки"]:
                    return True, f"suspicious_phrase: {phrase}"
        
        # 2. Слишком мало слов для длинного аудио (смягчаем проверку)
        if voice_duration > 6 and len(words) < voice_duration / 3:  # Было /2, стало /3
            return True, f"too_short_text: {len(words)} words for {voice_duration}s"
        
        # 3. Только междометия (смягчаем - разрешаем больше междометий)
        interjections = {"ммм", "хмм", "эм", "ага", "угу", "ой", "ах", "ох", "эх", "ух"}
        if len(words) <= 2 and all(word in interjections for word in words) and voice_duration > 3:
            return True, "only_interjections"
        
        # 4. Повторяющиеся символы (смягчаем - разрешаем короткие)
        for word in words:
            if len(word) > 5 and len(set(word)) == 1:  # Было >3, стало >5
                return True, f"repetitive_chars: {word}"
        
        return False, ""
    
    def should_reject_voice_message(self, transcribed_text: str, voice_duration: float) -> Tuple[bool, str]:
        """Определение, следует ли отклонить голосовое сообщение"""
        
        # Фильтруем очень короткие сообщения (вероятно случайные)
        if voice_duration < WHISPER_SETTINGS["min_duration"]:
            return True, f"too_short_duration: {voice_duration}s"
        
        # Проверяем на подозрительность
        is_suspicious, reason = self.is_transcription_suspicious(transcribed_text, voice_duration)
        
        if is_suspicious:
            # Для коротких аудио и фразовых совпадений отклоняем сразу
            if voice_duration < WHISPER_SETTINGS["max_duration_for_phrase_filter"] or "suspicious_phrase" in reason:
                return True, reason
            # Для длинных аудио можем быть менее строгими с некоторыми типами ошибок
            elif "too_short_text" not in reason:
                return True, reason
        
        return False, ""
    
    def test_voice_settings(self, transcribed_text: str, voice_duration: float) -> Dict[str, any]:
        """Тестовая функция для проверки настроек распознавания голоса"""
        result = {
            "duration": voice_duration,
            "text": transcribed_text,
            "words_count": len(transcribed_text.split()) if transcribed_text else 0,
            "checks": {}
        }
        
        # Проверяем каждое условие отдельно
        if not transcribed_text:
            result["checks"]["empty_text"] = True
        else:
            result["checks"]["empty_text"] = False
            
            text_lower = transcribed_text.lower()
            words = text_lower.split()
            
            # Проверка на подозрительные фразы
            suspicious_phrases = WHISPER_SETTINGS["suspicious_phrases"]
            found_suspicious = []
            for phrase in suspicious_phrases:
                if phrase.lower() in text_lower:
                    found_suspicious.append(phrase)
            result["checks"]["suspicious_phrases"] = found_suspicious
            
            # Проверка на количество слов
            if voice_duration > 6 and len(words) < voice_duration / 3:
                result["checks"]["too_short_text"] = True
            else:
                result["checks"]["too_short_text"] = False
            
            # Проверка на междометия
            interjections = {"ммм", "хмм", "эм", "ага", "угу", "ой", "ах", "ох", "эх", "ух"}
            if len(words) <= 2 and all(word in interjections for word in words) and voice_duration > 3:
                result["checks"]["only_interjections"] = True
            else:
                result["checks"]["only_interjections"] = False
            
            # Проверка на повторяющиеся символы
            repetitive_chars = []
            for word in words:
                if len(word) > 5 and len(set(word)) == 1:
                    repetitive_chars.append(word)
            result["checks"]["repetitive_chars"] = repetitive_chars
        
        return result


# Глобальный экземпляр AI сервиса
ai_service = AIService()
