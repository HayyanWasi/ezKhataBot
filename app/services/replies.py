"""Fixed reply templates in English, Urdu and Roman Urdu.

Replies are never written by the LLM, so names and amounts are always exact.
"""

import re

TEXTS: dict[str, dict[str, str]] = {
    "not_registered": {
        "en": "This number isn't registered with EzKhata. Please contact the EzKhata team.",
        "roman_ur": "Yeh number EzKhata par register nahi hai. EzKhata team se rabta karein.",
        "ur": "یہ نمبر ایزی کھاتہ پر رجسٹر نہیں ہے۔ ایزی کھاتہ ٹیم سے رابطہ کریں۔",
    },
    "greeting": {
        "en": "Hi {name}! 👋 You're in *{business}*. How can I help?",
        "roman_ur": "Salam {name}! 👋 Aap *{business}* mein hain. Batayein kya karna hai?",
        "ur": "السلام علیکم {name}! 👋 آپ *{business}* میں ہیں۔ بتائیں کیا کرنا ہے؟",
    },
    "help": {
        "en": (
            "Right now I can:\n"
            "• switch shop — \"switch shop\"\n"
            "• change language — \"talk in English\"\n"
            "• remember notes — \"remember Ali is Rohaan's brother\"\n\n"
            "Khata entries are coming soon."
        ),
        "roman_ur": (
            "Abhi main yeh kar sakta hoon:\n"
            "• dukaan badalna — \"dukaan badlo\"\n"
            "• zubaan badalna — \"English mein baat karo\"\n"
            "• baatein yaad rakhna — \"yaad rakhna Ali Rohaan ka bhai hai\"\n\n"
            "Khata entries jald aa rahi hain."
        ),
        "ur": (
            "ابھی میں یہ کر سکتا ہوں:\n"
            "• دکان بدلنا — \"دکان بدلو\"\n"
            "• زبان بدلنا — \"انگریزی میں بات کرو\"\n"
            "• باتیں یاد رکھنا — \"یاد رکھنا علی روحان کا بھائی ہے\"\n\n"
            "کھاتہ اندراجات جلد آ رہے ہیں۔"
        ),
    },
    "current_business": {
        "en": "You're in *{business}*.",
        "roman_ur": "Aap abhi *{business}* mein hain.",
        "ur": "آپ ابھی *{business}* میں ہیں۔",
    },
    "your_businesses": {
        "en": "Your shops:\n{options}",
        "roman_ur": "Aapki dukaanein:\n{options}",
        "ur": "آپ کی دکانیں:\n{options}",
    },
    "choose_business": {
        "en": "Which shop?\n{options}",
        "roman_ur": "Kaun si dukaan?\n{options}",
        "ur": "کون سی دکان؟\n{options}",
    },
    "business_switched": {
        "en": "✅ Now in *{business}*.",
        "roman_ur": "✅ Ab *{business}* active hai.",
        "ur": "✅ اب *{business}* فعال ہے۔",
    },
    "only_one_business": {
        "en": "You only have one shop: *{business}*.",
        "roman_ur": "Aapki sirf ek dukaan hai: *{business}*.",
        "ur": "آپ کی صرف ایک دکان ہے: *{business}*۔",
    },
    "no_business": {
        "en": "You don't have access to any shop yet.",
        "roman_ur": "Abhi aapko kisi dukaan ka access nahi hai.",
        "ur": "ابھی آپ کو کسی دکان کی رسائی نہیں ہے۔",
    },
    "invalid_choice": {
        "en": "Please send a number from 1 to {n}.\n{options}",
        "roman_ur": "1 se {n} tak number bhejein.\n{options}",
        "ur": "1 سے {n} تک نمبر بھیجیں۔\n{options}",
    },
    "language_set": {
        "en": "✅ OK, I'll reply in English.",
        "roman_ur": "✅ Theek hai, ab Roman Urdu mein jawab dunga.",
        "ur": "✅ ٹھیک ہے، اب اردو میں جواب دوں گا۔",
    },
    "language_auto": {
        "en": "✅ OK, I'll reply in the language you write in.",
        "roman_ur": "✅ Theek hai, jis zubaan mein likhenge usi mein jawab dunga.",
        "ur": "✅ ٹھیک ہے، جس زبان میں لکھیں گے اسی میں جواب دوں گا۔",
    },
    "remembered": {
        "en": "✅ Noted.",
        "roman_ur": "✅ Yaad rakh liya.",
        "ur": "✅ یاد رکھ لیا۔",
    },
    "memories": {
        "en": "What I remember:\n{items}",
        "roman_ur": "Mujhe yeh yaad hai:\n{items}",
        "ur": "مجھے یہ یاد ہے:\n{items}",
    },
    "no_memories": {
        "en": "I haven't saved anything yet.",
        "roman_ur": "Abhi kuch yaad nahi rakha.",
        "ur": "ابھی کچھ یاد نہیں رکھا۔",
    },
    "choose_memory": {
        "en": "Which one should I forget?\n{options}",
        "roman_ur": "Kaunsi baat bhula doon?\n{options}",
        "ur": "کون سی بات بھلا دوں؟\n{options}",
    },
    "forgotten": {
        "en": "✅ Forgotten: {item}",
        "roman_ur": "✅ Bhula diya: {item}",
        "ur": "✅ بھلا دیا: {item}",
    },
    "memory_not_found": {
        "en": "I couldn't find that in my notes.",
        "roman_ur": "Yeh baat mere notes mein nahi mili.",
        "ur": "یہ بات میرے نوٹس میں نہیں ملی۔",
    },
    "cancelled": {
        "en": "OK, cancelled.",
        "roman_ur": "Theek hai, cancel kar diya.",
        "ur": "ٹھیک ہے، منسوخ کر دیا۔",
    },
    "nothing_to_cancel": {
        "en": "Nothing to cancel.",
        "roman_ur": "Cancel karne ko kuch nahi hai.",
        "ur": "منسوخ کرنے کو کچھ نہیں ہے۔",
    },
    "not_understood": {
        "en": "Sorry, I didn't understand. Send /help to see what I can do.",
        "roman_ur": "Maaf kijiye, samajh nahi aaya. /help bhej kar dekhein main kya kar sakta hoon.",
        "ur": "معاف کیجیے، سمجھ نہیں آیا۔ /help بھیج کر دیکھیں میں کیا کر سکتا ہوں۔",
    },
    "error": {
        "en": "Something went wrong. Please send your message again.",
        "roman_ur": "Kuch masla hua. Apna message dobara bhejein.",
        "ur": "کچھ مسئلہ ہوا۔ اپنا پیغام دوبارہ بھیجیں۔",
    },
}


