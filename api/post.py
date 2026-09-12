import os
import json
import random
import re
import time
import requests
import feedparser
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from mistralai.client import Mistral
from sulguk import transform_html

# ==================== КОНФИГ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

# ==================== ПРОФИЛЬ АВТОРА ====================
AUTHOR_PROFILE = """
Автор канала — молодой разработчик, который:
- Пишет о технологиях простыми словами
- Сам прошёл путь от новичка до уверенного кодера
- Не любит занудство, но и не хайпует
- Делится личным опытом и реальными историями
- Объясняет сложное через бытовые аналогии
- Считает, что программирование — это творчество, а не скука
"""

# ==================== СИСТЕМНЫЙ ПРОМПТ ====================
SYSTEM_PROMPT = f"""Ты ведёшь Telegram-канал о технологиях и программировании.

📌 ПРОФИЛЬ АВТОРА:
{AUTHOR_PROFILE}

📌 ТЕМАТИКА КАНАЛА (только это!):
- Программирование (Python, JS, Go и т.д.)
- Технологии и IT-новости
- Инструменты разработчика (git, docker, IDE)
- Искусственный интеллект и ML
- Советы для новичков и не только
- Интересные факты о коде, железе, интернете

❌ НЕ ПИШИ О: политике, религии, криминале, медицине, личных проблемах.

⚠️ КРИТИЧНО — ДЛИНА:
Максимум 900 символов! Считай символы. Не влезает — сократи.

📌 ФОРМАТИРОВАНИЕ:
1. ТОЛЬКО теги: <b>жирный</b>, <i>курсив</i>, <code>код</code>, <pre>блок</pre>
2. НИКАКОГО markdown (**, ###, ---, ```)
3. ВСЕГДА закрывай теги
4. Внутри <code> заменяй < на &lt; и > на &gt;

📌 СТИЛЬ:
- Первый абзац — зацепка (вопрос, история, факт)
- Середина — объяснение через аналогию или личный опыт
- Конец — вывод или вопрос к читателю
- Пиши от первого лица: "я", "мой опыт", "советую"
- Эмодзи: 5-7 штук

ФОРМАТ ОТВЕТА: только готовый пост с HTML. Без предисловий.
"""

# ==================== ФОРМАТЫ ПОСТОВ ====================
POST_FORMATS = [
    # 1. Личная история
    """ФОРМАТ: Личная история
Начни: "Когда я начинал..." или "Помню свой первый..."
Расскажи реальный случай из практики разработчика.
В конце — вывод.
Тема: {topic}""",

    # 2. Простыми словами
    """ФОРМАТ: Простыми словами
Начни с вопроса: "Знаешь, что такое X?" или "Зачем нужен Y?"
Объясни через бытовую аналогию.
Тема: {topic}""",

    # 3. Лайфхак
    """ФОРМАТ: Лайфхак
Начни: "Вот трюк, который сэкономит тебе часы:"
Дай конкретный практический совет разработчику.
Тема: {topic}""",

    # 4. Миф vs реальность
    """ФОРМАТ: Миф vs Реальность
Начни: "Многие думают, что X. На самом деле..."
Разрушь миф о разработке или технологиях.
Тема: {topic}""",

    # 5. Новость + мнение
    """ФОРМАТ: Новость + мнение
Расскажи новость из IT.
Добавь своё мнение: "Как по мне..."
Спроси читателя: "А что думаешь ты?"
Тема: {topic}""",

    # 6. Совет из опыта
    """ФОРМАТ: Совет из опыта
Начни: "Совет, который я бы дал себе 5 лет назад:"
Поделись уроком.
Объясни почему важно.
Тема: {topic}""",

    # 7. Разбор ошибки
    """ФОРМАТ: Разбор ошибки
Начни: "Однажды я сломал прод..." или "Классическая ошибка новичков:"
Расскажи про типичную ошибку в коде.
Как её избежать.
Тема: {topic}""",

    # 8. Сравнение
    """ФОРМАТ: Сравнение
Начни: "X или Y — что выбрать?"
Сравни два инструмента/языка/подхода.
Дай рекомендацию от себя.
Тема: {topic}""",
]

# ==================== RSS-ИСТОЧНИКИ ====================
RSS_FEEDS = [
    "https://habr.com/ru/rss/news/",
    "https://habr.com/ru/rss/hubs/python/",
    "https://dev.to/feed",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
]

