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
            "Send me messages like:\n"
            "• \"Gave 500 to Ali\" / \"Got 300 from Ali\"\n"
            "• \"Ali's balance\" / \"all balances\"\n"
            "• \"add supplier Rohaan\" / \"undo\"\n"
            "• \"switch shop\" / \"talk in English\" / \"remember …\""
        ),
        "roman_ur": (
            "Mujhe aise likhein:\n"
            "• \"Ali ko 500 diye\" / \"Ali se 300 mile\"\n"
            "• \"Ali ka hisaab\" / \"sab ka hisaab\"\n"
            "• \"Rohaan supplier add karo\" / \"undo\"\n"
            "• \"dukaan badlo\" / \"English mein baat karo\" / \"yaad rakhna …\""
        ),
        "ur": (
            "مجھے ایسے لکھیں:\n"
            "• \"علی کو 500 دیے\" / \"علی سے 300 ملے\"\n"
            "• \"علی کا حساب\" / \"سب کا حساب\"\n"
            "• \"روحان سپلائر شامل کرو\" / \"undo\"\n"
            "• \"دکان بدلو\" / \"انگریزی میں بات کرو\" / \"یاد رکھنا …\""
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
    # ---- Party khata -------------------------------------------------------
    "owner_only": {
        "en": "Only the shop owner can do this. You can check balances.",
        "roman_ur": "Yeh sirf dukaan ka maalik kar sakta hai. Aap hisaab dekh sakte hain.",
        "ur": "یہ صرف دکان کا مالک کر سکتا ہے۔ آپ حساب دیکھ سکتے ہیں۔",
    },
    "entry_gave": {
        "en": "✅ Gave {amount} to {name} ({date})",
        "roman_ur": "✅ {name} ko {amount} diye ({date})",
        "ur": "✅ {name} کو {amount} دیے ({date})",
    },
    "entry_got": {
        "en": "✅ Got {amount} from {name} ({date})",
        "roman_ur": "✅ {name} se {amount} liye ({date})",
        "ur": "✅ {name} سے {amount} لیے ({date})",
    },
    "balance_get": {
        "en": "You will get {amount} from {name}",
        "roman_ur": "{name} se lene hain: {amount}",
        "ur": "{name} سے لینے ہیں: {amount}",
    },
    "balance_give": {
        "en": "You will give {amount} to {name}",
        "roman_ur": "{name} ko dene hain: {amount}",
        "ur": "{name} کو دینے ہیں: {amount}",
    },
    "balance_settled": {
        "en": "{name}'s account is settled",
        "roman_ur": "{name} ka hisaab barabar hai",
        "ur": "{name} کا حساب برابر ہے",
    },
    "ask_party": {
        "en": "Whose entry is this? Send the name.",
        "roman_ur": "Kis ka hisaab hai? Naam likhein.",
        "ur": "کس کا حساب ہے؟ نام لکھیں۔",
    },
    "ask_amount": {
        "en": "{name}: how much?",
        "roman_ur": "{name}: kitne paise?",
        "ur": "{name}: کتنے پیسے؟",
    },
    "ask_direction": {
        "en": "{amount}:\n1) You gave to {name}\n2) You got from {name}",
        "roman_ur": "{amount}:\n1) {name} ko diye\n2) {name} se liye",
        "ur": "{amount}:\n1) {name} کو دیے\n2) {name} سے لیے",
    },
    "ask_opening_direction": {
        "en": "Old balance {amount}:\n1) You will get from {name}\n2) You will give to {name}",
        "roman_ur": "Pehle ka {amount}:\n1) {name} se lene hain\n2) {name} ko dene hain",
        "ur": "پہلے کا {amount}:\n1) {name} سے لینے ہیں\n2) {name} کو دینے ہیں",
    },
    "ask_party_type": {
        "en": "{name} is new.\n1) Customer\n2) Supplier",
        "roman_ur": "{name} naya hai.\n1) Customer\n2) Supplier",
        "ur": "{name} نیا ہے۔\n1) گاہک\n2) سپلائر",
    },
    "choose_party": {
        "en": "Which {name}?\n{options}",
        "roman_ur": "Kaun sa {name}?\n{options}",
        "ur": "کون سا {name}؟\n{options}",
    },
    "new_party_option": {"en": "New party", "roman_ur": "Naya party", "ur": "نئی پارٹی"},
    "type_customer": {"en": "customer", "roman_ur": "customer", "ur": "گاہک"},
    "type_supplier": {"en": "supplier", "roman_ur": "supplier", "ur": "سپلائر"},
    "party_added": {
        "en": "✅ {name} added as {type}",
        "roman_ur": "✅ {name} {type} add ho gaya",
        "ur": "✅ {name} بطور {type} شامل ہو گیا",
    },
    "party_exists": {
        "en": "{name} is already a {type}. Use a fuller name (e.g. {name} Khan).",
        "roman_ur": "{name} pehle se {type} hai. Poora naam likhein (jaise {name} Khan).",
        "ur": "{name} پہلے سے {type} ہے۔ پورا نام لکھیں (جیسے {name} خان)۔",
    },
    "party_not_found": {
        "en": "No party named {name}.",
        "roman_ur": "{name} naam ki koi party nahi mili.",
        "ur": "{name} نام کی کوئی پارٹی نہیں ملی۔",
    },
    "phone_saved": {
        "en": "✅ Saved {name}'s number",
        "roman_ur": "✅ {name} ka number save ho gaya",
        "ur": "✅ {name} کا نمبر محفوظ ہو گیا",
    },
    "invalid_phone": {
        "en": "That number doesn't look right. Write it like 03001234567.",
        "roman_ur": "Number theek nahi. Aise likhein: 03001234567",
        "ur": "نمبر درست نہیں۔ ایسے لکھیں: 03001234567",
    },
    "future_date": {
        "en": "Entries can't be added for a future date.",
        "roman_ur": "Aage ki tareekh ki entry nahi ho sakti.",
        "ur": "آنے والی تاریخ کی انٹری نہیں ہو سکتی۔",
    },
    "verb_gave": {"en": "gave", "roman_ur": "diye", "ur": "دیے"},
    "verb_got": {"en": "got", "roman_ur": "liye", "ur": "لیے"},
    "verb_opening": {"en": "old bal.", "roman_ur": "pehle ka", "ur": "پہلے کا"},
    "short_get": {"en": "get {amount}", "roman_ur": "lene {amount}", "ur": "لینے {amount}"},
    "short_give": {"en": "give {amount}", "roman_ur": "dene {amount}", "ur": "دینے {amount}"},
    "short_settled": {"en": "settled", "roman_ur": "barabar", "ur": "برابر"},
    "no_entries": {
        "en": "No entries yet.",
        "roman_ur": "Abhi koi entry nahi.",
        "ur": "ابھی کوئی انٹری نہیں۔",
    },
    "party_list": {
        "en": "Total you will get: {get}\nTotal you will give: {give}\n\n{items}",
        "roman_ur": "Kul lene hain: {get}\nKul dene hain: {give}\n\n{items}",
        "ur": "کل لینے ہیں: {get}\nکل دینے ہیں: {give}\n\n{items}",
    },
    "no_parties": {
        "en": "No parties yet. Try: \"Gave 500 to Ali\"",
        "roman_ur": "Abhi koi party nahi. Likhein: \"Ali ko 500 diye\"",
        "ur": "ابھی کوئی پارٹی نہیں۔ لکھیں: \"علی کو 500 دیے\"",
    },
    "confirm_delete": {
        "en": "Delete {name}'s {amount} entry ({date})? yes/no",
        "roman_ur": "{name} ki {amount} wali entry ({date}) delete karun? haan/nahi",
        "ur": "{name} کی {amount} والی انٹری ({date}) ڈیلیٹ کروں؟ ہاں/نہیں",
    },
    "entry_deleted": {
        "en": "🗑️ Entry deleted",
        "roman_ur": "🗑️ Entry delete ho gayi",
        "ur": "🗑️ انٹری ڈیلیٹ ہو گئی",
    },
    "delete_kept": {
        "en": "OK, the entry is kept.",
        "roman_ur": "Theek hai, entry nahi hati.",
        "ur": "ٹھیک ہے، انٹری نہیں ہٹی۔",
    },
    "no_entry_to_delete": {
        "en": "No entry found to delete.",
        "roman_ur": "Delete karne ko koi entry nahi mili.",
        "ur": "ڈیلیٹ کرنے کو کوئی انٹری نہیں ملی۔",
    },
    "answer_yes_no": {
        "en": "Please reply yes or no.",
        "roman_ur": "Haan ya nahi likhein.",
        "ur": "ہاں یا نہیں لکھیں۔",
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
    if len(words) == 1:  # "undo", "ok", "list": too short to tell, keep the conversation's language
        return default
    return "en"
