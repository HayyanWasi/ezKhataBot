"""Live Roman Urdu QA battery. Usage: python tests/qa_battery.py <group> [pause]
Groups run in separate synthetic shops (own phone each) so they can run in parallel."""

import sys

from qa_live import Session, save

GROUP = sys.argv[1]
PAUSE = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
R = []


def seed(s, text, tries=4):
    """Set-up helper (not scored): send a clear command and answer its questions."""
    r = s.say(text, quiet=True)
    for _ in range(tries):
        k = r["pend_after"]
        if not k:
            return r
        if k.startswith("confirm") or k == "choose_party":
            r = s.say("haan" if k.startswith("confirm") else "1", quiet=True)
        elif k == "opening_cash":
            r = s.say("0", quiet=True)
        elif k == "shop_details":
            r = s.say("skip", quiet=True)
        elif k == "choose_category":
            r = s.say("1", quiet=True)
        else:
            return r
    return r


def T(s, tid, feat, style, text, **exp):
    return s.say(text, tid, feat, style, exp)


def conf(s, tid, feat, style="Confirmation", text="haan", **exp):
    return s.say(text, tid, feat, style, exp)


SOCIAL_I = ["greeting", "help"]


def g_social():
    s = Session("999000000301", "QA Social Shop", R, PAUSE)
    F = "Conversation"
    for i, (st, tx) in enumerate([
        ("Normal", "kya kar rahe ho?"), ("Karachi casual", "kiya kar rha hai tou?"),
        ("Pronoun aap", "kya krrhe ho aap?"), ("Pronoun tum", "kya krrhe ho tum?"),
        ("Karachi casual", "mere bhai tum kiya karhe ho?"), ("Misspelled", "mere bhi tum kiya karrhe ho?"),
        ("Compressed", "kya kr rhy"), ("Compressed", "kia krra"), ("Compressed", "kya krha h"),
        ("Repeated letters", "kyaa kr rhe ho"), ("Compressed", "kya krre ho"), ("Rough", "abe tu kya kr raha h"),
        ("Rough", "oye tou kya karha hai"), ("Greeting", "assalam o alaikum bhai kese ho"), ("Slang", "bhai kia scene h"),
        ("Identity", "tm kon ho bhai"), ("Capability", "tu kia kia kr skta h"), ("Capability", "kya kya kar sakte ho aap"),
        ("Help", "madad chahiye bhai kese use karun is ko"), ("Short", "help"), ("Short", "hi"),
        ("Gratitude", "shukriya bhai"), ("Rude no abuse", "bekar bot hai tu kuch nahi aata"),
    ], 1):
        T(s, f"SOC-{i:02d}", F, st, tx, i=SOCIAL_I + ["unknown"], w="none", nx="samajh nahi aaya|didn't understand")
    for i, (st, tx) in enumerate([("Filler", "ok"), ("Filler", "hmm"), ("Emoji", "👍"), ("Gibberish", "asdfgh"),
                                  ("Punctuation", "???"), ("Wrong input", "kal"), ("Wrong input", "cash")], 1):
        T(s, f"WRG-{i:02d}", "Wrong/accidental input", st, tx, w="none")


def g_employee():
    s = Session("999000000302", "QA Employee Shop", R, PAUSE)
    F = "Employee"
    AE = ["add_employee"]

    def add(tid, style, text, num):
        r = T(s, tid, F, style, text, i=AE, p=True, w="none", rx=num[-7:])
        if r["pend_after"] and r["pend_after"].startswith("confirm"):
            conf(s, tid + "c", F, "Confirmation", "haan", w="some")
        else:
            s.settle()

    add("EMP-01", "Normal", "employee add karo Ali 03331000001", "03331000001")
    add("EMP-02", "English order", "add employee Asif 03331000002", "03331000002")
    add("EMP-03", "Name first", "Danish ko add kardo number 03331000004", "03331000004")
    add("EMP-04", "Pronoun ref", "Farhan add krdo iska number ye hai 03331000005", "03331000005")
    add("EMP-05", "Compressed", "kamran 03331000006 add", "03331000006")
    add("EMP-06", "Karachi casual", "bhai sajid ko employee mein daldo 03331000007", "03331000007")
    add("EMP-07", "Rough", "oye imran ko add kr iska number 03331000008", "03331000008")
    add("EMP-08", "Compressed", "employee tariq 03331000009", "03331000009")
    add("EMP-09", "Compressed", "zubair dal 03331000012", "03331000012")
    add("EMP-10", "Spaced phone", "Hamza ko staff add karo 0333 1000013", "1000013")
    add("EMP-11", "+92 format", "naveed ko employee rakh lo +92 333 1000014", "1000014")
    # missing number -> must ask, not save
    T(s, "EMP-12", F, "Missing detail", "usman ko staff me dal", i=AE, w="none", p=True)
    T(s, "EMP-13", F, "Follow-up bare number", "03331000015", i=AE, rx="Usman|usman", p=True)  # context kept?
    s.settle()
    T(s, "EMP-14", F, "Missing detail", "waqas staff add kr", i=AE, w="none", p=True)
    T(s, "EMP-15", F, "Follow-up name only", "employee add krdo", i=AE, w="none", p=True)
    T(s, "EMP-16", F, "Follow-up name", "Rizwan", w="none", rx="number|Number", nx="samajh nahi aaya|Write the employee")
    T(s, "EMP-17", F, "Follow-up phone", "03331000016", w="some", p=True)
    s.settle()
    # multi-action
    T(s, "EMP-18", F, "Multi-action", "Rizwan ko employee add karo 03331000017 aur uski salary 30000 rakhdo",
      i=AE + ["many_entries"], rx="30000|30,000|salary|tankhwah")
    s.settle()
    T(s, "EMP-19", F, "Multi-action update", "Ali ka number update karo aur uski salary bhi 35k kar do", w="none",
      rx="35|salary|number")
    s.settle()
    T(s, "EMP-20", F, "List formal", "employees dikhao", i=["list_employees"], w="none", rx="Ali")
    T(s, "EMP-21", F, "List compressed", "staff list bta", i=["list_employees"], w="none")
    T(s, "EMP-22", F, "List casual", "mere paas kitne banday kaam kr rhe hain", i=["list_employees"], w="none")
    T(s, "EMP-23", F, "List slang", "emp kon kon hain", i=["list_employees"], w="none")
    T(s, "EMP-24", F, "Duplicate", "employee add karo Ali 03331000001", w="none", nx="add ho gaya|add kar diya")
    s.settle()
    T(s, "EMP-25", F, "Remove casual", "asif ko hata do bhai", i=["remove_employee"], p=True, w="none")
    conf(s, "EMP-25b", F, "Cancel with nai", "nai", w="none")
    T(s, "EMP-26", F, "Remove ambiguous pronoun", "usko nikal do", w="none")
    s.settle()
    T(s, "EMP-27", F, "Remove unknown name", "farzana ko employee se hata do", w="none")
    s.settle()
    T(s, "EMP-28", F, "Add no name", "03331000020 add kr employee me", w="none", p=True)
    s.settle()
    T(s, "EMP-29", F, "Mixed English", "please add Sarmad as staff member his no is 03331000021", i=AE, p=True, w="none")
    conf(s, "EMP-29b", F, "Confirm ji", "ji", w="some")
    T(s, "EMP-30", F, "Confirm word w/o pending", "haan", w="none")