# ==================== ФИЛЬТР ТЕМ (только IT) ====================
ALLOWED_KEYWORDS = [
    "python", "javascript", "java", "go ", "rust", "c++", "kotlin", "swift",
    "код", "программ", "разработ", "developer", "dev",
    "git", "docker", "kubernetes", "linux", "vscode", "ide",
    "ai", "ии", "нейросет", "ml", "machine learning", "gpt", "llm",
    "база данных", "sql", "nosql", "postgres", "mysql",
    "алгоритм", "структур", "api", "http", "web",
    "фреймворк", "библиотек", "npm", "pip",
    "сервер", "backend", "frontend", "fullstack",
    "тестирован", "баг", "фикс", "ошибк",
    "технолог", "it", "компьютер", "софт",
]

def is_it_related(text):
    """Проверяет, относится ли новость к IT/программированию"""
    text_lower = text.lower()
    return any(kw in text_lower for kw in ALLOWED_KEYWORDS)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
def clean_html_from_feed(text):
    """Убирает HTML-мусор из RSS"""
    text = re.sub(r'<img[^>]*>', '', text)
    text = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def sanitize_mistral_output(text):
    """Чистит markdown из ответа Mistral"""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-—=]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'```[a-zA-Z]*\n', '<pre>', text)
    text = text.replace('```', '</pre>')
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ==================== ТЕМЫ ====================
def fetch_fresh_news():
    """Берёт свежую IT-новость из RSS"""
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                title = clean_html_from_feed(entry.get("title", ""))
                summary = clean_html_from_feed(entry.get("summary", ""))[:400]
                
                # Фильтр: только IT-темы
                if not is_it_related(title + " " + summary):
                    continue
                
                return f"{title}\n\n{summary}"
        except Exception as e:
            print(f"Ошибка RSS {feed_url}: {e}")
    return None


def get_next_topic():
    """Берёт свежую новость или тему из topics.txt"""
    news = fetch_fresh_news()
    if news:
        return news, None
    
    # Fallback — темы из файла
    try:
        topics_path = os.path.join(os.path.dirname(__file__), "..", "topics.txt")
        with open(topics_path, "r", encoding="utf-8") as f:
            all_topics = [line.strip() for line in f if line.strip()]
    except:
        return "Интересные факты о технологиях", None
    
    used_path = os.path.join(os.path.dirname(__file__), "..", "used_topics.json")
    try:
        with open(used_path, "r", encoding="utf-8") as f:
            used = json.load(f).get("used", [])
    except:
        used = []
    
    for topic in all_topics:
        if topic not in used:
            return topic, None
    
    return all_topics[0] if all_topics else "Технологии", None


def save_used_topic(topic):
    """Сохраняет использованную тему"""
    used_path = os.path.join(os.path.dirname(__file__), "..", "used_topics.json")
    try:
        with open(used_path, "r", encoding="utf-8") as f:
            used_data = json.load(f)
    except:
        used_data = {"used": []}
    
    if topic not in used_data["used"]:
        used_data["used"].append(topic)
    
    # Храним только последние 50
    used_data["used"] = used_data["used"][-50:]
    
    with open(used_path, "w", encoding="utf-8") as f:
        json.dump(used_data, f, ensure_ascii=False, indent=2)


