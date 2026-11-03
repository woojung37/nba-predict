"""League definitions and Korean team names."""

LEAGUES = {
    "kbl": {"sport": "basketball", "league_id": 91, "name": "KBL", "name_ko": "KBL 남자농구",
            "season_key": lambda year: f"{year}-{year + 1}"},
    "vmen": {"sport": "volleyball", "league_id": 151, "name": "V-League Men", "name_ko": "V리그 남자배구",
             "season_key": lambda year: year},
    "vwomen": {"sport": "volleyball", "league_id": 152, "name": "V-League Women", "name_ko": "V리그 여자배구",
               "season_key": lambda year: year},
}

# Seasons are named by their starting year here: 2024 = 2024-25.
FREE_HISTORY = [2023, 2024]
CURRENT_SEASON = 2026

# API-Sports names -> Korean short names. Unknown names fall back to the API name.
TEAM_KO = {
    # KBL
    "Anyang JungKwanJang": "정관장", "Goyang Sono": "소노", "KCC Egis": "KCC", "KoGas": "가스공사",
    "LG Sakers": "LG", "Mobis Phoebus": "현대모비스", "Seoul Knights": "SK", "Seoul Thunders": "삼성",
    "Suwon KT": "KT", "Wonju DB": "DB",
    # V-League men
    "Ansan OK": "OK저축은행", "Busan OK": "OK저축은행", "Hyundai Skywalkers": "현대캐피탈",
    "KAL Jumbos": "대한항공", "KB Stars": "KB손해보험", "Kepco": "한국전력",
    "Samsung Blue Fangs": "삼성화재", "Woori": "우리카드",
    # V-League women
    "Daejeon JKJ W": "정관장", "Expressway Co W": "한국도로공사", "GS Caltex W": "GS칼텍스",
    "Hungkuk W": "흥국생명", "Hyundai E&C Hillstate W": "현대건설", "IBK W": "IBK기업은행",
    "Pepper Savings Bank W": "페퍼저축은행",
}

# Same club under a new API id after a move/rename -> keep one id so ratings carry over.
ID_ALIAS = {
    "vmen": {4144: 2100},  # Ansan OK -> Busan OK (2025)
}
