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
            "• \"tea 200\" / \"3000 came in\" / \"today's sale 20000\"\n"
            "• \"Ali paid back 1000\" / \"deposited 10000 in JazzCash\"\n"
            "• \"today's cash\" / \"September cash book PDF\"\n"
            "• \"add supplier Rohaan\" / \"undo\" / \"Ali's entry was 600, not 500\"\n"
            "• \"Ali's statement for September\" / \"all parties statement\"\n"
            "• \"remind me tomorrow at 10 to pay Rohaan\" / \"my reminders\"\n"
            "• \"switch shop\" / \"talk in English\" / \"remember …\""
        ),
        "roman_ur": (
            "Mujhe aise likhein:\n"
            "• \"Ali ko 500 diye\" / \"Ali se 300 mile\"\n"
            "• \"Ali ka hisaab\" / \"sab ka hisaab\"\n"
            "• \"chai 200\" / \"3000 aaye\" / \"aaj 20000 ki sale hui\"\n"
            "• \"Ali ne 1000 wapas diye\" / \"JazzCash mein 10000 jama karaye\"\n"
            "• \"aaj ka cash\" / \"September ki cash book PDF\"\n"
            "• \"Rohaan supplier add karo\" / \"undo\" / \"Ali wali entry 500 nahi 600 thi\"\n"
            "• \"Ali ka September ka statement\" / \"sab ka statement\"\n"
            "• \"kal 10 baje yaad dilana Rohaan ko payment karni hai\" / \"meri reminders\"\n"
            "• \"dukaan badlo\" / \"English mein baat karo\" / \"yaad rakhna …\""
        ),
        "ur": (
            "مجھے ایسے لکھیں:\n"
            "• \"علی کو 500 دیے\" / \"علی سے 300 ملے\"\n"
            "• \"علی کا حساب\" / \"سب کا حساب\"\n"
            "• \"چائے 200\" / \"3000 آئے\" / \"آج 20000 کی سیل ہوئی\"\n"
            "• \"علی نے 1000 واپس دیے\" / \"آج کا کیش\"\n"
            "• \"روحان سپلائر شامل کرو\" / \"undo\"\n"
            "• \"علی کا ستمبر کا اسٹیٹمنٹ\" / \"سب کا اسٹیٹمنٹ\"\n"
            "• \"کل 10 بجے یاد دلانا روحان کو پیمنٹ کرنی ہے\" / \"میری یاد دہانیاں\"\n"
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
        "en": "Only the shop owner can do this. You can check balances and add cash entries.",
        "roman_ur": "Yeh sirf dukaan ka maalik kar sakta hai. Aap hisaab dekh sakte hain aur cash entries kar sakte hain.",
        "ur": "یہ صرف دکان کا مالک کر سکتا ہے۔ آپ حساب دیکھ سکتے ہیں اور کیش انٹریاں کر سکتے ہیں۔",
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
    # ---- Statements -------------------------------------------------------
    "statement_ready": {
        "en": "📄 {name}'s statement ({period})",
        "roman_ur": "📄 {name} ka statement ({period})",
        "ur": "📄 {name} کا اسٹیٹمنٹ ({period})",
    },
    "statement_all_ready": {
        "en": "📄 All parties statement ({period})\nTotal you will get: {get}\nTotal you will give: {give}",
        "roman_ur": "📄 Sab parties ka statement ({period})\nKul lene hain: {get}\nKul dene hain: {give}",
        "ur": "📄 سب پارٹیوں کا اسٹیٹمنٹ ({period})\nکل لینے ہیں: {get}\nکل دینے ہیں: {give}",
    },
    "period_full": {"en": "full khata", "roman_ur": "poora khata", "ur": "پورا کھاتہ"},
    # ---- Reminders --------------------------------------------------------
    "reminder_set": {
        "en": "⏰ I'll remind you on {when}: {text}",
        "roman_ur": "⏰ {when} yaad dilaunga: {text}",
        "ur": "⏰ {when} یاد دلاؤں گا: {text}",
    },
    "reminder_fire": {
        "en": "⏰ Reminder: {text}",
        "roman_ur": "⏰ Yaad dihani: {text}",
        "ur": "⏰ یاد دہانی: {text}",
    },
    "reminders_list": {
        "en": "Your reminders:\n{items}",
        "roman_ur": "Aapki reminders:\n{items}",
        "ur": "آپ کی یاد دہانیاں:\n{items}",
    },
    "no_reminders": {
        "en": "No reminders set.",
        "roman_ur": "Koi reminder set nahi hai.",
        "ur": "کوئی یاد دہانی نہیں ہے۔",
    },
    "reminder_cancelled": {
        "en": "✅ Reminder cancelled: {text}",
        "roman_ur": "✅ Reminder cancel ho gayi: {text}",
        "ur": "✅ یاد دہانی منسوخ: {text}",
    },
    "reminder_not_found": {
        "en": "No reminder matches that.",
        "roman_ur": "Aisi koi reminder nahi mili.",
        "ur": "ایسی کوئی یاد دہانی نہیں ملی۔",
    },
    "choose_reminder": {
        "en": "Which reminder?\n{options}",
        "roman_ur": "Kaun si reminder?\n{options}",
        "ur": "کون سی یاد دہانی؟\n{options}",
    },
    "ask_reminder_what": {
        "en": "What should I remind you about?",
        "roman_ur": "Kya yaad dilaun?",
        "ur": "کیا یاد دلاؤں؟",
    },
    "ask_reminder_when": {
        "en": "When should I remind you? (e.g. tomorrow 10 am)",
        "roman_ur": "Kab yaad dilaun? (jaise: kal 10 baje)",
        "ur": "کب یاد دلاؤں؟ (جیسے: کل 10 بجے)",
    },
    "past_time": {
        "en": "That time has already passed. Please give a future time.",
        "roman_ur": "Yeh waqt guzar chuka hai. Aage ka waqt batayein.",
        "ur": "یہ وقت گزر چکا ہے۔ آگے کا وقت بتائیں۔",
    },
    "word_and": {"en": "and", "roman_ur": "aur", "ur": "اور"},
    # ---- Image entries (OCR) ----------------------------------------------
    "image_found": {
        "en": "📷 Found {n} entries:",
        "roman_ur": "📷 {n} entries mili:",
        "ur": "📷 {n} انٹریاں ملیں:",
    },
    "image_section_party": {"en": "Party khata:", "roman_ur": "Party khata:", "ur": "پارٹی کھاتہ:"},
    "image_section_later": {
        "en": "Can't be saved yet (Cash Book coming soon):",
        "roman_ur": "Abhi save nahi hongi (Cash Book jald aa raha hai):",
        "ur": "ابھی محفوظ نہیں ہوں گی (کیش بک جلد آ رہی ہے):",
    },
    "image_row_gave": {
        "en": "{date} · Gave {amount} to {name}",
        "roman_ur": "{date} · {name} ko {amount} diye",
        "ur": "{date} · {name} کو {amount} دیے",
    },
    "image_row_got": {
        "en": "{date} · Got {amount} from {name}",
        "roman_ur": "{date} · {name} se {amount} liye",
        "ur": "{date} · {name} سے {amount} لیے",
    },
    "image_new": {"en": "(new)", "roman_ur": "(naya)", "ur": "(نیا)"},
    "image_missing_amount": {"en": "no amount", "roman_ur": "amount nahi mila", "ur": "رقم نہیں ملی"},
    "image_missing_direction": {
        "en": "gave or got not clear",
        "roman_ur": "diye ya liye clear nahi",
        "ur": "دیے یا لیے واضح نہیں",
    },
    "image_missing_party": {"en": "no name", "roman_ur": "naam nahi mila", "ur": "نام نہیں ملا"},
    "image_missing_choice": {"en": "which {name}?", "roman_ur": "kaun sa {name}?", "ur": "کون سا {name}؟"},
    "image_ask_later": {
        "en": "I'll ask after saving",
        "roman_ur": "baad mein poochunga",
        "ur": "بعد میں پوچھوں گا",
    },
    "image_total_mismatch": {
        "en": "⚠️ The sheet's total is {written}, the entries add up to {sum}. Please check once.",
        "roman_ur": "⚠️ Sheet ka total {written} hai, entries ka jor {sum}. Ek baar check kar lein.",
        "ur": "⚠️ شیٹ کا ٹوٹل {written} ہے، انٹریوں کا جوڑ {sum}۔ ایک بار چیک کر لیں۔",
    },
    "image_confirm": {"en": "Save them? yes/no", "roman_ur": "Save karun? haan/nahi", "ur": "محفوظ کروں؟ ہاں/نہیں"},
    "image_new_names": {
        "en": "New names: {names}\n1) All customers\n2) All suppliers\n3) Skip their entries",
        "roman_ur": "Naye naam: {names}\n1) Sab customer\n2) Sab supplier\n3) Inki entries chhor do",
        "ur": "نئے نام: {names}\n1) سب گاہک\n2) سب سپلائر\n3) ان کی انٹریاں چھوڑ دو",
    },
    "image_saved": {
        "en": "✅ Saved {n} entries",
        "roman_ur": "✅ {n} entries save ho gayin",
        "ur": "✅ {n} انٹریاں محفوظ ہو گئیں",
    },
    "image_nothing_found": {
        "en": "I couldn't find any entries in this photo.",
        "roman_ur": "Tasveer mein koi entry nahi mili.",
        "ur": "تصویر میں کوئی انٹری نہیں ملی۔",
    },
    "image_cancelled": {
        "en": "OK, nothing was saved.",
        "roman_ur": "Theek hai, kuch save nahi kiya.",
        "ur": "ٹھیک ہے، کچھ محفوظ نہیں کیا۔",
    },
    "ocr_unavailable": {
        "en": "Reading photos isn't switched on yet. Please send the entries as text.",
        "roman_ur": "Tasveer parhne ki service abhi on nahi. Entries text mein bhej dein.",
        "ur": "تصویر پڑھنے کی سروس ابھی آن نہیں۔ انٹریاں ٹیکسٹ میں بھیج دیں۔",
    },
    "ocr_failed": {
        "en": "I couldn't read this photo. Please send a clearer photo.",
        "roman_ur": "Tasveer parh nahi saka. Saaf tasveer dobara bhejein.",
        "ur": "تصویر پڑھ نہیں سکا۔ صاف تصویر دوبارہ بھیجیں۔",
    },
    "ocr_too_big": {
        "en": "This photo is too large (over 10 MB).",
        "roman_ur": "Tasveer bohat bari hai (10 MB se zyada).",
        "ur": "تصویر بہت بڑی ہے (10 MB سے زیادہ)۔",
    },
    "cat_expense": {"en": "Expense", "roman_ur": "Kharcha", "ur": "خرچہ"},
    "cat_cash_in": {"en": "Cash in", "roman_ur": "Cash jama", "ur": "کیش جمع"},
    "cat_cash_out": {"en": "Cash out", "roman_ur": "Cash nikala", "ur": "کیش نکالا"},
    "cat_bank": {"en": "Bank", "roman_ur": "Bank", "ur": "بینک"},
    "cat_sale": {"en": "Counter sale", "roman_ur": "Counter sale", "ur": "کاؤنٹر سیل"},
    "image_section_cash": {"en": "Cash book:", "roman_ur": "Cash book:", "ur": "کیش بک:"},
    "image_section_bank": {"en": "Bank:", "roman_ur": "Bank:", "ur": "بینک:"},
    "image_missing_category": {"en": "which category?", "roman_ur": "kaunsi category?", "ur": "کون سی کیٹیگری؟"},
    "image_missing_bank": {"en": "which bank?", "roman_ur": "kaunsa bank?", "ur": "کون سا بینک؟"},
    "image_missing_in_out": {"en": "in or out?", "roman_ur": "aaye ya gaye?", "ur": "آئے یا گئے؟"},
    # ---- Cash book + banks ------------------------------------------------
    "cash_name": {"en": "Cash", "roman_ur": "Cash", "ur": "کیش"},
    "ask_opening_cash": {
        "en": "First, how much cash is in the shop right now? (send 0 or skip if you don't know)",
        "roman_ur": "Pehle bata dein, abhi dukaan mein kitna cash hai? (pata nahi to 0 ya skip likhein)",
        "ur": "پہلے بتا دیں، ابھی دکان میں کتنا کیش ہے؟ (معلوم نہیں تو 0 لکھیں)",
    },
    "ask_cash_amount": {"en": "How much?", "roman_ur": "Kitne paise?", "ur": "کتنے پیسے؟"},
    "ask_cash_direction": {
        "en": "{amount}:\n1) Came in\n2) Went out",
        "roman_ur": "{amount}:\n1) Aaye (cash in)\n2) Gaye (cash out)",
        "ur": "{amount}:\n1) آئے (کیش اِن)\n2) گئے (کیش آؤٹ)",
    },
    "ask_category": {
        "en": "Which category for \"{word}\"?\n{options}\nOr send a new name.",
        "roman_ur": "\"{word}\" kis category mein daalun?\n{options}\nYa naya naam likhein.",
        "ur": "\"{word}\" کس کیٹیگری میں ڈالوں؟\n{options}\nیا نیا نام لکھیں۔",
    },
    "new_category_option": {"en": "{name} (new)", "roman_ur": "{name} (nayi)", "ur": "{name} (نئی)"},
    "choose_bank": {"en": "Which bank?\n{options}", "roman_ur": "Kaunsa bank?\n{options}", "ur": "کون سا بینک؟\n{options}"},
    "confirm_new_bank": {
        "en": "{name} is a new account. Add it? yes/no",
        "roman_ur": "{name} naya account hai, add karun? haan/nahi",
        "ur": "{name} نیا اکاؤنٹ ہے، شامل کروں؟ ہاں/نہیں",
    },
    "ask_bank_name": {
        "en": "Which bank or wallet? (e.g. JazzCash)",
        "roman_ur": "Kaunsa bank ya wallet? (jaise JazzCash)",
        "ur": "کون سا بینک یا والٹ؟ (جیسے JazzCash)",
    },
    "bank_owner_only": {
        "en": "Only the shop owner can add a new bank.",
        "roman_ur": "Naya bank sirf dukaan ka maalik add kar sakta hai.",
        "ur": "نیا بینک صرف دکان کا مالک شامل کر سکتا ہے۔",
    },
    "money_in_saved": {
        "en": "✅ In: {amount}{detail} ({date})",
        "roman_ur": "✅ {amount} aaye{detail} ({date})",
        "ur": "✅ {amount} آئے{detail} ({date})",
    },
    "money_out_saved": {
        "en": "✅ Out: {amount}{detail} ({date})",
        "roman_ur": "✅ {amount} gaye{detail} ({date})",
        "ur": "✅ {amount} گئے{detail} ({date})",
    },
    "sale_saved": {
        "en": "✅ Sale {amount} ({date})",
        "roman_ur": "✅ {amount} ki sale ({date})",
        "ur": "✅ {amount} کی سیل ({date})",
    },
    "ask_transfer_direction": {
        "en": "{amount} with {bank}:\n1) Cash deposited into {bank}\n2) Cash taken out of {bank}",
        "roman_ur": "{amount} {bank}:\n1) Cash {bank} mein jama kiya\n2) {bank} se cash nikala",
        "ur": "{amount} {bank}:\n1) کیش {bank} میں جمع کیا\n2) {bank} سے کیش نکالا",
    },
    "transfer_saved": {
        "en": "✅ {amount}: {source} → {target} ({date})",
        "roman_ur": "✅ {amount}: {source} → {target} ({date})",
        "ur": "✅ {amount}: {source} ← {target} ({date})",
    },
    "bank_added": {"en": "✅ {name} added", "roman_ur": "✅ {name} add ho gaya", "ur": "✅ {name} شامل ہو گیا"},
    "bank_exists": {
        "en": "{name} is already added.",
        "roman_ur": "{name} pehle se add hai.",
        "ur": "{name} پہلے سے شامل ہے۔",
    },
    "bank_not_found": {
        "en": "No bank named {name}.",
        "roman_ur": "{name} naam ka koi bank nahi mila.",
        "ur": "{name} نام کا کوئی بینک نہیں ملا۔",
    },
    "money_report": {
        "en": "📒 {name} · {period}\nOpening: {opening}\nIn: {money_in}\nOut: {money_out}\nBalance: {closing}",
        "roman_ur": "📒 {name} · {period}\nShuru mein: {opening}\nAaye: {money_in}\nGaye: {money_out}\nBaqi: {closing}",
        "ur": "📒 {name} · {period}\nشروع میں: {opening}\nآئے: {money_in}\nگئے: {money_out}\nباقی: {closing}",
    },
    "report_expenses": {"en": "Expenses:\n{items}", "roman_ur": "Kharche:\n{items}", "ur": "خرچے:\n{items}"},
    "report_other_accounts": {
        "en": "Other accounts:\n{items}",
        "roman_ur": "Baqi accounts:\n{items}",
        "ur": "باقی اکاؤنٹس:\n{items}",
    },
    "no_money_yet": {
        "en": "No cash book entries yet. Try: \"tea 200\" or \"3000 came in\"",
        "roman_ur": "Abhi cash book mein koi entry nahi. Likhein: \"chai 200\" ya \"3000 aaye\"",
        "ur": "ابھی کیش بک میں کوئی انٹری نہیں۔ لکھیں: \"چائے 200\"",
    },
    "entry_cash_in": {"en": "Cash in", "roman_ur": "Cash in", "ur": "کیش اِن"},
    "entry_cash_out": {"en": "Cash out", "roman_ur": "Cash out", "ur": "کیش آؤٹ"},
    "entry_sale": {"en": "Sale", "roman_ur": "Sale", "ur": "سیل"},
    "entry_transfer": {"en": "Transfer", "roman_ur": "Transfer", "ur": "ٹرانسفر"},
    "entry_opening_balance": {"en": "Opening balance", "roman_ur": "Shuru ka balance", "ur": "ابتدائی بیلنس"},
    "entry_adjustment": {"en": "Adjustment", "roman_ur": "Adjustment", "ur": "ایڈجسٹمنٹ"},
    # ---- Edit / delete / photo -------------------------------------------
    "confirm_edit": {
        "en": "{name} entry ({date}): {changes}. OK? yes/no",
        "roman_ur": "{name} wali entry ({date}): {changes}. Theek hai? haan/nahi",
        "ur": "{name} والی انٹری ({date}): {changes}۔ ٹھیک ہے؟ ہاں/نہیں",
    },
    "no_entry_found": {
        "en": "I couldn't find that entry.",
        "roman_ur": "Aisi koi entry nahi mili.",
        "ur": "ایسی کوئی انٹری نہیں ملی۔",
    },
    "edit_nothing": {
        "en": "What should I change? e.g. \"Ali's entry was 600, not 500\"",
        "roman_ur": "Kya badalna hai? Jaise: \"Ali wali entry 500 nahi 600 thi\"",
        "ur": "کیا بدلنا ہے؟ جیسے: \"علی والی انٹری 500 نہیں 600 تھی\"",
    },
    "entry_edited": {"en": "✏️ Entry updated", "roman_ur": "✏️ Entry theek ho gayi", "ur": "✏️ انٹری درست ہو گئی"},
    "edit_kept": {"en": "OK, nothing changed.", "roman_ur": "Theek hai, kuch nahi badla.", "ur": "ٹھیک ہے، کچھ نہیں بدلا۔"},
    "staff_own_cash_only": {
        "en": "You can only change your own cash entries.",
        "roman_ur": "Aap sirf apni cash entries badal sakte hain.",
        "ur": "آپ صرف اپنی کیش انٹریاں بدل سکتے ہیں۔",
    },
    "entry_photo": {
        "en": "📷 Photo of {name} {amount} ({date})",
        "roman_ur": "📷 {name} {amount} ({date}) ki photo",
        "ur": "📷 {name} {amount} ({date}) کی تصویر",
    },
    "no_entry_photo": {
        "en": "No photo found for that entry.",
        "roman_ur": "Is entry ki koi photo nahi mili.",
        "ur": "اس انٹری کی کوئی تصویر نہیں ملی۔",
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
