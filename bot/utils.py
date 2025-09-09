def get_welcome_message():
    """Возвращает приветственное сообщение."""
    return (
        "Привет! Я бот для подсчёта калорий. Я помогу рассчитать твою дневную норму "
        "и сохраню твой профиль для будущих расчётов."
    )


def calculate_daily_calories(weight, height, age, gender, activity_level):
    """
    Рассчитывает дневную норму калорий по формуле Харриса-Бенедикта.
    """
    if gender == 'male':
        bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    elif gender == 'female':
        bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)
    else:
        raise ValueError("Пол должен быть 'male' или 'female'")

    activity_factors = {
        'none': 1.2,
        'low': 1.375,
        'medium': 1.55,
        'high': 1.725
    }

    factor = activity_factors.get(activity_level)
    if factor is None:
        raise ValueError(f"Неизвестный уровень активности: {activity_level}")

    return round(bmr * factor, 1)