import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from bot.database import get_meals_last_7_days, get_meals_last_30_days
import io
import base64

# Настройка matplotlib для русского языка
plt.rcParams['font.family'] = 'DejaVu Sans'
plt.rcParams['axes.unicode_minus'] = False

async def create_weekly_chart(user_id: int):
    """Создает график калорий за неделю"""
    meals = get_meals_last_7_days(user_id)
    
    # Группируем по дням
    daily_calories = {}
    for meal in meals:
        date_str = meal['timestamp'].split()[0]
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if date not in daily_calories:
            daily_calories[date] = 0
        daily_calories[date] += meal['calories']
    
    # Создаем список дат за последние 7 дней
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=6)
    dates = [start_date + timedelta(days=i) for i in range(7)]
    
    # Создаем список калорий для каждого дня
    calories = [daily_calories.get(date, 0) for date in dates]
    
    # Создаем график
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Строим столбчатую диаграмму
    bars = ax.bar(range(len(dates)), calories, color='#4CAF50', alpha=0.7)
    
    # Настраиваем оси
    ax.set_xlabel('Дни недели', fontsize=12)
    ax.set_ylabel('Калории', fontsize=12)
    ax.set_title('Калории за неделю', fontsize=14, fontweight='bold')
    
    # Настраиваем подписи на оси X
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels([date.strftime('%d.%m') for date in dates], rotation=45)
    
    # Добавляем значения на столбцы
    for i, bar in enumerate(bars):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 10,
                f'{int(height)}', ha='center', va='bottom', fontweight='bold')
    
    # Настраиваем сетку
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    
    # Настраиваем отступы
    plt.tight_layout()
    
    # Сохраняем в байты
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer

async def create_monthly_chart(user_id: int):
    """Создает график калорий за месяц"""
    meals = get_meals_last_30_days(user_id)
    
    # Группируем по дням
    daily_calories = {}
    for meal in meals:
        date_str = meal['timestamp'].split()[0]
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        if date not in daily_calories:
            daily_calories[date] = 0
        daily_calories[date] += meal['calories']
    
    # Создаем список дат за последние 30 дней
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=29)
    dates = [start_date + timedelta(days=i) for i in range(30)]
    
    # Создаем список калорий для каждого дня
    calories = [daily_calories.get(date, 0) for date in dates]
    
    # Создаем график
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Строим линейный график
    ax.plot(range(len(dates)), calories, color='#2196F3', linewidth=2, marker='o', markersize=4)
    
    # Настраиваем оси
    ax.set_xlabel('Дни месяца', fontsize=12)
    ax.set_ylabel('Калории', fontsize=12)
    ax.set_title('Калории за месяц', fontsize=14, fontweight='bold')
    
    # Настраиваем подписи на оси X (каждые 5 дней)
    step = 5
    ax.set_xticks(range(0, len(dates), step))
    ax.set_xticklabels([dates[i].strftime('%d.%m') for i in range(0, len(dates), step)], rotation=45)
    
    # Настраиваем сетку
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    
    # Настраиваем отступы
    plt.tight_layout()
    
    # Сохраняем в байты
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer