from enum import Enum

class ConstraintType(Enum):
    MAX_PER_DAY = "max_per_day"
    MAX_CONTINUOUS = "max_continuous"
    PERIOD_PRIORITY = "period_priority"  # <--- Проверь это имя!

GLOBAL_CONSTRAINTS = [
    {
        "type": ConstraintType.MAX_CONTINUOUS,
        "subjects": ["Фізика", "Математика", "Алгебра", "Геометрія", "Хімія"],
        "max_value": 2,
    },
    {
        "type": ConstraintType.MAX_PER_DAY,
        "subjects": ["Фізика", "Хімія", "Біологія", "Географія"],
        "max_value": 2,
    },
    {
        "type": ConstraintType.PERIOD_PRIORITY, # <--- И это
        "subjects": ["Математика", "Алгебра", "Укр. мова", "Англ. мова"],
        "preferred_periods": [1, 2, 3, 4, 5],
        "bonus": 2000
    }
]