# ==================== ГЕНЕРАЦИЯ ПОСТА ====================
def generate_post(topic):
    """Генерирует пост через Mistral AI"""
    if not MISTRAL_API_KEY:
        return None, "MISTRAL_API_KEY не задан"
    
    client = Mistral(api_key=MISTRAL_API_KEY)
    max_retries = 5
    
    # Случайный формат
    chosen_format = random.choice(POST_FORMATS).format(topic=topic)
    
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model="ministral-8b-latest",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": chosen_format}
                ],
                temperature=0.85,
                max_tokens=400
            )
            raw_text = response.choices[0].message.content
            cleaned = sanitize_mistral_output(raw_text)
            return cleaned, None
        
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Rate limit" in err_str:
                wait = 5 * (attempt + 1)
                print(f"⚠️ Rate limit, ждём {wait} сек... ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            return None, err_str
    
    return None, "Превышен лимит запросов"


# ==================== ФОТО ====================
def search_image(query):
    """Ищет картинку на Unsplash без людей"""
    if not UNSPLASH_ACCESS_KEY:
        return None
    
    try:
        # Убираем лишние символы
        clean_query = re.sub(r'[^\w\s]', ' ', query)[:80]
        # Исключаем людей
        clean_query += " technology code computer"
        
        url = "https://api.unsplash.com/search/photos"
        params = {
            "query": clean_query,
            "per_page": 10,
            "orientation": "landscape",
            "client_id": UNSPLASH_ACCESS_KEY
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("results"):
            # Фильтруем фото с людьми
            bad_words = [
                "person", "people", "man", "woman", "face", "human",
                "indian", "asian", "african", "portrait", "child", "kid",
                "boy", "girl", "male", "female", "guy", "lady"
            ]
            
            for photo in data["results"]:
                tags = [t.get("title", "").lower() for t in photo.get("tags", [])]
                alt = (photo.get("alt_description") or "").lower()
                combined = " ".join(tags) + " " + alt
                
                if not any(w in combined for w in bad_words):
                    return photo["urls"]["regular"]
            
            # Если все с людьми — вернём None (лучше без фото, чем с человеком)
            return None
    except Exception as e:
        print(f"Ошибка Unsplash: {e}")
    
    return None


# ==================== ПУБЛИКАЦИЯ ====================
def publish_to_channel(text, image_url=None):
    """Публикует пост в канал"""
    if not BOT_TOKEN or not CHANNEL_ID:
        return False, "BOT_TOKEN или CHANNEL_ID не заданы"
    
    try:
        MAX_CAPTION = 1024
        
        # Обрезка по границе предложения
        if image_url and len(text) > MAX_CAPTION:
            cut_text = text[:MAX_CAPTION]
            last_dot = max(
                cut_text.rfind('.'),
                cut_text.rfind('!'),
                cut_text.rfind('?'),
                cut_text.rfind('\n')
            )
            if last_dot > MAX_CAPTION - 200:
                text = text[:last_dot + 1]
            else:
                text = cut_text
        
        # Fix HTML
        try:
            parsed = transform_html(text)
            text = parsed.text
            entities = []
            for e in parsed.entities:
                if hasattr(e, 'model_dump'):
                    entities.append(e.model_dump(exclude_none=True))
                else:
                    entities.append(e)
        except Exception as fix_err:
            return False, f"HTML fix error: {fix_err}"
        
        if image_url:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            payload = {
                "chat_id": CHANNEL_ID,
                "photo": image_url,
                "caption": text,
                "caption_entities": entities
            }
            response = requests.post(url, json=payload, timeout=15)
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": CHANNEL_ID,
                "text": text[:4096],
                "entities": entities,
                "disable_web_page_preview": False
            }
            response = requests.post(url, json=payload, timeout=15)
        
        result = response.json()
        if result.get("ok"):
            return True, None
        return False, result.get("description", "Неизвестная ошибка")
    except Exception as e:
        return False, str(e)


# ==================== ГЛАВНАЯ ====================
def run_posting():
    """Главная функция"""
    log = []
    
    topic, err = get_next_topic()
    if err:
        log.append(f"Ошибка темы: {err}")
    log.append(f"Тема: {topic[:80]}")
    
    post_text, err = generate_post(topic)
    if err:
        return False, f"Ошибка Mistral: {err}"
    log.append(f"Пост ({len(post_text)} симв.)")
    
    # Картинка по заголовку
    search_query = topic.split('\n')[0][:50]
    image_url = search_image(search_query)
    log.append("Фото найдено" if image_url else "Без фото")
    
    ok, err = publish_to_channel(post_text, image_url)
    if not ok:
        return False, f"Ошибка публикации: {err}"
    log.append("Опубликовано")
    
    save_used_topic(topic)
    return True, " | ".join(log)


# ==================== VERCEL HANDLER ====================
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.getenv("CRON_SECRET", "")
        if secret:
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            if query.get("secret", [""])[0] != secret:
                self.send_response(403)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Forbidden"}).encode())
                return
        
        ok, message = run_posting()
        
        self.send_response(200 if ok else 500)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        
        response = {
            "success": ok,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode())
    
    def do_POST(self):
        self.do_GET()
