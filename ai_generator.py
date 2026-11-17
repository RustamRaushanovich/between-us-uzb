import base64
import json
import random
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REFERENCE_IMAGE = BASE_DIR / "assets" / "reference.jpg"
GENERATED_DIR = BASE_DIR / "generated"

MORNING_SCENES = [
    (
        "boy in sky-blue denim jacket over white tee with tiny 'Between' patch, "
        "girl in pastel yellow knit cardigan with 'Us' hairclip, sitting on a sunny "
        "flower-filled balcony at 6 AM sunrise with warm tea and croissants"
    ),
    (
        "boy in mint-green hoodie with 'Between' embroidery, girl in soft peach "
        "windbreaker with 'Us' pin, jogging/walking together in a misty golden morning "
        "park as the sun rises through trees"
    ),
    (
        "boy in beige linen shirt, girl in cream sundress with light cardigan, "
        "watering potted flowers together on a bright sunlit terrace in the early morning"
    ),
]

NIGHT_SCENES = [
    (
        "boy in dark navy star-patterned pajamas with tiny 'Between' pocket, "
        "girl in soft lavender-and-cream pajamas with 'Us' patch hugging a teddy bear, "
        "sitting by a cozy bedroom window with crescent moon and fairy lights"
    ),
    (
        "boy in cozy charcoal knit loungewear, girl in warm cream fleece hoodie, "
        "sitting wrapped in a soft blanket on a rooftop under a starry night sky "
        "and glowing lanterns, drinking warm chamomile tea"
    ),
]

HOURLY_SCENES = [
    (
        "boy in black bomber jacket with 'Between' text, girl in cream bomber jacket "
        "with 'Us' text, walking hand-in-hand under a clear umbrella on a rainy autumn "
        "street reflecting warm golden streetlights"
    ),
    (
        "boy in warm olive corduroy jacket, girl in burgundy beret and cream sweater, "
        "sitting together in a quiet cozy library surrounded by warm lamp light and books"
    ),
    (
        "boy in casual white sweater and jeans, girl in soft pink coat and scarf, "
        "sharing headphones while sitting on a park bench under cherry blossoms"
    ),
    (
        "boy in dark denim jacket and scarf, girl in camel coat and knit beanie, "
        "watching a golden sunset by a calm lake from a wooden pier"
    ),
    (
        "boy in cozy grey sweatshirt, girl in pastel blue sweater, baking cookies "
        "together in a warm sunlit kitchen with flour on their cheeks, laughing"
    ),
    (
        "boy in mustard hoodie, girl in cream puffer vest over turtleneck, "
        "riding bicycles together along a quiet tree-lined path in golden afternoon light"
    ),
    (
        "boy in navy sweater, girl in soft beige cardigan, sitting at a small outdoor "
        "cafe table sharing hot chocolate and smiling warmly at each other"
    ),
    (
        "boy in cozy winter parka with fur hood, girl in white knit sweater and earmuffs, "
        "catching gentle snowflakes together under warm glowing street lamps"
    ),
]

FALLBACK_MORNING_CAPTIONS = [
    (
        "Xayrli tong! Yangi kun — yangi umidlar va pok niyatlar boshlanishi. "
        "Bugungi kuningiz fayzli, barakali va iliq tabassumlarga boy bo'lsin! ☀️🤍\n\n@Between_Us_uzb"
    ),
    (
        "Assalomu alaykum, xayrli tong! Tonggi salqin havo va quyosh nuri qalbingizga "
        "xotirjamlik olib kirsin. Yaxshi kayfiyat hamrohingiz bo'lsin! 🌸☕️\n\n@Between_Us_uzb"
    ),
    (
        "Yangi tong muborak! Har bir boshlangan kun — yaxshilikka, mehrga va "
        "orzularga yana bir qadam yaqinlashish uchun imkoniyatdir. 🌅💛\n\n@Between_Us_uzb"
    ),
    (
        "Xayrli tong! Bugun faqat yaxshi narsalarni o'ylang, tabassum qiling va "
        "qalbingizdagi iliqlikni yaqinlaringiz bilan bo'lishing. ☀️🌷\n\n@Between_Us_uzb"
    ),
]

