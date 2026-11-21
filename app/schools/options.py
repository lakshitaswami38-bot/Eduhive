FACILITIES = [
    ("library", "Library"),
    ("science_lab", "Science lab"),
    ("computer_lab", "Computer lab"),
    ("sports_ground", "Sports ground"),
    ("smart_classes", "Smart classes"),
    ("transport", "School transport"),
    ("hostel", "Hostel"),
    ("cctv", "CCTV security"),
    ("medical_room", "Medical room"),
    ("canteen", "Canteen"),
    ("auditorium", "Auditorium"),
]

SPECIALITIES = [
    ("sports", "Sports"),
    ("science", "Science"),
    ("mathematics", "Mathematics"),
    ("arts", "Arts and craft"),
    ("music", "Music"),
    ("dance", "Dance"),
    ("robotics", "Robotics"),
    ("coding", "Coding"),
    ("debate", "Debate and public speaking"),
    ("languages", "Languages"),
]

MEDIUMS = [
    ("", "Select medium"),
    ("English", "English"),
    ("Hindi", "Hindi"),
    ("Both", "English and Hindi"),
    ("Other", "Other"),
]

CLASS_LEVELS = ["Nursery", "LKG", "UKG"] + [str(n) for n in range(1, 13)]

FACILITY_LABELS = dict(FACILITIES)
SPECIALITY_LABELS = dict(SPECIALITIES)