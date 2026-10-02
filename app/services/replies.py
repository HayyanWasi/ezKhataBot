"""Fixed reply templates in English, Urdu and Roman Urdu.

Replies are never written by the LLM, so names and amounts are always exact.
"""

import re

TEXTS: dict[str, dict[str, str]] = {
    "text_or_photo_only": {
        "en": "For now please send text or a photo.",
        "roman_ur": "Abhi sirf text ya photo bhejein.",
        "ur": "ابھی صرف ٹیکسٹ یا تصویر بھیجیں۔",
    },
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
            "• \"add item socks, sell 30, 100 pcs\" / \"50 socks from Bilal on credit\" / \"stock list\"\n"
            "• \"bill for Rohaan: 50 socks, 10% discount\" / \"sold 2 socks\" / \"show bills\"\n"
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
            "• \"socks add karo 30 ki bechta hun 100 pcs\" / \"Bilal se 50 socks udhaar aae\" / \"stock dikhao\"\n"
            "• \"Rohaan ka bill: 50 socks, 10% discount, 1000 cash baqi udhaar\" / \"2 socks bech diye\" / \"bills dikhao\"\n"
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
            "• \"جرابیں شامل کرو، 30 کی بیچتا ہوں\" / \"50 جرابیں آئیں\" / \"اسٹاک دکھاؤ\"\n"
            "• \"روحان کا بل: 50 جرابیں، 10% ڈسکاؤنٹ\" / \"2 جرابیں بیچیں\" / \"بل دکھاؤ\"\n"
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
    "recent_head": {"en": "🕘 *Latest entries*", "roman_ur": "🕘 *Haaliya entries*", "ur": "🕘 *حالیہ انٹریاں*"},
    "recent_none": {"en": "No entries yet.", "roman_ur": "Abhi koi entry nahi.", "ur": "ابھی کوئی انٹری نہیں۔"},
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
    "image_bill_mismatch": {
        "en": "⚠️ The bill total is {total}, but its items add up to {sum}. Please check the photo once.",
        "roman_ur": "⚠️ Bill ka total {total} hai, lekin items ka jor {sum} hai. Ek baar photo check kar lein.",
        "ur": "⚠️ بل کا ٹوٹل {total} ہے، لیکن آئٹمز کا جوڑ {sum} ہے۔ ایک بار تصویر چیک کر لیں۔",
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
    # ------------------------------------------------------------------ bills
    "bill_which_items": {
        "en": "Which items, and how many? e.g. \"Rohaan ka bill: 50 socks, 2 belt\"",
        "roman_ur": "Bill mein kaunse items aur kitne? Jaise: \"Rohaan ka bill: 50 socks, 2 belt\"",
        "ur": "بل میں کون سے آئٹم اور کتنے؟ جیسے: \"روحان کا بل: 50 جرابیں، 2 بیلٹ\"",
    },
    "ask_bill_rate": {
        "en": "Sale rate of *{name}*? (price of 1 {unit})",
        "roman_ur": "*{name}* ka bechne ka rate? (1 {unit} ki qeemat)",
        "ur": "*{name}* کا فروخت ریٹ؟ (1 {unit} کی قیمت)",
    },
    "ask_bill_pay": {
        "en": "Bill {total}: how was it paid?\n1) Cash\n2) Online (bank)\n3) Udhaar",
        "roman_ur": "Bill {total}: paise kaise mile?\n1) Cash\n2) Online (bank)\n3) Udhaar",
        "ur": "بل {total}: پیسے کیسے ملے؟\n1) کیش\n2) آن لائن (بینک)\n3) ادھار",
    },
    "ask_bill_customer": {
        "en": "Udhaar needs a name: whose bill is it?",
        "roman_ur": "Udhaar ke liye naam chahiye: kis customer ka bill hai?",
        "ur": "ادھار کے لیے نام چاہیے: کس گاہک کا بل ہے؟",
    },
    "confirm_new_customer": {
        "en": "*{name}* is a new customer. Add? (yes/no)",
        "roman_ur": "*{name}* naya customer hai. Add karun? (haan/nahi)",
        "ur": "*{name}* نیا گاہک ہے۔ شامل کروں؟ (ہاں/نہیں)",
    },
    "ask_shop_details": {
        "en": "For your bills (asked once): write the shop's address and phone number. Or \"skip\".",
        "roman_ur": "Bill ke liye (sirf ek dafa): dukaan ka address aur phone number likhein. Ya \"skip\" likhein.",
        "ur": "بل کے لیے (صرف ایک دفعہ): دکان کا پتہ اور فون نمبر لکھیں۔ یا \"skip\" لکھیں۔",
    },
    "bill_discount_too_big": {
        "en": "The discount is more than the bill. Please send the bill again.",
        "roman_ur": "Discount bill se zyada hai. Bill dobara bhejein.",
        "ur": "ڈسکاؤنٹ بل سے زیادہ ہے۔ بل دوبارہ بھیجیں۔",
    },
    "bill_head": {
        "en": "🧾 *Bill #{no}* · {name} · {date}",
        "roman_ur": "🧾 *Bill #{no}* · {name} · {date}",
        "ur": "🧾 *بل #{no}* · {name} · {date}",
    },
    "bill_cancelled_tag": {"en": "❌ CANCELLED", "roman_ur": "❌ CANCEL", "ur": "❌ منسوخ"},
    "bill_subtotal": {"en": "Total: {amount}", "roman_ur": "Total: {amount}", "ur": "ٹوٹل: {amount}"},
    "bill_discount": {
        "en": "Discount{pct}: -{amount}", "roman_ur": "Discount{pct}: -{amount}", "ur": "ڈسکاؤنٹ{pct}: -{amount}",
    },
    "bill_tax": {"en": "Tax{pct}: +{amount}", "roman_ur": "Tax{pct}: +{amount}", "ur": "ٹیکس{pct}: +{amount}"},
    "bill_total": {"en": "*Grand total: {amount}*", "roman_ur": "*Kul: {amount}*", "ur": "*کل: {amount}*"},
    "bill_paid_full": {"en": "✅ Paid ({how})", "roman_ur": "✅ Poore paise mil gae ({how})", "ur": "✅ پورے پیسے مل گئے ({how})"},
    "bill_paid_part": {
        "en": "Received: {paid} · Due: {balance}",
        "roman_ur": "Mila: {paid} · Baqi: {balance}",
        "ur": "ملا: {paid} · باقی: {balance}",
    },
    "bill_online": {"en": "online", "roman_ur": "online", "ur": "آن لائن"},
    "bills_head": {"en": "🧾 *Bills*{name} · {period}", "roman_ur": "🧾 *Bills*{name} · {period}", "ur": "🧾 *بل*{name} · {period}"},
    "bills_total": {
        "en": "Total sale: *{total}* ({n} bills: {bills})",
        "roman_ur": "Kul sale: *{total}* ({n} bills: {bills})",
        "ur": "کل سیل: *{total}* ({n} بل: {bills})",
    },
    "bills_cash_sales": {
        "en": "+ cash sales without a bill: {amount}",
        "roman_ur": "+ baghair bill ki cash sale: {amount}",
        "ur": "+ بغیر بل کی کیش سیل: {amount}",
    },
    "bill_due": {"en": "due {amount}", "roman_ur": "baqi {amount}", "ur": "باقی {amount}"},
    "no_bills": {"en": "No bills in this period.", "roman_ur": "Is dauran koi bill nahi.", "ur": "اس دوران کوئی بل نہیں۔"},
    "bill_not_found": {"en": "No bill #{no}.", "roman_ur": "Bill #{no} nahi mila.", "ur": "بل #{no} نہیں ملا۔"},
    "ask_bill_no": {
        "en": "Which bill number? e.g. \"Bill 3 cancel karo\"",
        "roman_ur": "Kaunsa bill number? Jaise: \"Bill 3 cancel karo\"",
        "ur": "کون سا بل نمبر؟ جیسے: \"بل 3 کینسل کرو\"",
    },
    "bill_edit_cancel": {
        "en": "A bill can't be changed. Cancel it (\"Bill {no} cancel karo\") and make it again.",
        "roman_ur": "Bill badla nahi ja sakta. Isay cancel karein (\"Bill {no} cancel karo\") aur naya bill banayein.",
        "ur": "بل بدلا نہیں جا سکتا۔ اسے کینسل کریں (\"بل {no} کینسل کرو\") اور نیا بل بنائیں۔",
    },
    "confirm_cancel_bill": {
        "en": "Cancel Bill #{no} ({name}, {amount})? Stock, cash and khata will go back. (yes/no)",
        "roman_ur": "Bill #{no} ({name}, {amount}) cancel karun? Stock, cash aur khata wapas ho jaenge. (haan/nahi)",
        "ur": "بل #{no} ({name}، {amount}) کینسل کروں؟ اسٹاک، کیش اور کھاتہ واپس ہو جائیں گے۔ (ہاں/نہیں)",
    },
    "bill_cancelled": {"en": "❌ Bill #{no} cancelled", "roman_ur": "❌ Bill #{no} cancel ho gaya", "ur": "❌ بل #{no} کینسل ہو گیا"},
    "bill_already_cancelled": {
        "en": "Bill #{no} is already cancelled.",
        "roman_ur": "Bill #{no} pehle se cancel hai.",
        "ur": "بل #{no} پہلے سے کینسل ہے۔",
    },
    "move_bill": {"en": "Sold (bill)", "roman_ur": "Bill se bika", "ur": "بل سے بکا"},
    "entry_bill": {"en": "Bill", "roman_ur": "Bill", "ur": "بل"},
    # ------------------------------------------------------------------ stock
    "barcode_unreadable": {
        "en": "Couldn't read the barcode. Send a clear, close photo with the whole barcode in it.",
        "roman_ur": "Barcode saaf nahi parha gaya. Poora barcode frame mein le kar qareeb se saaf photo bhejein.",
        "ur": "بارکوڈ صاف نہیں پڑھا گیا۔ پورا بارکوڈ فریم میں لے کر قریب سے صاف تصویر بھیجیں۔",
    },
    "ask_barcode_item": {
        "en": "🔖 {code}\nWhich item is this barcode for? Write its name.",
        "roman_ur": "🔖 {code}\nYeh barcode kis item ka hai? Naam likhein.",
        "ur": "🔖 {code}\nیہ بارکوڈ کس آئٹم کا ہے؟ نام لکھیں۔",
    },
    "barcode_saved": {
        "en": "🔖 Barcode {code} saved on *{name}*",
        "roman_ur": "🔖 Barcode {code} *{name}* pe save ho gaya",
        "ur": "🔖 بارکوڈ {code} *{name}* پر محفوظ ہو گیا",
    },
    "barcode_taken": {
        "en": "Barcode {code} is already on *{name}*.",
        "roman_ur": "Barcode {code} pehle se *{name}* pe hai.",
        "ur": "بارکوڈ {code} پہلے سے *{name}* پر ہے۔",
    },
    "item_photo_saved": {
        "en": "📷 Photo saved for *{name}*",
        "roman_ur": "📷 *{name}* ki photo save ho gayi",
        "ur": "📷 *{name}* کی تصویر محفوظ ہو گئی",
    },
    "stock_change_below_zero": {
        "en": "❌ Can't: *{name}* would go below 0 (only {qty} {unit} in stock now). Nothing changed.",
        "roman_ur": "❌ Nahi ho sakta: *{name}* ka stock 0 se neeche chala jaega (abhi {qty} {unit} hain). Kuch nahi badla.",
        "ur": "❌ نہیں ہو سکتا: *{name}* کا اسٹاک 0 سے نیچے چلا جائے گا (ابھی {qty} {unit} ہیں)۔ کچھ نہیں بدلا۔",
    },
    "edit_qty_one_item": {
        "en": "This entry has several items. Delete it (\"undo\") and send it again.",
        "roman_ur": "Is entry mein kai items hain. Isay delete (\"undo\") kar ke dobara bhejein.",
        "ur": "اس انٹری میں کئی آئٹم ہیں۔ اسے ڈیلیٹ (\"undo\") کر کے دوبارہ بھیجیں۔",
    },
    "item_added": {
        "en": "✅ Item added: *{name}*{category}",
        "roman_ur": "✅ Item add ho gaya: *{name}*{category}",
        "ur": "✅ آئٹم شامل ہو گیا: *{name}*{category}",
    },
    "item_category_hint": {
        "en": "(To change the category, write e.g. \"socks category Kapre karo\")",
        "roman_ur": "(Category badalni ho tou likhein, jaise: \"socks ki category Kapre karo\")",
        "ur": "(کیٹیگری بدلنی ہو تو لکھیں، جیسے: \"جرابوں کی کیٹیگری کپڑے کرو\")",
    },
    "item_exists": {
        "en": "*{name}* is already in your stock ({qty} {unit}).",
        "roman_ur": "*{name}* pehle se stock mein hai ({qty} {unit}).",
        "ur": "*{name}* پہلے سے اسٹاک میں ہے ({qty} {unit})۔",
    },
    "item_exists_short": {
        "en": "Another item is already called *{name}*.",
        "roman_ur": "*{name}* naam ka item pehle se hai.",
        "ur": "*{name}* نام کا آئٹم پہلے سے ہے۔",
    },
    "stock_qty": {"en": "Stock: {qty} {unit}", "roman_ur": "Stock: {qty} {unit}", "ur": "اسٹاک: {qty} {unit}"},
    "sale_price": {"en": "Sale {amount}", "roman_ur": "Sale {amount}", "ur": "فروخت {amount}"},
    "purchase_price": {"en": "Purchase {amount}", "roman_ur": "Khareed {amount}", "ur": "خرید {amount}"},
    "ask_unit": {
        "en": "What is the unit of *{name}*?\n{options}\nOr write it (e.g. bori, gaz)",
        "roman_ur": "*{name}* ka unit kya hai?\n{options}\nYa khud likhein (jaise bori, gaz)",
        "ur": "*{name}* کی اکائی کیا ہے؟\n{options}\nیا خود لکھیں (جیسے بوری، گز)",
    },
    "ask_unit_new": {
        "en": "*{name}* is a new item. What is its unit?\n{options}\nOr write it (e.g. bori, gaz)",
        "roman_ur": "*{name}* naya item hai. Iska unit kya hai?\n{options}\nYa khud likhein (jaise bori, gaz)",
        "ur": "*{name}* نیا آئٹم ہے۔ اس کی اکائی کیا ہے؟\n{options}\nیا خود لکھیں (جیسے بوری، گز)",
    },
    "choose_item": {
        "en": "Which item do you mean by *{word}*?\n{options}",
        "roman_ur": "*{word}* se kaunsa item?\n{options}",
        "ur": "*{word}* سے کون سا آئٹم؟\n{options}",
    },
    "new_item_option": {"en": "A new item", "roman_ur": "Naya item", "ur": "نیا آئٹم"},
    "ask_same_item": {
        "en": "Do you mean *{name}* by *{word}*? (yes/no)",
        "roman_ur": "*{word}* se matlab *{name}* hai? (haan/nahi)",
        "ur": "*{word}* سے مراد *{name}* ہے؟ (ہاں/نہیں)",
    },
    "item_not_found": {
        "en": "No item called *{name}* in your stock. Send \"stock list\" to see your items.",
        "roman_ur": "*{name}* naam ka koi item stock mein nahi. Items dekhne ke liye \"stock dikhao\" likhein.",
        "ur": "*{name}* نام کا کوئی آئٹم اسٹاک میں نہیں۔ آئٹم دیکھنے کے لیے \"اسٹاک دکھاؤ\" لکھیں۔",
    },
    "stock_which_items": {
        "en": "Which items, and how many? e.g. \"50 socks aae\"",
        "roman_ur": "Kaunse items aur kitne? Jaise: \"50 socks aae\"",
        "ur": "کون سے آئٹم اور کتنے؟ جیسے: \"50 جرابیں آئیں\"",
    },
    "ask_stock_qty": {
        "en": "How many {unit} of *{name}*?",
        "roman_ur": "*{name}* kitne {unit}?",
        "ur": "*{name}* کتنے {unit}؟",
    },
    "ask_stock_pay": {
        "en": "{items}: how was it paid?\n1) Udhaar (credit)\n2) Cash\n3) Online (bank)\n4) Stock only, no money",
        "roman_ur": "{items}: paise kaise diye?\n1) Udhaar\n2) Cash\n3) Online (bank)\n4) Sirf stock, paison ka hisaab nahi",
        "ur": "{items}: پیسے کیسے دیے؟\n1) ادھار\n2) کیش\n3) آن لائن (بینک)\n4) صرف اسٹاک، پیسوں کا حساب نہیں",
    },
    "ask_stock_supplier": {
        "en": "From which supplier? Write the name.",
        "roman_ur": "Kis supplier se? Naam likhein.",
        "ur": "کس سپلائر سے؟ نام لکھیں۔",
    },
    "confirm_new_supplier": {
        "en": "*{name}* is a new supplier. Add? (yes/no)",
        "roman_ur": "*{name}* naya supplier hai. Add karun? (haan/nahi)",
        "ur": "*{name}* نیا سپلائر ہے۔ شامل کروں؟ (ہاں/نہیں)",
    },
    "ask_stock_rate": {
        "en": "Purchase rate of *{name}*? (price of 1 {unit})",
        "roman_ur": "*{name}* ka rate? (1 {unit} ki khareed qeemat)",
        "ur": "*{name}* کا ریٹ؟ (1 {unit} کی خرید قیمت)",
    },
    "stock_owner_only_money": {
        "en": "Only the owner can add stock on udhaar or through a bank. You can add it with cash, or as stock only.",
        "roman_ur": "Udhaar ya bank se stock sirf malik add kar sakta hai. Aap cash ya \"sirf stock\" se add kar sakte hain.",
        "ur": "ادھار یا بینک سے اسٹاک صرف مالک شامل کر سکتا ہے۔ آپ کیش یا \"صرف اسٹاک\" سے شامل کر سکتے ہیں۔",
    },
    "stock_short": {
        "en": "❌ Only {qty} {unit} of *{name}* in stock. Nothing saved.",
        "roman_ur": "❌ *{name}* sirf {qty} {unit} hain. Kuch save nahi hua.",
        "ur": "❌ *{name}* صرف {qty} {unit} ہیں۔ کچھ محفوظ نہیں ہوا۔",
    },
    "stock_in_saved": {
        "en": "✅ Stock in ({date})",
        "roman_ur": "✅ Stock aa gaya ({date})",
        "ur": "✅ اسٹاک آ گیا ({date})",
    },
    "stock_out_saved": {
        "en": "✅ Stock out ({date})",
        "roman_ur": "✅ Stock kam kar diya ({date})",
        "ur": "✅ اسٹاک کم کر دیا ({date})",
    },
    "stock_total": {"en": "💰 Total: {amount}", "roman_ur": "💰 Kul: {amount}", "ur": "💰 کل: {amount}"},
    "low_stock_warning": {
        "en": "⚠️ Low stock: *{name}* only {qty} {unit} left",
        "roman_ur": "⚠️ *{name}* sirf {qty} {unit} reh gae",
        "ur": "⚠️ *{name}* صرف {qty} {unit} رہ گئے",
    },
    "low_stock_owner": {
        "en": "⚠️ {business}: low stock after {by}'s entry: {items}",
        "roman_ur": "⚠️ {business}: {by} ki entry ke baad stock kam: {items}",
        "ur": "⚠️ {business}: {by} کی انٹری کے بعد اسٹاک کم: {items}",
    },
    "no_items": {
        "en": "No items in stock yet. Add one like: \"socks add karo, 30 ki bechta hun, 100 pcs\"",
        "roman_ur": "Abhi stock mein koi item nahi. Aise add karein: \"socks add karo, 30 ki bechta hun, 100 pcs\"",
        "ur": "ابھی اسٹاک میں کوئی آئٹم نہیں۔ ایسے شامل کریں: \"جرابیں شامل کرو، 30 کی بیچتا ہوں، 100 عدد\"",
    },
    "no_low_stock": {
        "en": "No item is low 👍 (Set an alert like: \"socks ka alert 10 pe lagao\")",
        "roman_ur": "Koi item kam nahi 👍 (Alert aise lagayein: \"socks ka alert 10 pe lagao\")",
        "ur": "کوئی آئٹم کم نہیں 👍 (الرٹ ایسے لگائیں: \"جرابوں کا الرٹ 10 پر لگاؤ\")",
    },
    "stock_report_list": {"en": "📦 *Stock* ({n} items)", "roman_ur": "📦 *Stock* ({n} items)", "ur": "📦 *اسٹاک* ({n} آئٹم)"},
    "stock_report_rates": {"en": "🏷️ *Rate list*", "roman_ur": "🏷️ *Rate list*", "ur": "🏷️ *ریٹ لسٹ*"},
    "stock_report_low": {"en": "⚠️ *Low stock* ({n})", "roman_ur": "⚠️ *Kam stock* ({n})", "ur": "⚠️ *کم اسٹاک* ({n})"},
    "stock_report_value": {"en": "💰 *Stock value*", "roman_ur": "💰 *Stock ki value*", "ur": "💰 *اسٹاک کی مالیت*"},
    "rate_line": {
        "en": "{name} — sale {sale} · purchase {purchase}",
        "roman_ur": "{name} — sale {sale} · khareed {purchase}",
        "ur": "{name} — فروخت {sale} · خرید {purchase}",
    },
    "value_line_no_price": {
        "en": "{name} — {qty} (no purchase price)",
        "roman_ur": "{name} — {qty} (khareed qeemat nahi)",
        "ur": "{name} — {qty} (خرید قیمت نہیں)",
    },
    "low_line": {
        "en": "{name} — {qty} (alert at {level})",
        "roman_ur": "{name} — {qty} (alert {level} pe)",
        "ur": "{name} — {qty} (الرٹ {level} پر)",
    },
    "low_level_line": {
        "en": "⚠️ Alert at {level} {unit}",
        "roman_ur": "⚠️ Alert {level} {unit} pe",
        "ur": "⚠️ الرٹ {level} {unit} پر",
    },
    "stock_value_total": {"en": "💰 Value: {amount}", "roman_ur": "💰 Value: {amount}", "ur": "💰 مالیت: {amount}"},
    "report_more": {
        "en": "… and {n} more. Send \"stock PDF\" for the full list.",
        "roman_ur": "… aur {n} items. Poori list ke liye \"stock PDF bhejo\" likhein.",
        "ur": "… اور {n} آئٹم۔ پوری لسٹ کے لیے \"اسٹاک PDF بھیجو\" لکھیں۔",
    },
    "stock_in_report": {
        "en": "📥 *Stock in*{name} · {period}\n{n} entries · {amount}",
        "roman_ur": "📥 *Stock in*{name} · {period}\n{n} entries · {amount}",
        "ur": "📥 *اسٹاک اِن*{name} · {period}\n{n} انٹریاں · {amount}",
    },
    "stock_out_report": {
        "en": "📤 *Stock out*{name} · {period}\n{n} entries · {amount}",
        "roman_ur": "📤 *Stock out*{name} · {period}\n{n} entries · {amount}",
        "ur": "📤 *اسٹاک آؤٹ*{name} · {period}\n{n} انٹریاں · {amount}",
    },
    "report_total_qty": {"en": "Total: {qty} {unit}", "roman_ur": "Kul: {qty} {unit}", "ur": "کل: {qty} {unit}"},
    "no_stock_moves": {
        "en": "No stock entries for {period}.",
        "roman_ur": "{period} mein koi stock entry nahi.",
        "ur": "{period} میں کوئی اسٹاک انٹری نہیں۔",
    },
    "move_stock_opening": {"en": "Opening", "roman_ur": "Shuru ka stock", "ur": "ابتدائی اسٹاک"},
    "move_stock_in": {"en": "Stock in", "roman_ur": "Stock aaya", "ur": "اسٹاک آیا"},
    "move_purchase": {"en": "Bought", "roman_ur": "Khareeda", "ur": "خریدا"},
    "move_stock_out": {"en": "Stock out", "roman_ur": "Stock kam", "ur": "اسٹاک کم"},
    "move_sale": {"en": "Sold", "roman_ur": "Becha", "ur": "بیچا"},
    "entry_stock_opening": {"en": "Opening stock", "roman_ur": "Shuru ka stock", "ur": "ابتدائی اسٹاک"},
    "entry_stock_in": {"en": "Stock in", "roman_ur": "Stock in", "ur": "اسٹاک اِن"},
    "entry_stock_out": {"en": "Stock out", "roman_ur": "Stock out", "ur": "اسٹاک آؤٹ"},
    "entry_purchase": {"en": "Purchase", "roman_ur": "Khareed", "ur": "خرید"},
    "edit_item_nothing": {
        "en": "What should I change? e.g. \"socks ka rate 35 karo\"",
        "roman_ur": "Kya badalna hai? Jaise: \"socks ka rate 35 karo\"",
        "ur": "کیا بدلنا ہے؟ جیسے: \"جرابوں کا ریٹ 35 کرو\"",
    },
    "field_name": {"en": "Name", "roman_ur": "Naam", "ur": "نام"},
    "field_unit": {"en": "Unit", "roman_ur": "Unit", "ur": "اکائی"},
    "field_category": {"en": "Category", "roman_ur": "Category", "ur": "کیٹیگری"},
    "field_sale": {"en": "Sale price", "roman_ur": "Sale rate", "ur": "فروخت قیمت"},
    "field_purchase": {"en": "Purchase price", "roman_ur": "Khareed rate", "ur": "خرید قیمت"},
    "field_alert": {"en": "Low stock alert", "roman_ur": "Low stock alert", "ur": "کم اسٹاک الرٹ"},
    "confirm_edit_item": {
        "en": "Change *{name}*?\n{changes}\n(yes/no)",
        "roman_ur": "*{name}* mein yeh badlun?\n{changes}\n(haan/nahi)",
        "ur": "*{name}* میں یہ بدلوں؟\n{changes}\n(ہاں/نہیں)",
    },
    "item_updated": {"en": "✏️ *{name}* updated", "roman_ur": "✏️ *{name}* update ho gaya", "ur": "✏️ *{name}* اپڈیٹ ہو گیا"},
    "item_gone": {"en": "That item is no longer there.", "roman_ur": "Yeh item ab mojood nahi.", "ur": "یہ آئٹم اب موجود نہیں۔"},
    "confirm_delete_item": {
        "en": "Delete item *{name}* (stock {qty} {unit})? (yes/no)",
        "roman_ur": "Item *{name}* delete karun? (stock {qty} {unit}) (haan/nahi)",
        "ur": "آئٹم *{name}* ڈیلیٹ کروں؟ (اسٹاک {qty} {unit}) (ہاں/نہیں)",
    },
    "item_deleted": {"en": "🗑️ Item *{name}* deleted", "roman_ur": "🗑️ Item *{name}* delete ho gaya", "ur": "🗑️ آئٹم *{name}* ڈیلیٹ ہو گیا"},
    "no_item_photo": {
        "en": "*{name}* has no photo. Send a photo with the caption \"{name} ki photo\".",
        "roman_ur": "*{name}* ki koi photo nahi. Photo ke saath likhein: \"{name} ki photo\"",
        "ur": "*{name}* کی کوئی تصویر نہیں۔ تصویر کے ساتھ لکھیں: \"{name} کی تصویر\"",
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
    "thi", "thay", "kitni", "dikhao", "bhejo", "banao", "lagao", "hatao", "bech", "becha", "beche", "diye",
    "diya", "liye", "liya", "aae", "aaye", "gae", "gaye", "hui", "hua", "mila", "mile", "wale", "wali",
    "baqi", "kharab", "muft", "sab", "hisaab", "mahine", "wapas", "wapis", "karna", "ho",
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
