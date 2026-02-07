import click
import random
from flask.cli import with_appcontext
from src.extensions import db
from src.models.school import School, Room, Teacher, Subject
from src.models.schedule import StudentGroup, TimeSlot, Workload
from src.models.enums import RoomType, SubgroupType


@click.command('init_real_school')
@with_appcontext
def init_real_school_command():
    """Полный сброс и подготовка базы (структура, но без данных нагрузки)."""

    print("🔥 СБРОС БАЗЫ ДАННЫХ...")
    db.drop_all()
    db.create_all()

    # 1. ШКОЛА
    school = School(name='Софіївсько-Борщагівський ліцей')
    db.session.add(school)
    db.session.flush()

    # 2. СЛОТЫ ВРЕМЕНИ (14 уроков)
    print("⏰ Настройка временной сетки...")
    for day in range(1, 6):
        for i in range(1, 15):
            # 1 смена: 1-7, 2 смена: 8-14
            shift = 1 if i <= 7 else 2
            db.session.add(TimeSlot(day_of_week=day, period_number=i, shift_number=shift, school_id=school.id))

    db.session.commit()
    print("✅ БАЗА ГОТОВА. Теперь загружай 'rooms.csv' и 'workload.csv' через /import.")


def register_commands(app):
    app.cli.add_command(init_real_school_command)