FALLBACK_NIGHT_CAPTIONS = [
    (
        "Xayrli tun... Bugungi barcha charchoqlar ortda qolsin. "
        "Tuningiz osuda, qalbingiz esa sokin va xotirjam o'tsin. Shirin tushlar! 🌙✨🤍\n\n@Between_Us_uzb"
    ),
    (
        "Tuningiz xayrli bo'lsin! Yulduzli osmon ostida barcha tashvishlarni unuting, "
        "ertangi tong sizga faqat yaxshiliklar olib kelsin. 🌌🤍\n\n@Between_Us_uzb"
    ),
    (
        "Sokin tun, osuda uyqu... Ba'zan eng yaxshi davo — ko'zlarni yumib, "
        "ertangi kunga ishonch bilan orom olishdir. Xayrli tun! 🌠🕊️\n\n@Between_Us_uzb"
    ),
    (
        "Xayrli tun! Qalbingizda tinchlik, uyingizda fayz va baraka bo'lsin. "
        "Yaxshi dam oling, ertaga yangi kun kutmoqda. 🌙💛\n\n@Between_Us_uzb"
    ),
]

FALLBACK_HOURLY_CAPTIONS = [
    (
        "Ba'zi tuyg'ular so'z bilan aytilmaydi... ular shunchaki nigohlarda va "
        "sukunatda yashaydi. 🤍✨\n\n@Between_Us_uzb"
    ),
    (
        "Hayotdagi eng go'zal lahzalar — yoningda seni tushunadigan inson bilan "
        "bo'lishilgan oddiy daqiqalardir. ☕️🍂\n\n@Between_Us_uzb"
    ),
    (
        "Shovqinli dunyoda faqat ikkimizga tegishli kichik bir sokinlik bo'lishi — "
        "eng katta baxt. 🤍🌙\n\n@Between_Us_uzb"
    ),
    (
        "Har bir fasl, har bir ob-havo go'zal — agar yoningda yuragingga yaqin inson bo'lsa. 🌧️💛\n\n@Between_Us_uzb"
    ),
    (
        "Kimdir senga 'yaxshimisan?' deb shunchaki so'raydi, kimdir esa ko'zlaringga "
        "qarab javobni allaqachon bilib oladi. 🤍🌿\n\n@Between_Us_uzb"
    ),
    (
        "Eng chiroyli xotiralar — rejasiz, tasodifan va samimiyat bilan o'tgan "
        "kunlardan qoladi. 📸✨\n\n@Between_Us_uzb"
    ),
    (
        "Vaqt hamma narsani o'zgartiradi, faqat chin dildan bog'langan qalblar "
        "masofaga ham, yillarga ham bo'ysunmaydi. 🕰️🤍\n\n@Between_Us_uzb"
    ),
    (
        "Ba'zan bitta issiq choy, jimlik va yoningdagi ishonchli yelka — "
        "dunyodagi barcha so'zlardan qadrliroq. ☕️🌸\n\n@Between_Us_uzb"
    ),
    (
        "Qalbga yaqin inson bilan o'tgan bir soat — yolg'izlikda o'tgan bir yildan "
        "mazmunliroq. ⏳💛\n\n@Between_Us_uzb"
    ),
    (
        "Hamma narsani baland ovozda aytish shart emas. Ba'zi sirlar faqat "
        "oramizda qolgani bilan go'zal... 🤫🤍\n\n@Between_Us_uzb"
    ),
    (
        "Yomg'ir ham, qor ham, quyosh ham — agar ikki kishi bir tomonga qarab "
        "yursa, har doim go'zal ko'rinadi. 🌦️✨\n\n@Between_Us_uzb"
    ),
    (
        "Insonni eng ko'p quvontiradigan narsa — uning kichik odatlarini ham "
        "unutmaydigan mehrli e'tibordir. 🌷🤍\n\n@Between_Us_uzb"
    ),
]


def _pick_scene(mode: str) -> str:
    if mode == "morning":
        return random.choice(MORNING_SCENES)
    if mode == "night":
        return random.choice(NIGHT_SCENES)
    return random.choice(HOURLY_SCENES)


