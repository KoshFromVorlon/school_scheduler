from flask import Blueprint, jsonify
from src.models.school import Room
from src.models.schedule import Workload, TimeSlot
from src.solver.engine import SchoolScheduler

# Создаем Blueprint (модуль)
debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/generate-test/<int:school_id>')
def generate_schedule(school_id):
    """
    Тестовый запуск генерации. В будущем это будет Celery задача.
    Сейчас - синхронный вызов для проверки алгоритма.
    """
    # 1. Загрузка данных
    workloads = Workload.query.filter_by(school_id=school_id).all()
    slots = TimeSlot.query.filter_by(school_id=school_id).all()
    rooms = Room.query.filter_by(school_id=school_id).all()

    if not workloads:
        return jsonify({"error": "No data found. Run 'flask seed_db' first."}), 404

    # 2. Запуск алгоритма
    solver = SchoolScheduler(school_id)
    result = solver.run_algorithm(workloads, slots, rooms)

    if not result:
        return jsonify({"status": "failed", "message": "Infeasible constraints"}), 400

    # 3. Формирование ответа (JSON)
    schedule_json = []
    for item in result:
        schedule_json.append({
            "day": item['slot'].day_of_week,
            "period": item['slot'].period_number,
            "subject": item['workload'].subject_id, # В идеале подтянуть name
            "teacher": item['workload'].teacher_id,
            "group": item['workload'].group_id,
            "room": item['room'].name
        })

    # Сортируем по Дню и Уроку
    schedule_json.sort(key=lambda x: (x['day'], x['period']))

    return jsonify({
        "status": "success",
        "total_lessons": len(schedule_json),
        "schedule": schedule_json
    })