def g_party():
    s = Session("999000000303", "QA Party Shop", R, PAUSE)
    F = "Party khata"
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "Ahmed customer add karo")
    seed(s, "Bilal supplier add karo")
    s.settle()
    PE = ["party_entry"]
    # direction clear
    T(s, "PTY-01", F, "Normal", "Ali ko 500 udhaar diye", i=PE, w="some", rx="500")
    T(s, "PTY-02", F, "Compressed", "ali ne 300 diye", i=PE, w="some", rx="300")
    T(s, "PTY-03", F, "Compressed k", "2k udhr ahmed ko", i=PE + ["cash_entry"], rx="2,?000")
    s.settle()
    T(s, "PTY-04", F, "Word number dhai hazar", "Ahmed ko dhai hazar udhaar diye", i=PE, rx="2,?500")
    s.settle()
    T(s, "PTY-05", F, "Word number paanch sau", "Ali ko paanch sau diye", i=PE, rx="500")
    s.settle()
    T(s, "PTY-06", F, "Word number dedh hazar", "ali ko dedh hazar udhar de diye", i=PE, rx="1,?500")
    s.settle()
    T(s, "PTY-07", F, "Comma amount", "Ali ne 1,500 wapas kiye", i=PE, rx="1,?500")
    s.settle()
    T(s, "PTY-08", F, "Backdated", "kal Ali ko 700 diye the", i=PE, rx="700")
    s.settle()
    T(s, "PTY-09", F, "Supplier", "Bilal se 4000 ka maal liya udhaar", i=PE, rx="4,?000")
    s.settle()
    T(s, "PTY-10", F, "Payment to supplier", "Bilal ko 1000 payment ki cash", i=PE, rx="1,?000")
    s.settle()
    # balances / reports (read-only)
    T(s, "PTY-11", F, "Compressed", "ali ka khata", i=["party_balance"], w="none", rx="Ali")
    T(s, "PTY-12", F, "Casual", "ali wala hisab bata", i=["party_balance"], w="none")
    T(s, "PTY-13", F, "Casual", "ali ka kitna bnta hai", i=["party_balance"], w="none")
    T(s, "PTY-14", F, "Casual", "ali se kitne lene hain", i=["party_balance"], w="none")
    T(s, "PTY-15", F, "Casual all", "sab udhar dikhao", i=["list_parties"], w="none")
    T(s, "PTY-16", F, "Slang", "kis kis ne paise dene hain", i=["list_parties"], w="none")
    T(s, "PTY-17", F, "Mixed", "Ali ka total outstanding batao", i=["party_balance"], w="none")
    T(s, "PTY-18", F, "Question", "kya ali ne paise diye the?", i=["party_balance", "party_entry"], w="none")
    T(s, "PTY-19", F, "Compressed", "ali ka no 03339998887", i=["set_party_phone"], w="some")
    T(s, "PTY-20", F, "Multi", "Ali ko 100 diye aur Ahmed se 200 liye", i=["many_entries", "party_entry"], w="some", rx="100.*200|200.*100")
    s.settle()
    # unsafe/ambiguous
    T(s, "AMB-01", F, "Ambiguous", "ali ko 500 daldo", w="none", p=True)
    s.settle()
    T(s, "AMB-02", F, "Ambiguous", "ali 500", w="none", p=True)
    s.settle()
    T(s, "AMB-03", F, "Ambiguous no name", "5k add kr", w="none", p=True)
    s.settle()
    T(s, "AMB-04", F, "Pronoun no antecedent", "usko 500 de", w="none")
    s.settle()
    T(s, "AMB-05", F, "Pronoun no antecedent", "usko payment krdi", w="none")
    s.settle()
    T(s, "AMB-06", F, "Pronoun no antecedent", "2 hazar uske account me", w="none")
    s.settle()
    T(s, "AMB-07", F, "No amount", "customer ka balance update kr", w="none")
    s.settle()
    T(s, "AMB-08", F, "Bare amount", "5k aya", w="none", p=True)
    s.settle()
    T(s, "AMB-09", F, "Bare amount", "3k gya", w="none", p=True)
    s.settle()
    T(s, "AMB-10", F, "Unknown name", "Zeeshan ko 700 diye", w="none")
    s.settle()
    T(s, "AMB-11", F, "Duplicate name risk", "Ali ko 500", w="none", p=True)
    s.settle()
    T(s, "AMB-12", F, "Amount typo", "Ali ko 5oo diye", w="none")
    s.settle()
    T(s, "AMB-13", F, "Two amounts conflicting", "Ali ko 500 diye nahi 700 diye", w="none")
    s.settle()
    # corrections / undo
    T(s, "COR-01", F, "Entry", "Ali ko 800 diye", i=PE, w="some")
    T(s, "COR-02", F, "Correction no entry word", "nahi 900 the", i=["edit_entry"], w="none", p=True)  # must confirm
    conf(s, "COR-02b", F, "Confirm", "haan", w="some")
    T(s, "COR-03", F, "Undo vague", "woh entry delete kr", w="none")
    s.settle()
    T(s, "COR-04", F, "Undo vague", "purana wala hata do", w="none")
    s.settle()
    T(s, "COR-05", F, "Undo vague date", "kal wala change krdo", w="none")
    s.settle()
    T(s, "COR-06", F, "Undo last", "last entry undo kr do", i=["delete_entry"], w="none", p=True)
    conf(s, "COR-06b", F, "Cancel", "rehne do", w="none")
    T(s, "COR-07", F, "Casual memory", "mene ali ka kuch dala tha?", i=["party_balance", "recent_entries"], w="none")
    T(s, "COR-08", F, "Casual memory", "wo 500 wala entry dikha", i=["recent_entries", "party_balance"], w="none")
    T(s, "COR-09", F, "Casual memory", "kya record kiya tha", i=["recent_entries"], w="none")
    T(s, "COR-10", F, "Casual memory", "pichla record kholo", i=["recent_entries"], w="none")
    T(s, "COR-11", F, "Casual memory", "kal jo entry ki thi wo dikhao", i=["recent_entries"], w="none")
    # follow-up references after an entry
    T(s, "CTX-01", F, "Entry then pronoun", "Ahmed ko 250 diye", i=PE, w="some")
    T(s, "CTX-02", F, "Pronoun phone", "uska number 03337776665", i=["set_party_phone"], w="some", rx="Ahmed")
    T(s, "CTX-03", F, "Pronoun balance", "uska hisab bta", i=["party_balance"], w="none", rx="Ahmed")
    T(s, "CTX-04", F, "Again same", "same Ali ko bhi", w="none")
    s.settle()
    T(s, "CTX-05", F, "Also", "aur 300 bhi", w="none")
    s.settle()


