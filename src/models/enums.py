import enum

class SubgroupType(enum.Enum):
    WHOLE_CLASS = "whole"
    GROUP_1 = "group_1"   # Первая подгруппа
    GROUP_2 = "group_2"   # Вторая подгруппа
    BOYS = "boys"
    GIRLS = "girls"

class RoomType(enum.Enum):
    STANDARD = "standard"
    LAB_PHYSICS = "physics"
    LAB_CHEMISTRY = "chemistry"
    LAB_BIO = "bio"
    GYM = "gym"
    IT_LAB = "it"