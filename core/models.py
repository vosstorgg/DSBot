"""
Модели данных и вспомогательные классы
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class UserProfile:
    """Модель профиля пользователя"""
    chat_id: str
    username: Optional[str] = None
    gender: Optional[str] = None
    age_group: Optional[str] = None
    lucid_dreaming: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass
class Dream:
    """Модель сна"""
    id: Optional[int] = None
    chat_id: str = ""
    dream_text: str = ""
    interpretation: str = ""
    source_type: str = "text"  # 'text' или 'voice'
    created_at: Optional[datetime] = None
    dream_date: Optional[str] = None
    tags: Optional[List[str]] = None


@dataclass
class Message:
    """Модель сообщения"""
    id: Optional[int] = None
    chat_id: str = ""
    role: str = ""  # 'user' или 'assistant'
    content: str = ""
    timestamp: Optional[datetime] = None


@dataclass
class AdminBroadcastState:
    """Состояние администратора при создании рассылки"""
    step: str = "waiting_content"  # waiting_content, confirming
    content: Optional[str] = None  # HTML (с форматированием и ссылками)
    media_type: Optional[str] = None  # photo, video, document, audio, voice, sticker
    media_file_id: Optional[str] = None
    caption: Optional[str] = None  # HTML caption
    parse_mode: Optional[str] = "HTML"


class BroadcastResult:
    """Результат рассылки"""
    def __init__(self):
        self.successful: List[str] = []
        self.failed: List[str] = []
        self.forbidden: List[str] = []
    
    @property
    def total_sent(self) -> int:
        return len(self.successful)
    
    @property
    def total_failed(self) -> int:
        return len(self.failed) + len(self.forbidden)
    
    @property
    def success_rate(self) -> float:
        total = self.total_sent + self.total_failed
        if total == 0:
            return 0.0
        return (self.total_sent / total) * 100


class PaginationHelper:
    """Помощник для пагинации"""
    
    @staticmethod
    def calculate_pagination(total_items: int, page: int, items_per_page: int) -> dict:
        """Вычисление параметров пагинации"""
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        page = max(0, min(page, total_pages - 1))
        offset = page * items_per_page
        
        has_prev = page > 0
        has_next = page < total_pages - 1
        
        return {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "items_per_page": items_per_page,
            "offset": offset,
            "has_prev": has_prev,
            "has_next": has_next
        }


class MessageFormatter:
    """Форматирование сообщений"""
    
    @staticmethod
    def format_dream_preview(dream_text: str, max_length: int = 60) -> str:
        """Форматирование превью сна"""
        if len(dream_text) <= max_length:
            return dream_text
        return dream_text[:max_length] + "..."
    
    @staticmethod
    def format_date(dt: datetime) -> str:
        """Форматирование даты для отображения"""
        return dt.strftime("%d.%m.%Y")
    
    @staticmethod
    def format_datetime(dt: datetime) -> str:
        """Форматирование даты и времени для отображения"""
        return dt.strftime("%d.%m.%Y в %H:%M")
    
    @staticmethod
    def truncate_message(text: str, max_length: int = 4000) -> str:
        """Обрезка сообщения до допустимой длины"""
        if len(text) <= max_length:
            return text
        return text[:max_length-30] + "\n\n_...сообщение обрезано_"
    
    @staticmethod
    def get_source_icon(source_type: str) -> str:
        """Получение иконки источника"""
        if source_type == "voice":
            return "🎤"
        else:
            return "✍️"
    
    @staticmethod
    def get_source_description(source_type: str) -> str:
        """Получение описания источника"""
        if source_type == "voice":
            return "🎤 Голосовое сообщение"
        else:
            return "✍️ Текстовое сообщение"