def g_cash():
    s = Session("999000000304", "QA Cash Shop", R, PAUSE)
    F = "Cash book"
    seed(s, "3000 aaye")  # opening cash question gets 0
    s.settle()
    CE = ["cash_entry"]
    T(s, "CSH-01", F, "Bare word amount", "rickshaw 300", i=CE, w="some", rx="300")
    s.settle()
    T(s, "CSH-02", F, "Reversed", "300 chai", i=CE, w="some", rx="300")
    s.settle()
    T(s, "CSH-03", F, "Roman Urdu", "bijli ka bill 3500 bhara", i=CE, w="some", rx="3,?500")
    s.settle()
    T(s, "CSH-04", F, "Compressed", "kiraya 15k diya", i=CE, w="some", rx="15,?000")
    s.settle()
    T(s, "CSH-05", F, "Word amount", "ek hazar kharcha nashta ka", i=CE, w="some", rx="1,?000")
    s.settle()
    T(s, "CSH-06", F, "Shorthand", "500 out", i=CE, w="some", rx="500")
    s.settle()
    T(s, "CSH-07", F, "Sale", "aaj 2000 ki sale hui", i=CE, w="some", rx="2,?000")
    s.settle()
    T(s, "CSH-08", F, "Missing amount", "expense daldo", w="none", p=True)
    s.settle()
    T(s, "CSH-09", F, "Missing amount", "expense add kr", w="none", p=True)
    T(s, "CSH-09b", F, "Compressed follow-up", "500", w="none")
    s.settle()
    T(s, "CSH-10", F, "Missing detail", "kharcha kia", w="none")
    s.settle()
    T(s, "CSH-11", F, "Salary", "salary 20000 di", i=CE, w="some")
    s.settle()
    T(s, "CSH-12", F, "Multi-action", "5000 sale add karo aur 1000 expense bhi daldo", i=["many_entries", "cash_entry"],
      w="some", rx="5,?000.*1,?000|1,?000.*5,?000")
    s.settle()
    T(s, "CSH-13", F, "Multi ambiguous", "10k aya 3k supplier ko diya baki cash me rakhdo", i=["many_entries", "party_entry", "cash_entry"], rx="10,?000|3,?000")
    s.settle()
    # reports
    for i, (st, tx, it) in enumerate([
        ("Compressed", "aj ka hisab", ["money_report"]), ("Compressed", "cash kitna", ["money_report"]),
        ("Casual", "aj kya hua", ["recent_entries", "money_report"]), ("Casual", "aj ka scene bta", ["money_report", "recent_entries"]),
        ("Casual", "aj kitna bana", ["profit_report", "bill_report", "money_report"]), ("Casual", "aj kitna aya", ["money_report"]),
        ("Casual", "kitna gaya", ["money_report"]), ("Casual", "mera kya hisab hai", ["money_report", "list_parties"]),
        ("Ambiguous", "kal ka bata", ["money_report", "recent_entries", "bill_report"]),
        ("Casual", "pichle hafte ka scene", ["money_report", "recent_entries", "profit_report"]),
        ("Casual", "sale kitni hui", ["bill_report", "money_report"]), ("Casual", "kharcha kitna hua", ["money_report"]),
        ("Casual", "is month ka kya scene hai", ["money_report", "profit_report", "recent_entries"]),
        ("Compressed", "kl ki sale", ["bill_report", "money_report"]), ("Compressed", "aj report", ["money_report"]),
        ("Compressed", "kl wala dikha", ["recent_entries", "money_report"]),
    ], 1):
        T(s, f"RPT-{i:02d}", "Reports/memory", st, tx, i=it, w="none", nx="samajh nahi aaya")
    T(s, "RPT-17", "Reports", "Multi report", "kal ki sale dikhao aur aj ka expense bhi batao", w="none")
    T(s, "RPT-18", "Reports", "Mixed", "bro aaj ki sale kitni hui", i=["bill_report", "money_report"], w="none")
    T(s, "RPT-19", "Reports", "Mixed", "yaar cash in hand kitna h", i=["money_report"], w="none")
    T(s, "RPT-20", "Reports", "PDF", "cash book ki pdf bhejo", i=["money_report"], w="none")
    T(s, "RPT-21", "Reports", "Profit", "boss kal ka profit?", i=["profit_report"], w="none")
    T(s, "RPT-22", "Reports", "Profit casual", "aj kitna munafa hua", i=["profit_report"], w="none")
    # bank / transfer
    T(s, "BNK-01", "Bank", "Add bank", "JazzCash add kr", i=["add_bank"], w="some")
    s.settle()
    T(s, "BNK-02", "Bank", "Transfer", "bank mein 1000 jama karaye jazzcash", i=["transfer_money"], w="some")
    s.settle()
    T(s, "BNK-03", "Bank", "Wallet in", "5k jazzcash me aye", i=CE, w="some", rx="5,?000")
    s.settle()
    # correction on cash
    T(s, "COR-20", "Cash corr", "Edit", "chai wali 300 entry 350 thi", i=["edit_entry"], p=True)
    conf(s, "COR-20b", "Cash corr", "Confirm", "haan", w="some")
    T(s, "COR-21", "Cash corr", "Delete last", "pichli entry hata do", i=["delete_entry"], p=True, w="none")
    conf(s, "COR-21b", "Cash corr", "Cancel", "nai", w="none")
    T(s, "DUP-01", "Duplicate", "Send twice", "rickshaw 100", i=CE, w="some")
    s.settle()
    T(s, "DUP-02", "Duplicate", "Send twice", "rickshaw 100", i=CE)
    s.settle()


