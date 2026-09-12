import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

from api.post import run_posting

print("⏳ Генерирую пост...")
ok, message = run_posting()
print(f"\n✅ Успех: {ok}")
print(f"📋 Лог: {message}")