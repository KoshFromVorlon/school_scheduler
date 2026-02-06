from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.extensions import db


# 1. Класс (Группа студентов)
class StudentGroup(db.Model):
    __tablename__ = 'student_groups'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)  # Пример: "10-А"
    size: Mapped[int] = mapped_column(default=25)

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)


# 2. Нагрузка (Кто, Кому, Что и Сколько должен преподать)
class Workload(db.Model):
    __tablename__ = 'workloads'

    id: Mapped[int] = mapped_column(primary_key=True)
    hours_per_week: Mapped[int] = mapped_column(nullable=False)  # Сколько часов

    # Связи
    teacher_id: Mapped[int] = mapped_column(ForeignKey('teachers.id'))
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id'))
    group_id: Mapped[int] = mapped_column(ForeignKey('student_groups.id'))
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'))


# 3. Временной слот (1-й урок Понедельника)
class TimeSlot(db.Model):
    __tablename__ = 'time_slots'

    id: Mapped[int] = mapped_column(primary_key=True)
    day_of_week: Mapped[int] = mapped_column(nullable=False)  # 1=ПН, 2=ВТ...
    period_number: Mapped[int] = mapped_column(nullable=False)  # Номер урока (1, 2, 3...)

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'))


# 4. ИТОГ: Запись в расписании (Результат работы алгоритма)
class ScheduleEntry(db.Model):
    __tablename__ = 'schedule_entries'

    id: Mapped[int] = mapped_column(primary_key=True)

    # Ссылка на нагрузку
    workload_id: Mapped[int] = mapped_column(ForeignKey('workloads.id'))

    # Когда и Где
    timeslot_id: Mapped[int] = mapped_column(ForeignKey('time_slots.id'))
    room_id: Mapped[int] = mapped_column(ForeignKey('rooms.id'), nullable=True)