def t(key: str, language: str, **values: object) -> str:
    templates = TEXTS[key]
    return templates.get(language, templates["en"]).format(**values)


def numbered(items: list[str]) -> str:
    return "\n".join(f"{i}) {item}" for i, item in enumerate(items, 1))


# ---------------------------------------------------------------------------
# Cheap language guess, used when no AI call happens (commands, number answers)
# ---------------------------------------------------------------------------

_URDU_SCRIPT = re.compile(r"[؀-ۿ]")
_ROMAN_URDU_WORDS = {
    "hai", "hain", "ka", "ki", "ke", "ko", "ne", "se", "mein", "mai", "kya", "kia", "karo",
    "kar", "nahi", "nhi", "haan", "han", "ji", "acha", "theek", "thik", "bhai", "paise",
    "udhaar", "udhar", "chahiye", "batao", "mujhe", "aap", "ap", "yaar", "yr", "salam",
    "madad", "dukaan", "dukan", "kitne", "kitna", "aur", "bhi", "abhi", "kal", "aaj", "tha",
}


def detect_language(text: str, default: str = "roman_ur") -> str:
    if _URDU_SCRIPT.search(text):
        return "ur"
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return default
    if any(w in _ROMAN_URDU_WORDS for w in words):
        return "roman_ur"
    return "en"