def g_stock():
    s = Session("999000000305", "QA Stock Shop", R, PAUSE)
    F = "Stock/bills"
    seed(s, "Bilal supplier add karo")
    seed(s, "socks item add karo 30 ki bechta hun 20 ki aati hai pieces 50 hain")
    seed(s, "charger item add karo sale 1500 khareed 1000 pieces 20")
    s.settle()
    T(s, "STK-01", F, "Casual qty", "socks kitne hain", i=["stock_report"], w="none", rx="50")
    T(s, "STK-02", F, "Compressed", "stock dikhao", i=["stock_report"], w="none")
    T(s, "STK-03", F, "Slang", "maal kam kon sa hai", i=["stock_report"], w="none")
    T(s, "STK-04", F, "Stock in", "30 socks aaye bilal se udhaar", i=["stock_in"], w="some")
    s.settle()
    T(s, "STK-05", F, "Stock out damage", "5 socks kharab ho gaye", i=["stock_out"], w="some")
    s.settle()
    T(s, "STK-06", F, "Rate edit", "socks ka rate 35 kr do", i=["edit_item"], w="some")
    s.settle()
    T(s, "STK-07", F, "Delete item", "charger delete kr do", i=["delete_item"], p=True, w="none")
    conf(s, "STK-07b", F, "Cancel", "nahi", w="none")
    T(s, "BIL-01", F, "Sale", "2 socks bech diye", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-02", F, "Counter", "counter sale 3 charger", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-03", F, "Multi sale+expense", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye",
      i=["create_bill"], rx="500")
    s.settle()
    T(s, "BIL-04", F, "Customer udhaar", "Ali ko 2 socks udhaar diye", i=["create_bill"])
    s.settle()
    T(s, "BIL-05", F, "Over stock", "1000 charger bech diye", w="none", nx="add ho gaya|bill ban gaya")
    s.settle()
    T(s, "BIL-06", F, "Unknown item", "5 laptop bech diye", w="none")
    s.settle()
    T(s, "BIL-07", F, "Cancel bill", "bill 1 cancel kr do", i=["cancel_bill"], p=True, w="none")
    conf(s, "BIL-07b", F, "Cancel", "chor do", w="none")
    T(s, "BIL-08", F, "Sales total", "aj ki sale", i=["bill_report", "money_report"], w="none")
    T(s, "BIL-09", F, "Profit", "munafa kitna hua aaj", i=["profit_report"], w="none")
    T(s, "BIL-10", F, "Stock in no supplier", "20 charger aye", i=["stock_in"])
    s.settle()
    T(s, "BIL-11", F, "Mixed", "sir 3 socks aur 1 charger ka bill bana do cash", i=["create_bill"])
    s.settle()


def g_misc():
    s = Session("999000000306", "QA Misc Shop", R, PAUSE)
    F = "Reminders/statement/memory"
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "Ali ko 500 udhaar diye")
    s.settle()
    T(s, "REM-01", F, "Reminder", "Ali se paise lene hain kal yaad dila dena", i=["set_reminder"], rx="Ali|kal")
    s.settle()
    T(s, "REM-02", F, "Reminder time", "kal 5 baje bijli ka bill yaad krwana", i=["set_reminder"])
    s.settle()
    T(s, "REM-03", F, "List", "reminders dikhao", i=["list_reminders"], w="none")
    T(s, "REM-04", F, "Cancel vague", "reminder hata do", i=["cancel_reminder"])
    s.settle()
    T(s, "STM-01", F, "Statement", "ali ka statement bhej", i=["statement"], w="none")
    T(s, "STM-02", F, "Compressed", "ali ka pdf", i=["statement"], w="none")
    T(s, "STM-03", F, "All", "sab ka hisab pdf me do", i=["statement"], w="none")
    T(s, "MEM-01", F, "Memory", "mera naam Hayyan hai yaad rakhna", i=["remember_user_fact"])
    T(s, "MEM-02", F, "Recall", "kya yaad hai tmhe", i=["list_memories"], w="none")
    T(s, "LNG-01", F, "Language", "ab se english me baat karo", i=["set_language"])
    T(s, "LNG-02", F, "Language back", "roman urdu me jawab do", i=["set_language"])
    T(s, "CAN-01", "Cancel", "Start entry", "customer add krna hai", p=True, w="none")
    T(s, "CAN-02", "Cancel", "Follow-up name", "Zubair", w="none", p=True)
    T(s, "CAN-03", "Cancel", "Follow-up phone", "0333 7654321", w="some")
    s.settle()
    T(s, "CAN-04", "Cancel", "Start", "Ali ko 100 diye", w="some")
    T(s, "CAN-05", "Cancel", "Cancel phrase", "rehne do", w="none")
    T(s, "CAN-06", "Cancel", "Change phrase", "change krdo", w="none")
    s.settle()
    T(s, "ENG-01", "Mixed English", "English", "show me ali's balance", i=["party_balance"], w="none")
    T(s, "ENG-02", "Mixed English", "Hinglish", "ali ko 500 pay kardo", w="none")
    s.settle()
    T(s, "ENG-03", "Mixed English", "Hinglish", "bhai last week ka total expenses send krdo", i=["money_report"], w="none")
    T(s, "ENG-04", "Mixed English", "Hinglish", "kal ke bills show kro", i=["bill_report"], w="none")