def generate_caption(gemini_key: str, mode: str, scene_desc: str) -> str:
    """Generate a fresh Latin-Uzbek caption via Gemini, with local fallback."""
    if gemini_key:
        if mode == "morning":
            task = (
                "Write a warm, uplifting 'Xayrli tong' (Good Morning) Telegram post in "
                "Uzbek LATIN script (lotin yozuvi) wishing a great day and good mood."
            )
        elif mode == "night":
            task = (
                "Write a calm, comforting 'Xayrli tun' (Good Night) Telegram post in "
                "Uzbek LATIN script (lotin yozuvi) wishing a peaceful and quiet night."
            )
        else:
            task = (
                "Write a short, poetic, heartfelt romantic/aesthetic Telegram post in "
                "Uzbek LATIN script (lotin yozuvi) about unspoken feelings, warmth, and togetherness."
            )

        prompt = (
            f"{task}\n"
            f"Scene context: {scene_desc}\n"
            "Rules:\n"
            "- Strictly use Uzbek LATIN script (NO Cyrillic!).\n"
            "- 2 to 4 short lines, warm and natural Uzbek, with 2-3 fitting emojis.\n"
            "- End with '@Between_Us_uzb' on a new line.\n"
            "- Output ONLY the post text, no extra commentary."
        )
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={gemini_key}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text:
                if "@Between_Us_uzb" not in text:
                    text = f"{text}\n\n@Between_Us_uzb"
                return text
        except Exception as exc:
            print(f"[AI Caption] Gemini xatosi, zaxira matn ishlatiladi: {exc}")

    if mode == "morning":
        return random.choice(FALLBACK_MORNING_CAPTIONS)
    if mode == "night":
        return random.choice(FALLBACK_NIGHT_CAPTIONS)
    return random.choice(FALLBACK_HOURLY_CAPTIONS)


def _generate_image_gemini(gemini_key: str, full_prompt: str, out_path: Path) -> bool:
    if not gemini_key:
        return False

    parts: list[dict] = []
    if REFERENCE_IMAGE.exists():
        ref_b64 = base64.b64encode(REFERENCE_IMAGE.read_bytes()).decode("ascii")
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": ref_b64}})
    parts.append({"text": full_prompt})

    for model_name in ("gemini-2.5-flash-image", "gemini-2.0-flash-exp-image-generation"):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={gemini_key}"
        )
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for part in data["candidates"][0]["content"]["parts"]:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(base64.b64decode(inline["data"]))
                    return True
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")[:300]
            print(f"[AI Image] {model_name} HTTP {exc.code}: {err_body}")
        except Exception as exc:
            print(f"[AI Image] {model_name} xatosi: {exc}")
    return False


def _find_fallback_image() -> Path | None:
    """Pick a random existing Between Us image from queue/posted/assets as fallback."""
    candidates: list[Path] = []
    for folder_name in ("queue", "morning_queue", "night_queue", "posted"):
        folder = BASE_DIR / folder_name
        if folder.exists():
            for p in folder.iterdir():
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    candidates.append(p)
    if candidates:
        return random.choice(candidates)
    if REFERENCE_IMAGE.exists():
        return REFERENCE_IMAGE
    return None


def generate_auto_post(gemini_key: str, mode: str, tag: str) -> tuple[Path, str]:
    """Generate a fresh image + Latin Uzbek caption and return (image_path, caption)."""
    scene = _pick_scene(mode)
    full_prompt = (
        "Create a 3D Pixar/chibi-style illustration featuring the exact same two young "
        "childhood characters (faces, big brown eyes, hair) from the reference image. "
        f"New outfit and scenery: {scene}. "
        "1:1 square aspect ratio, no circular logo frame, no large text overlays."
    )

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GENERATED_DIR / f"auto_{mode}_{tag}.jpg"

    ok = _generate_image_gemini(gemini_key, full_prompt, out_path)
    if not ok:
        fallback = _find_fallback_image()
        if fallback is None:
            raise FileNotFoundError(
                "Gemini AI rasm yaratolmadi va zaxira rasm ham topilmadi."
            )
        out_path = fallback

    caption = generate_caption(gemini_key, mode, scene)
    return out_path, caption
