import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from bot.database import get_meals_last_7_days, get_meals_last_30_days, get_db_connection
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


async def create_goal_progress_chart(user_id: int, current_weight: float, target_weight: float, 
                                   goal_type: str, goal_rate: str, start_date: datetime = None):
    """Создает график прогресса достижения цели"""
    
    # Парсим темп (например, "0.5кг/нед")
    kg_per_week = float(goal_rate.replace('кг/нед', ''))
    
    # Если дата начала не указана, берем текущую дату
    if start_date is None:
        start_date = datetime.now().date()
    else:
        start_date = start_date.date()
    
    # Рассчитываем количество недель до достижения цели
    weight_difference = abs(target_weight - current_weight)
    weeks_to_goal = int(weight_difference / kg_per_week)
    
    # Создаем список дат (каждую неделю)
    dates = [start_date + timedelta(weeks=i) for i in range(weeks_to_goal + 1)]
    
    # Рассчитываем вес для каждой недели
    weights = []
    for i in range(len(dates)):
        if goal_type == "lose":
            weight = current_weight - (kg_per_week * i)
        else:  # gain
            weight = current_weight + (kg_per_week * i)
        weights.append(weight)
    
    # Создаем график
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Строим линию прогресса
    ax.plot(dates, weights, color='#4CAF50', linewidth=3, marker='o', markersize=6, label='План')
    
    # Добавляем текущий вес (красная точка)
    ax.scatter([start_date], [current_weight], color='red', s=100, zorder=5, label='Текущий вес')
    
    # Добавляем целевую точку (зеленая точка)
    ax.scatter([dates[-1]], [target_weight], color='green', s=100, zorder=5, label='Целевой вес')
    
    # Настраиваем оси
    ax.set_xlabel('Дата', fontsize=12)
    ax.set_ylabel('Вес (кг)', fontsize=12)
    ax.set_title(f'Прогресс достижения цели: {goal_type}', fontsize=14, fontweight='bold')
    
    # Настраиваем подписи на оси X (каждые 2 недели)
    step = max(1, len(dates) // 8)
    ax.set_xticks(dates[::step])
    ax.set_xticklabels([date.strftime('%d.%m') for date in dates[::step]], rotation=45)
    
    # Добавляем сетку
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    
    # Добавляем легенду
    ax.legend()
    
    # Добавляем аннотации
    ax.annotate(f'Начало: {current_weight} кг', 
                xy=(start_date, current_weight), xytext=(10, 10),
                textcoords='offset points', fontsize=10, color='red')
    
    ax.annotate(f'Цель: {target_weight} кг\n{dates[-1].strftime("%d.%m.%Y")}', 
                xy=(dates[-1], target_weight), xytext=(10, -20),
                textcoords='offset points', fontsize=10, color='green')
    
    # Настраиваем отступы
    plt.tight_layout()
    
    # Сохраняем в байты
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer, dates[-1]  # Возвращаем также дату достижения цели

async def create_current_progress_chart(user_id: int, current_weight: float, target_weight: float, 
                                      goal_type: str, goal_rate: str, start_date: datetime = None):
    """Создает график текущего прогресса с отметкой где должен быть вес сейчас"""
    
    # Парсим темп
    kg_per_week = float(goal_rate.replace('кг/нед', ''))
    
    if start_date is None:
        start_date = datetime.now().date()
    else:
        start_date = start_date.date()
    
    # Рассчитываем сколько недель прошло
    weeks_passed = (datetime.now().date() - start_date).days / 7
    
    # Рассчитываем какой вес должен быть сейчас
    if goal_type == "lose":
        expected_weight = current_weight - (kg_per_week * weeks_passed)
    else:  # gain
        expected_weight = current_weight + (kg_per_week * weeks_passed)
    
    # Создаем данные для графика (последние 8 недель)
    weeks_data = []
    weights_data = []
    expected_weights = []
    
    for i in range(8):
        week_date = start_date + timedelta(weeks=i)
        if goal_type == "lose":
            expected = current_weight - (kg_per_week * i)
        else:
            expected = current_weight + (kg_per_week * i)
        
        weeks_data.append(week_date)
        expected_weights.append(expected)
        
        # Здесь можно добавить реальные данные веса, если они есть
        # Пока используем только ожидаемые значения
        weights_data.append(None)
    
    # Создаем график
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Строим линию ожидаемого прогресса
    ax.plot(weeks_data, expected_weights, color='#4CAF50', linewidth=2, 
            linestyle='--', alpha=0.7, label='Ожидаемый прогресс')
    
    # Отмечаем текущую дату
    current_date = datetime.now().date()
    ax.axvline(x=current_date, color='red', linestyle='-', alpha=0.7, label='Сегодня')
    
    # Отмечаем текущий вес
    ax.scatter([current_date], [current_weight], color='red', s=100, zorder=5, label='Текущий вес')
    
    # Отмечаем ожидаемый вес на сегодня
    ax.scatter([current_date], [expected_weight], color='blue', s=100, zorder=5, label='Ожидаемый вес')
    
    # Настраиваем оси
    ax.set_xlabel('Дата', fontsize=12)
    ax.set_ylabel('Вес (кг)', fontsize=12)
    ax.set_title('Текущий прогресс', fontsize=14, fontweight='bold')
    
    # Настраиваем подписи на оси X
    ax.set_xticks(weeks_data[::2])
    ax.set_xticklabels([date.strftime('%d.%m') for date in weeks_data[::2]], rotation=45)
    
    # Добавляем сетку
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    
    # Добавляем легенду
    ax.legend()
    
    # Добавляем информацию о прогрессе
    progress_text = f"Текущий вес: {current_weight:.1f} кг\nОжидаемый: {expected_weight:.1f} кг"
    if expected_weight > current_weight:
        progress_text += f"\nОтставание: {expected_weight - current_weight:.1f} кг"
    else:
        progress_text += f"\nОпережение: {current_weight - expected_weight:.1f} кг"
    
    ax.text(0.02, 0.98, progress_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # Настраиваем отступы
    plt.tight_layout()
    
    # Сохраняем в байты
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    return img_buffer