def opened(s):
    """Answer the one-time opening-cash question so later cash/sale steps are real tests."""
    seed(s, "1000 aaye")
    s.settle()


def g_ctx():
    s = Session("999000000307", "QA Context Shop", R, PAUSE)
    F = "Context"
    opened(s)
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "Bilal supplier add karo")
    s.settle()
    # 1. bot asks for amount; compressed answers
    T(s, "CTX-10", F, "Missing amount", "expense add kr", w="none", p=True)
    T(s, "CTX-11", F, "Bare number answer", "500", w="none", p=True)  # still needs what for
    T(s, "CTX-12", F, "Word answer", "chai", w="some")
    s.settle()
    T(s, "CTX-13", F, "Missing amount", "chai ka kharcha likh do", w="none", p=True)
    T(s, "CTX-14", F, "Hazar answer", "2 hazar", w="some", rx="2,?000")
    s.settle()
    # 2. direction question answers
    T(s, "CTX-15", F, "Direction q", "Ali 500", w="none", p=True)
    T(s, "CTX-16", F, "Answer 'pehla'", "pehla wala", w="some", rx="Ali.*500|500")
    s.settle()
    T(s, "CTX-17", F, "Direction q", "Ali 700", w="none", p=True)
    T(s, "CTX-18", F, "Answer word", "liye", w="some")
    s.settle()
    T(s, "CTX-19", F, "Direction q", "Ali 900", w="none", p=True)
    T(s, "CTX-20", F, "Answer ambiguous han", "han", w="none")
    s.settle()
    T(s, "CTX-21", F, "Direction q", "Ali 100", w="none", p=True)
    T(s, "CTX-22", F, "Answer cancel", "rehne do", w="none", p=False)
    s.settle()
    # 3. new party question
    T(s, "CTX-23", F, "New party", "Zeeshan ko 700 diye", w="none", p=True)
    T(s, "CTX-24", F, "Answer 'supplier hai'", "nahi supplier hai", w="some")
    s.settle()
    T(s, "CTX-25", F, "New party", "Waqar ko 300 udhaar diye", w="none", p=True)
    T(s, "CTX-26", F, "Answer nai", "nai", w="none")
    s.settle()
    # 4. stock pay question
    seed(s, "socks item add karo 30 ki bechta hun 20 ki aati hai pieces 10 hain")
    s.settle()
    T(s, "CTX-27", F, "Stock pay q", "50 socks aye bilal se", i=["stock_in"], w="none", p=True)
    T(s, "CTX-28", F, "Answer word", "udhar", w="some")
    s.settle()
    T(s, "CTX-29", F, "Stock pay q", "10 socks aye", i=["stock_in"], w="none", p=True)
    T(s, "CTX-30", F, "Answer cash word", "cash se", w="some")
    s.settle()
    # 5. interrupt a question with a new request
    T(s, "CTX-31", F, "Missing", "customer add krna hai", p=True, w="none")
    T(s, "CTX-32", F, "Interrupt", "ali ka khata dikha", i=["party_balance"], w="none", rx="Ali")
    T(s, "CTX-33", F, "Orphan answer", "Ahmed", w="none")
    s.settle()
    # 6. bare compressed tokens with no question pending
    for i, tx in enumerate(["ali", "500", "han", "nai", "woh wala", "cash", "03331234567", "2 hazar", "uska", "same", "rehne do",
                            "change krdo", "kal", "theek hai"], 34):
        T(s, f"CTX-{i}", "Orphan compressed", "Bare token no context", tx, w="none")
        s.settle()
    # 7. compressed accounting
    T(s, "CMP-01", "Compressed", "kr", "ali add kr", i=["add_party"], w="none", p=True)
    s.settle()
    T(s, "CMP-02", "Compressed", "dal", "ali ko dal", w="none")
    s.settle()
    T(s, "CMP-03", "Compressed", "udhr", "500 udhr", w="none")
    s.settle()
    T(s, "CMP-04", "Compressed", "2k name", "2k ali", w="none", p=True)
    s.settle()
    T(s, "CMP-05", "Compressed", "kitna bnta", "kitna bnta", w="none")
    s.settle()
    T(s, "CMP-06", "Compressed", "usko 500 de", "usko 500 de", w="none")
    s.settle()
    T(s, "CMP-07", "Compressed", "add kr phone name", "add kr 03331239999 hamid", i=["add_party", "add_employee"], w="none")
    s.settle()
    T(s, "CMP-08", "Compressed", "ali ko khata", "ali ko 3k udhr de dia", i=["party_entry"], w="some", rx="3,?000")
    s.settle()
    T(s, "CMP-09", "Compressed", "kl ki sale", "kl ki sale", i=["bill_report", "money_report"], w="none")
    T(s, "CMP-10", "Compressed", "cash kitna", "cash kitna", i=["money_report"], w="none", rx="Rs")
    T(s, "CMP-11", "Compressed", "5k aya", "5k aya", w="none", p=True)
    s.settle()
    T(s, "CMP-12", "Compressed", "3k gya", "3k gya", w="none", p=True)
    s.settle()
    # 8. duplicate on party entries
    T(s, "DUP-10", F, "Duplicate", "Ali ko 450 diye", i=["party_entry"], w="some")
    T(s, "DUP-11", F, "Duplicate repeat", "Ali ko 450 diye", i=["party_entry"])
    s.settle()
    T(s, "DUP-12", F, "Correction w/o entry word", "sorry 540 the", w="none")
    s.settle()
    T(s, "ACC-01", F, "Accident", "Ali ko 5000000 diye", w="none", p=True)  # implausibly large
    s.settle()
    T(s, "ACC-02", F, "Accident", "Ali ko 0 diye", w="none")
    s.settle()
    T(s, "ACC-03", F, "Negative", "Ali ko -500 diye", w="none")
    s.settle()
    T(s, "ACC-04", F, "Decimal", "Ali ko 500.50 diye", i=["party_entry"], rx="500\.5")
    s.settle()


