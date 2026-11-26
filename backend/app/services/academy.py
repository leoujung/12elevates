"""ONE Academy: 16-module structure, content not yet written.

The business owner chose to build the structure first and fill in the 16 module titles
later ("Bangun dulu strukturnya dengan 16 slot kosong 'Segera Hadir'"). So every module
here is a placeholder -- no title, no duration, no real content -- and none can be
"completed" because there is nothing to learn yet. This is intentionally stateless (no
database table): there is no real progress to persist until modules exist. When content
is supplied, this file is where titles/durations get filled in, and a completion-tracking
table can be added at that point.
"""

TOTAL_MODULES = 16


def academy_overview() -> dict:
    modules = [
        {"order": i, "title": "Segera Hadir", "duration_minutes": None, "status": "coming_soon"}
        for i in range(1, TOTAL_MODULES + 1)
    ]
    return {
        "modules": modules,
        "total": TOTAL_MODULES,
        "completed": 0,
        "percent": 0,
        "message": "Konten ONE Academy belum tersedia. Modul akan terbuka saat kontennya siap.",
    }
