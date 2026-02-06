from sqlalchemy import ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.extensions import db
# ИМПОРТ ИЗ НОВОГО ФАЙЛА
from src.models.enums import SubgroupType, RoomType


class StudentGroup(db.Model):
    __tablename__ = 'student_groups'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    size: Mapped[int] = mapped_column(default=30)
    shift: Mapped[int] = mapped_column(default=1)

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)

    def __str__(self):
        return self.name


class Workload(db.Model):
    __tablename__ = 'workloads'

    id: Mapped[int] = mapped_column(primary_key=True)
    hours_per_week: Mapped[int] = mapped_column(nullable=False)

    teacher_id: Mapped[int] = mapped_column(ForeignKey('teachers.id'))
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id'))
    group_id: Mapped[int] = mapped_column(ForeignKey('student_groups.id'))
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'))

    # Ссылаемся на общие типы
    subgroup: Mapped[SubgroupType] = mapped_column(Enum(SubgroupType), default=SubgroupType.WHOLE_CLASS)
    required_room_type: Mapped[RoomType] = mapped_column(Enum(RoomType), default=RoomType.STANDARD)

    teacher = relationship('Teacher')
    subject = relationship('Subject')
    group = relationship('StudentGroup')

    def __str__(self):
        sg = "" if self.subgroup == SubgroupType.WHOLE_CLASS else f" ({self.subgroup.value})"
        return f"{self.subject}{sg} - {self.group}"


class TimeSlot(db.Model):
    __tablename__ = 'time_slots'

    id: Mapped[int] = mapped_column(primary_key=True)
    day_of_week: Mapped[int] = mapped_column(nullable=False)
    period_number: Mapped[int] = mapped_column(nullable=False)
    shift_number: Mapped[int] = mapped_column(default=1)

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'))

    def __str__(self):
        days = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт"}
        return f"{days.get(self.day_of_week, str(self.day_of_week))}, Урок {self.period_number}"


class ScheduleEntry(db.Model):
    __tablename__ = 'schedule_entries'

    id: Mapped[int] = mapped_column(primary_key=True)

    workload_id: Mapped[int] = mapped_column(ForeignKey('workloads.id'))
    timeslot_id: Mapped[int] = mapped_column(ForeignKey('time_slots.id'))
    room_id: Mapped[int] = mapped_column(ForeignKey('rooms.id'), nullable=True)

    workload = relationship('Workload')
    timeslot = relationship('TimeSlot')
    room = relationship('Room')

    def __str__(self):
        return f"{self.workload} @ {self.timeslot}"