def g_rerun():
    """The stock/bill/party steps that were blocked by the one-time opening-cash question in the first run."""
    s = Session("999000000308", "QA Rerun Shop", R, PAUSE)
    F = "Stock/bills"
    opened(s)
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "socks item add karo 30 ki bechta hun 20 ki aati hai pieces 50 hain")
    seed(s, "charger item add karo sale 1500 khareed 1000 pieces 20")
    s.settle()
    T(s, "BIL-01", F, "Sale", "2 socks bech diye", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-02", F, "Counter", "counter sale 3 charger", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-03", F, "Multi sale+expense", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye", i=["create_bill"], w="some", rx="500")
    s.settle()
    T(s, "BIL-04", F, "Customer udhaar", "Ali ko 2 socks udhaar diye", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-07", F, "Cancel bill", "bill 1 cancel kr do", i=["cancel_bill"], p=True, w="none")
    conf(s, "BIL-07b", F, "Cancel", "chor do", w="none")
    T(s, "BIL-08", F, "Sales total", "aj ki sale", i=["bill_report"], w="none", rx="Rs [1-9]")
    T(s, "BIL-09", F, "Profit", "munafa kitna hua aaj", i=["profit_report"], w="none")
    T(s, "BIL-11", F, "Mixed", "sir 3 socks aur 1 charger ka bill bana do cash", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-12", F, "Slang aj kitna bana", "aj kitna bana", w="none", nx="samajh nahi aaya")
    T(s, "BIL-13", F, "Compressed", "2 socks 60 me bech de", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-14", F, "Missing qty", "socks bech diye", w="none", p=True)
    s.settle()
    T(s, "ENG-02", "Mixed English", "Hinglish", "ali ko 500 pay kardo", w="none")
    s.settle()
    T(s, "CAN-04", "Cancel", "Start", "Ali ko 100 diye", w="some")
    T(s, "CAN-05", "Cancel", "Cancel phrase", "rehne do", w="none")
    T(s, "CAN-06", "Cancel", "Change phrase", "change krdo", w="none")


def g_cash2():
    """Cash steps that stopped at the one-time 'which category?' question in the first run."""
    s = Session("999000000309", "QA Cash2 Shop", R, PAUSE)
    F = "Cash book"
    opened(s)
    def asked(tid, style, text, amount_rx):
        r = T(s, tid, F, style, text, i=["cash_entry"], p=True, w="none")
        if r["pend_after"] == "choose_category":
            T(s, tid + "b", F, "Category answer", "1", w="some", rx=amount_rx)
        s.settle()
    asked("CSH-01", "Bare word amount", "rickshaw 300", "300")
    asked("CSH-02", "Reversed", "300 chai", "300")
    asked("CSH-03", "Roman Urdu", "bijli ka bill 3500 bhara", "3,?500")
    asked("CSH-04", "Compressed", "kiraya 15k diya", "15,?000")
    asked("CSH-05", "Word amount", "ek hazar nashta ka kharcha", "1,?000")
    asked("CSH-11", "Salary", "salary 20000 di", "20,?000")
    r = T(s, "COR-20", "Cash corr", "Edit no 'entry' dates", "chai wali 300 entry 350 thi", i=["edit_entry"], p=True, w="none")
    conf(s, "COR-20b", "Cash corr", "Confirm", "haan", w="some")
    T(s, "DUP-01", "Duplicate", "Repeat", "rickshaw 100", i=["cash_entry"], w="some")
    s.settle()
    T(s, "DUP-02", "Duplicate", "Repeat immediately", "rickshaw 100", i=["cash_entry"])
    s.settle()
    T(s, "RPT-17", "Reports", "Multi report", "kal ki sale dikhao aur aj ka expense bhi batao", w="none")
    T(s, "RPT-18", "Reports", "Mixed", "bro aaj ki sale kitni hui", i=["bill_report", "money_report"], w="none")
    T(s, "RPT-21", "Reports", "Profit kal", "boss kal ka profit?", i=["profit_report"], w="none", rx="4 Oct")
    T(s, "RPT-23", "Reports", "Kal expense", "kal kitna kharcha hua", i=["money_report"], w="none", rx="4 Oct")
    T(s, "RPT-24", "Reports", "Specific date", "15 sep ka hisab", i=["money_report"], w="none", rx="15 Sep")
    T(s, "RPT-25", "Reports", "Parso", "parso ki sale", w="none", rx="3 Oct")
    T(s, "RPT-26", "Reports", "Pichle hafte", "pichle hafte ka kharcha", i=["money_report"], w="none")
    T(s, "RPT-27", "Reports", "Month name", "september ke kharche", i=["money_report"], w="none", rx="Sep")


def g_bills2():
    s = Session("999000000310", "QA Bills2 Shop", R, PAUSE)
    F = "Stock/bills"
    opened(s)
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "socks item add karo 30 ki bechta hun 20 ki aati hai pieces 50 hain")
    seed(s, "charger item add karo sale 1500 khareed 1000 pieces 20")
    seed(s, "2 socks bech diye")   # one-time shop details question + bill #1
    s.settle()
    T(s, "BIL-01", F, "Sale", "3 socks bech diye", i=["create_bill"], w="some", rx="90")
    s.settle()
    T(s, "BIL-02", F, "Counter", "counter sale 1 charger", i=["create_bill"], w="some", rx="1,?500")
    s.settle()
    T(s, "BIL-03", F, "Multi sale+expense", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye", i=["create_bill"], w="some", rx="500")
    s.settle()
    T(s, "BIL-04", F, "Customer udhaar", "Ali ko 2 socks udhaar diye", i=["create_bill"], w="some", rx="Ali")
    s.settle()
    T(s, "BIL-07", F, "Cancel bill", "bill 1 cancel kr do", i=["cancel_bill"], p=True, w="none")
    conf(s, "BIL-07b", F, "Cancel", "chor do", w="none")
    T(s, "BIL-08", F, "Sales total", "aj ki sale", i=["bill_report"], w="none", rx="Rs [1-9]")
    T(s, "BIL-09", F, "Profit", "munafa kitna hua aaj", i=["profit_report"], w="none", rx="Rs")
    T(s, "BIL-10", F, "Profit kal slang", "aj kitna bana", w="none", rx="Rs [1-9]")
    T(s, "BIL-11", F, "Mixed", "sir 3 socks aur 1 charger ka bill bana do cash", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-13", F, "Compressed price", "2 socks 60 me bech de", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-15", F, "Discount", "10 charger ka bill 10% discount ke sath", i=["create_bill"])
    s.settle()
    T(s, "BIL-16", F, "Casual cust", "ali ko 5 socks de diye 150 ke", i=["create_bill"])
    s.settle()
    T(s, "BIL-17", F, "Bill show", "bill 2 dikhao", i=["bill_report"], w="none")
    T(s, "BIL-18", F, "Bill list compressed", "aaj ke bills", i=["bill_report"], w="none")
    T(s, "BIL-19", F, "Stock after", "socks kitne bache", i=["stock_report"], w="none")


def g_bills3():
    s = Session("999000000311", "QA Bills3 Shop", R, PAUSE)
    F = "Stock/bills"
    opened(s)
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "socks item add karo 30 ki bechta hun 20 ki aati hai pieces 50 hain")
    seed(s, "charger item add karo sale 1500 khareed 1000 pieces 20")
    r = s.say("2 socks bech diye", quiet=True)          # triggers the one-time question
    r = s.say("Shop 5 Gulshan Karachi 03211234567", "BIL-00", F, "Shop details answer", dict(w="some"))
    s.settle()
    T(s, "BIL-01", F, "Sale", "3 socks bech diye", i=["create_bill"], w="some", rx="90")
    s.settle()
    T(s, "BIL-02", F, "Counter", "counter sale 1 charger", i=["create_bill"], w="some", rx="1,?500")
    s.settle()
    T(s, "BIL-03", F, "Multi sale+expense", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye", i=["create_bill"], w="some", rx="500")
    s.settle()
    T(s, "BIL-04", F, "Customer udhaar", "Ali ko 2 socks udhaar diye", i=["create_bill"], w="some", rx="Ali")
    s.settle()
    T(s, "BIL-11", F, "Mixed", "sir 3 socks aur 1 charger ka bill bana do cash", i=["create_bill"], w="some")
    s.settle()
    T(s, "BIL-13", F, "Compressed price", "2 socks 60 me bech de", i=["create_bill"], w="some", rx="60")
    s.settle()
    T(s, "BIL-15", F, "Discount", "10 charger ka bill 10% discount ke sath", i=["create_bill"])
    s.settle()
    T(s, "BIL-16", F, "Casual cust", "ali ko 5 socks de diye 150 ke", i=["create_bill"])
    conf(s, "BIL-16b", F, "Pay answer", "udhaar", w="some")
    s.settle()
    T(s, "BIL-17", F, "Bill show", "bill 2 dikhao", i=["bill_report"], w="none", rx="Bill|bill")
    T(s, "BIL-20", F, "Cancel then confirm", "bill 2 cancel kr do", i=["cancel_bill"], p=True, w="none")
    conf(s, "BIL-20b", F, "Confirm", "ji haan", w="some")
    T(s, "BIL-21", F, "Sale multi-item words", "teen socks aur do charger bech diye", i=["create_bill"], rx="3|2")
    s.settle()


def g_extra():
    s = Session("999000000312", "QA Extra Shop", R, PAUSE)
    F = "Party/cash variants"
    opened(s)
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "Ahmed customer add karo")
    seed(s, "Ali ko 1000 udhaar diye")
    s.settle()
    def one(tid, style, text, **e):
        r = T(s, tid, F, style, text, **e)
        s.settle()
        return r
    one("VAR-01", "No amount", "ali ne paise de diye", w="none", p=True)
    one("VAR-02", "Clear got", "Ali se 500 mile", i=["party_entry"], w="some", rx="500")
    one("VAR-03", "Wallet", "ali ne 500 bheje jazzcash pe", i=["party_entry"], w="none")
    one("VAR-04", "Baqi", "Ali ka 500 baqi hai", w="none")
    one("VAR-05", "Likh lo", "Ali k 500 likh lo", w="none", p=True)
    one("VAR-06", "Spelling sey/lenay", "ali sey 500 lenay hain", i=["party_entry"], rx="500")
    one("VAR-07", "Spelling nay/dey", "ali nay 500 rupay dey diye", i=["party_entry"], rx="500")
    one("VAR-08", "Compressed rs", "500rs ali ko", w="none", p=True)
    one("VAR-09", "Statement not txn", "ali ne kaha kal dega", w="none", nx="✅")
    one("VAR-10", "Question", "ali kitne ka hai", i=["party_balance"], w="none")
    one("VAR-11", "Settle full", "ali ka hisab saaf kr do", w="none")
    one("VAR-12", "Full payment no amount", "ali se sare paise le liye", w="none", p=True)
    one("VAR-13", "Bill arrived not paid", "bijli ka bill aya hai 4000 ka", w="none")
    one("VAR-14", "Backdated sale", "kal 3000 ki sale hui thi", i=["cash_entry"], w="some", rx="3,?000")
    one("VAR-15", "Chai wale", "chai wale ko 200 de diye", w="none")
    one("VAR-16", "Drawings", "paise nikaale 1000 ghar ke liye", i=["cash_entry"], w="none")
    one("VAR-17", "Two parties", "ali ko 500 aur ahmed ko 300 de diye", w="none", rx="500.*300|300.*500")
    one("VAR-18", "Delete vague sale", "kal wali sale delete kr do", w="none")
    one("VAR-19", "Dangerous delete all", "sab kuch delete kr do", w="none", nx="delete ho gaya|hata di|mita di")
    one("VAR-20", "Dangerous wipe", "mera sara record mita do", w="none", nx="delete ho gaya|hata di|mita di")
    one("VAR-21", "Delete party", "ali ko hata do", w="none")
    one("VAR-22", "Close account", "ali ka account band kr do", w="none")
    one("VAR-23", "Reverse payment", "500 ali ko diye the wapas kr do", w="none")
    one("VAR-24", "Misspelled name aly", "aly ko 500 diye", w="none", p=True)
    one("VAR-25", "Misspelled name alii", "alii ko 500 dye", w="none", p=True)
    one("VAR-26", "CAPS", "ALI KO 200 UDHAAR DIYE", i=["party_entry"], w="some", rx="200")
    one("VAR-27", "Name contains ko", "Kokab ko 300 diye", w="none", p=True)
    one("VAR-28", "Phone dashed", "ali ka number 0333-1234567", i=["set_party_phone"])
    one("VAR-29", "Phone short", "ali ka number 0333123", i=["set_party_phone"], w="none", nx="save ho gaya")
    one("VAR-30", "Phone +92", "ahmed ka nbr +923331234567", i=["set_party_phone"], rx="Ahmed")
    one("VAR-31", "Phone 10 digit", "ahmed ka num 3331234568", i=["set_party_phone"])
    one("VAR-32", "Emp invalid phone", "employee add karo Zain 12345", i=["add_employee"], w="none", nx="add karun|haan/nahi")
    one("VAR-33", "Number words", "Ali ko teen hazar diye", i=["party_entry"], rx="3,?000")
    one("VAR-34", "Number words sau", "Ali ko do sau diye", i=["party_entry"], rx="200")
    one("VAR-35", "k suffix", "ali ko 1.5k udhaar de diye", i=["party_entry"], rx="1,?500")
    one("VAR-36", "lakh", "ali ko 1 lakh diye", i=["party_entry"], rx="100,?000")
    one("VAR-37", "Urdu digits words mix", "Ali ko 5 hazar rupay diye", i=["party_entry"], rx="5,?000")
    one("VAR-38", "Date parso", "parso Ali ko 400 diye the", i=["party_entry"], rx="3 Oct|400")
    one("VAR-39", "Date weekday", "pichle mangal ko Ali ne 300 diye", i=["party_entry"], rx="300")
    one("VAR-40", "Slang", "bhai ali ka kaam tamam 200 aaye hain", w="none")


def g_multi():
    """Multi-action messages followed all the way through: was every part done, in order, nothing dropped?"""
    s = Session("999000000313", "QA Multi Shop", R, PAUSE)
    F = "Multi-action"
    opened(s)
    seed(s, "Ali customer add karo 03331234567")
    seed(s, "socks item add karo 30 ki bechta hun 20 ki aati hai pieces 50 hain")
    seed(s, "charger item add karo sale 1500 khareed 1000 pieces 20")
    seed(s, "chai 10")
    seed(s, "2 socks bech diye")
    s.settle()

    def chase(tid, style, text, answers, **exp):
        r = T(s, tid, F, style, text, **exp)
        log = [f"{text!r} -> {r['reply']}"]
        for a in answers:
            if not s.pending_kind():
                break
            q = s.say(a, quiet=True)
            log.append(f"{a!r} -> {q['reply']}")
        s.settle()
        r["chain"] = log
        return r

    def report(tid, text, rx, **exp):
        T(s, tid, F, "Check state", text, rx=rx, **exp)

    chase("MUL-01", "Sale + expense", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye", ["cash", "1", "haan", "1", "haan"])
    report("MUL-01v", "aaj kya kya hua", "500|[Dd]elivery", w="none")
    chase("MUL-02", "Party + udhaar", "Ahmed ko customer add karo aur uske account mein 2500 udhar likhdo", ["haan", "1", "udhaar", "diye"])
    report("MUL-02v", "ahmed ka khata", "2,?500", w="none")
    chase("MUL-03", "Sale + expense", "5000 sale add karo aur 1000 expense bhi daldo", ["haan", "1"])
    report("MUL-03v", "aj ka hisab", "6,?000|5,?000", w="none")
    chase("MUL-04", "Two parties", "Ali ko 100 diye aur Ahmed se 200 liye", ["haan"])
    report("MUL-04v", "sab udhar dikhao", "Ali", w="none")
    chase("MUL-05", "Three lines", "chai 50 aur rickshaw 100 aur nashta 150", ["1", "1", "1", "haan"])
    report("MUL-05v", "aj kya kya hua", "50.*100|150", w="none")
    chase("MUL-06", "Party + phone", "Ali ko 500 diye aur uska number 03331239876 save kr lo", ["haan", "1"])
    report("MUL-06v", "ali ka khata", "9876|500", w="none")
    chase("MUL-07", "Stock + damage", "50 socks aye bilal se cash aur 5 kharab nikle", ["cash", "1", "haan"])
    report("MUL-07v", "socks kitne hain", "[0-9]", w="none")
    chase("MUL-08", "Two reports", "ali ka khata dikhao aur ahmed ka bhi", [])
    chase("MUL-09", "Edit + phone", "Ali ka number update karo aur uski salary bhi 35k kar do", [])
    chase("MUL-10", "Supplier split", "10k aya 3k supplier ko diya baki cash me rakhdo", ["haan", "1", "supplier", "1", "bilal"])
    report("MUL-10v", "aj kya kya hua", "10,?000|3,?000", w="none")
    chase("MUL-11", "Add item + stock", "socks ka rate 35 kar do aur charger ka 1600", ["haan", "haan"])
    report("MUL-11v", "rate list dikhao", "35.*1,?600|1,?600", w="none")
    chase("MUL-12", "Reminder + entry", "Ali ko 300 diye aur kal yaad dila dena paise lene hain", ["haan", "1"])
    report("MUL-12v", "reminders dikhao", "Ali|paise", w="none")


GROUPS = {"social": g_social, "employee": g_employee, "party": g_party, "cash": g_cash, "stock": g_stock, "misc": g_misc, "ctx": g_ctx, "rerun": g_rerun, "cash2": g_cash2, "bills2": g_bills2, "bills3": g_bills3, "extra": g_extra, "multi": g_multi}
if __name__ == "__main__":
    out = f"results_{GROUP}.json"
    try:
        GROUPS[GROUP]()
    finally:
        save(R, __file__.replace("qa_battery.py", out))
