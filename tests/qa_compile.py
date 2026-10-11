"""Merge all live QA result files, apply the reviewer's strict manual grading, print stats and write qa_final.json."""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

D = Path(__file__).parent
ORDER = ["social", "employee", "party", "cash", "stock", "misc", "ctx", "rerun", "cash2", "bills2", "bills3", "extra", "multi"]

# (id, text-or-None) -> (status, failure type, severity, explanation)
# types: NLU | Entity | Context | Logic | Safety | Setup-UX | Backend
O = {}


def o(i, status, ftype="", sev="None", note="", text=None):
    O[(i, text)] = (status, ftype, sev, note)


INC = "INCONCLUSIVE"
# ---- conversation
o("SOC-05", "FAIL", "NLU", "Medium", "Exact casual question from the brief ('mere bhai tum kiya karhe ho?') -> 'samajh nahi aaya'; sibling spellings pass.")
o("SOC-16", "FAIL", "NLU", "Low", "'tm kon ho bhai' (who are you) not understood.")
o("SOC-22", "FAIL", "NLU", "Low", "'shukriya bhai' (thanks) gets 'samajh nahi aaya'.")
o("SOC-23", "FAIL", "NLU", "Low", "Rough-but-not-abusive complaint answered with 'samajh nahi aaya' instead of a calm help reply.")
# ---- employees
o("EMP-12", "FAIL", "Context", "High", "Name 'usman' was given but ignored: bot sent a generic how-to and stored NOTHING (no pending state).")
o("EMP-13", "FAIL", "Context", "High", "Follow-up phone number after the bot asked for it -> 'samajh nahi aaya' (context lost).")
o("EMP-14", "FAIL", "Context", "High", "Same as EMP-12: name 'waqas' ignored, nothing remembered.")
o("EMP-15", "PARTIAL", "Context", "Medium", "Gives an example sentence instead of asking 'Naam kya hai?'; no pending question is stored.")
o("EMP-16", "FAIL", "Context", "High", "'Rizwan' as the answer to the employee question -> not understood, and reply switched to ENGLISH.")
o("EMP-17", "FAIL", "Context", "High", "Bare phone number after the question -> not understood.")
o("EMP-18", "FAIL", "Logic", "High", "Multi-action: employee confirm card shows no salary; the 'salary 30000' half was silently ignored.")
o("EMP-19", "FAIL", "NLU", "Medium", "'Ali ka number update karo aur uski salary bhi 35k kar do' -> unknown; no explanation that salary is unsupported.")
o("EMP-28", "FAIL", "Entity", "Medium", "Phone number given first, name missing: bot discards the number and gives a generic how-to; nothing remembered.")
# ---- party
for i in ("PTY-02", "PTY-07", "PTY-08", "PTY-10", "COR-01", "COR-02", "COR-02b", "AMB-08", "AMB-09", "CTX-28"):
    o(i, INC, "", "None", "Blocked by a one-time setup question (opening cash) or consumed by an earlier pending question; not a valid language test.")
o("PTY-04", "FAIL", "Entity", "High", "'dhai hazar' (2,500) not understood: bot asks 'kitne paise?'. Number words are not parsed (amounts.py is digits-only).")
o("PTY-05", "FAIL", "Entity", "High", "'paanch sau' (500) not understood -> 'kitne paise?'.")
o("PTY-06", "FAIL", "Entity", "High", "'dedh hazar' (1,500) not understood -> 'kitne paise?'.")
o("AMB-01", "FAIL", "Safety", "Critical", "'ali ko 500 daldo' saved immediately as 'Ali ko 500 diye'. Direction was guessed, no clarification, no confirmation.")
o("AMB-07", "PARTIAL", "NLU", "Low", "'customer ka balance update kr' -> 'samajh nahi aaya'; safe but should ask which customer/what balance.")
o("AMB-11", "FAIL", "Safety", "Medium", "'Ali ko 500' saved as 'gave' without asking direction (defensible from 'ko', but the same message with a different spelling asks).")
o("COR-03", "PARTIAL", "Logic", "Low", "'woh entry delete kr': guessed the last entry and asked yes/no instead of asking WHICH entry. Confirmation gate prevented harm.")
o("COR-04", "PARTIAL", "Logic", "Low", "'purana wala hata do' (the OLD one): proposed deleting the LATEST entry (opposite of 'purana'). Confirmation gate prevented harm.")
o("COR-05", "PARTIAL", "Logic", "Medium", "'kal wala change krdo': guessed an entry (the opening-balance row) and a new date; only the yes/no gate protects the user.")
o("COR-06", "PARTIAL", "Logic", "Low", "'last entry undo' proposed deleting the automatic opening-balance entry.")
o("COR-08", "FAIL", "NLU", "Medium", "'wo 500 wala entry dikha' -> party list instead of finding the Rs 500 entry.")
# ---- cash
o("CSH-13", "PARTIAL", "Logic", "Medium", "'10k aya 3k supplier ko diya baki cash me rakhdo': generic word 'supplier' treated as a party NAME; first half saved before the second was clear.")
o("RPT-05", "PARTIAL", "NLU", "Low", "'aj kitna bana' gave the cash report in one run and profit in another (inconsistent).")
o("RPT-17", "FAIL", "Logic", "High", "Multi-action report: 'kal ki sale dikhao aur aj ka expense bhi batao' answers only the first part (failed in both runs); the second is silently dropped.")
o("RPT-18", "PARTIAL", "NLU", "Medium", "'bro aaj ki sale kitni hui' -> profit report in run 1, bills report in run 2 (inconsistent between runs).")
o("RPT-21", "PARTIAL", "Entity", "High", "'boss kal ka profit?' returned TODAY's (5 Oct) profit in run 1 and yesterday in run 2: wrong date in one run.")
o("RPT-25", "FAIL", "Entity", "High", "'parso ki sale' (day before yesterday): date ignored, answered for today with a PROFIT report.")
o("CSH-05", "FAIL", "Entity", "High", "'ek hazar nashta ka kharcha' -> 'Kitne paise?' (number word 1000 not parsed).")
o("DUP-02", "PARTIAL", "Safety", "Medium", "Identical 'rickshaw 100' sent twice within seconds is saved twice with no duplicate warning.")
o("DUP-11", "PARTIAL", "Safety", "Medium", "Identical 'Ali ko 450 diye' repeated is saved twice with no duplicate warning.")
# ---- ctx
o("CTX-12", "FAIL", "Context", "Medium", "After '500' (amount) and the direction question, 'chai' made the bot forget the 500 and ask 'Kitne paise?' again.")
o("CTX-20", "FAIL", "Context", "Medium", "'han' to a 1/2 question -> 'samajh nahi aaya' AND the pending question was silently dropped instead of re-asked.")
o("CTX-22", "PARTIAL", "Context", "Low", "'rehne do' cancels (nothing saved) but replies 'samajh nahi aaya' instead of 'theek hai, cancel'.")
o("CTX-27", "FAIL", "Safety", "High", "'50 socks aye bilal se' saved as UDHAAR (Bilal ko dene hain Rs 1,000) though payment method was never said. A different message ('20 charger aye') asks.")
o("CMP-01", "FAIL", "Logic", "Medium", "'ali add kr' when Ali already exists says 'Ali naya hai' and offers to create another Ali.")
o("CMP-02", "FAIL", "Logic", "Medium", "'ali ko dal' same: existing customer treated as new.")
o("CMP-09", "PARTIAL", "NLU", "Low", "'kl ki sale' answered with a profit report instead of the sale total.")
o("CMP-11", "FAIL", "Safety", "Medium", "'5k aya' saved as cash-in Rs 5,000 with no question about from whom / cash vs bank.")
o("CMP-12", "FAIL", "Safety", "Medium", "'3k gya' saved as cash-out Rs 3,000 with no question about to whom / why.")
o("ACC-01", "FAIL", "Safety", "High", "'Ali ko 5000000 diye' saved instantly (Rs 5,000,000 > 5 million) with no sanity/confirmation check; cash went to -Rs 4,998,350.")
# ---- stock/bills
for k in ("2 socks bech diye", "counter sale 3 charger", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye", "Ali ko 2 socks udhaar diye",
          "sir 3 socks aur 1 charger ka bill bana do cash", "2 socks 60 me bech de", "3 socks bech diye", "counter sale 1 charger"):
    pass
o("BIL-03", "FAIL", "Entity", "Critical", "Sale + 'delivery 500' message: runs gave (a) bill + delivery expense saved as Rs 1, (b) qty dropped, rate=3000 and the 500 turned into 'paid_amount', (c) asked for a customer name. The Rs 500 expense is never reliably recorded.", text="2 charger 3000 ke sell kiye aur 500 delivery wale ko diye")
o("BIL-21", "FAIL", "Entity", "High", "'teen socks aur do charger bech diye' -> 'Socks kitne pcs?' (number words 3 and 2 not parsed).")
o("BIL-15", "PASS", "", "None", "Discount 10% applied correctly (Rs 15,000 -> 13,500).")
# ---- misc
o("REM-02", "PARTIAL", "Entity", "Medium", "'kal 5 baje' scheduled at 05:00 AM; a shopkeeper almost certainly means 5 PM. AM/PM guessed, not asked.")
o("CAN-05", "FAIL", "NLU", "Medium", "'rehne do' with nothing pending is read as a DELETE request for the last entry (yes/no card). A cancel phrase must never lead to delete.")
o("ENG-02", "PARTIAL", "Safety", "Medium", "'ali ko 500 pay kardo' (imperative) is saved immediately as a completed payment of Rs 500 (khata + cash).")
# ---- extra
o("VAR-08", "FAIL", "Safety", "Medium", "'500rs ali ko' saved as 'gave' without asking direction.")
o("VAR-09", "FAIL", "Safety", "Medium", "'ali ne kaha kal dega' (a remark) silently created a reminder 'Ali payment dega' nobody asked for.")
o("VAR-13", "PARTIAL", "Logic", "Medium", "'bijli ka bill aya hai 4000 ka' (bill ARRIVED, not paid) proceeds as a paid expense (asks category only).")
o("VAR-15", "PASS", "", "None", "Treated as an expense to 'chai wale' - reasonable.")
o("VAR-16", "PASS", "", "None", "Cash-out saved with 'ghar ke liye' as category - acceptable.")
o("VAR-21", "PARTIAL", "NLU", "Medium", "'ali ko hata do' (remove Ali) understood as delete Ali's last entry (yes/no card).")
o("VAR-23", "PARTIAL", "NLU", "Low", "'500 ... wapas kr do' (reverse/return) proposed deleting an entry; ambiguous request resolved by guessing.")
o("VAR-33", "FAIL", "Entity", "High", "'teen hazar' (3,000) not understood -> 'kitne paise?'.")
o("VAR-34", "FAIL", "Entity", "High", "'do sau' (200) not understood -> 'kitne paise?'.")
o("VAR-40", "PARTIAL", "Safety", "Medium", "'bhai ali ka kaam tamam 200 aaye hain' saved as 'Ali se 200 liye' - slang guess, no confirmation.")
# ---- multi
o("MUL-01", "FAIL", "Entity", "Critical", "Bill saved but the 'delivery 500' expense was saved as Rs 1 (the answer to a hidden amount question) - wrong financial record.")
o("MUL-01v", "VERIFY")
o("MUL-03", "PASS", "", "None", "Both entries detected, confirm card, both saved (expense after a category question).")
o("MUL-05", "PASS", "", "None", "3 entries detected and confirmed; new expense words each need a category question.")
o("MUL-06", "PARTIAL", "Logic", "Low", "Both done (entry + phone), but the reply never mentions the phone save.")
o("MUL-07", "PARTIAL", "Logic", "Low", "Both stock-in and stock-out done, but the reply reports only the stock-in.")
o("MUL-08", "FAIL", "Logic", "Medium", "'ali ka khata dikhao aur ahmed ka bhi' shows only Ali; Ahmed silently dropped.")
o("MUL-09", "FAIL", "NLU", "Medium", "Number update + salary -> unknown; neither half handled nor explained.")
o("MUL-10", "PARTIAL", "Logic", "Medium", "Both entries confirmed, but generic noun 'supplier' became a party name (a party literally called 'supplier' was created).")
o("MUL-11", "FAIL", "Logic", "High", "'socks ka rate 35 kar do aur charger ka 1600': only socks changed; charger rate silently ignored.")
o("MUL-12", "FAIL", "Logic", "Critical", "'Ali ko 300 diye aur kal yaad dila dena...': only the reminder was created; the Rs 300 khata entry was silently dropped.")
for v in ("MUL-02v", "MUL-03v", "MUL-04v", "MUL-05v", "MUL-06v", "MUL-07v", "MUL-10v", "MUL-11v", "MUL-12v"):
    o(v, "VERIFY")
# first-run entries whose result was blocked by one-time setup questions
for t in ("2 socks bech diye", "counter sale 3 charger", "Ali ko 2 socks udhaar diye", "sir 3 socks aur 1 charger ka bill bana do cash",
          "2 socks 60 me bech de"):
    for i in ("BIL-01", "BIL-02", "BIL-03", "BIL-04", "BIL-11", "BIL-13"):
        pass


for i in ("PTY-19", "PTY-20", "CTX-02", "CSH-09b", "CSH-12", "COR-20b", "STK-06", "CAN-02", "CAN-03", "CTX-14", "BIL-20b"):
    o(i, "PASS", "", "None", "Machine check was too narrow; manual review: correct behaviour.")
O[("BIL-03", "2 charger 3000 ke sell kiye aur 500 delivery wale ko diye")] = ("FAIL", "Entity", "High",
    "Sale + delivery 500: this run asked for a customer for 'udhaar' (never said); other runs: expense saved as Rs 1, or qty dropped and 500 taken as 'paid_amount'. See MUL-01.")


def style_group(style, feature):
    s = style.lower()
    if "compress" in s or "short" in s or s in {"kr", "dal", "udhr", "2k name", "bare token no context", "add kr phone name", "ali ko khata", "kl ki sale", "cash kitna"} or s.startswith("bare"):
        return "Compressed / very short"
    if "word number" in s or "number words" in s:
        return "Roman Urdu number words"
    if any(x in s for x in ("misspell", "spelling", "caps", "repeated", "typo")):
        return "Misspelled / spelling variants"
    if "multi" in s or "two parties" in s or "three lines" in s or "supplier split" in s or "party + " in s or "stock + " in s or "sale + " in s or "edit + " in s or "reminder + " in s:
        return "Multi-action"
    if any(x in s for x in ("follow-up", "answer", "confirm", "cancel", "orphan", "interrupt", "missing", "pronoun", "again", "also", "correction", "undo", "entry then")):
        return "Follow-up / context / missing detail"
    if any(x in s for x in ("casual", "slang", "rough", "karachi", "fan", "memory")):
        return "Casual / Karachi / slang"
    if any(x in s for x in ("english", "mixed", "hinglish")):
        return "Mixed Urdu-English"
    if "ambig" in s or "no amount" in s or "bare amount" in s or "dangerous" in s or "accident" in s or "negative" in s:
        return "Ambiguous / safety"
    return "Normal / clean"


def main():
    merged = {}
    for g in ORDER:
        p = D / f"results_{g}.json"
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            r["group"] = g
            merged[(r["id"], r["text"])] = r
    rows, unreviewed = [], []
    for (i, text), r in merged.items():
        ov = O.get((i, text)) or O.get((i, None))
        auto = r["verdict"]
        if ov:
            status, ftype, sev, note = ov
        elif auto == "PASS":
            status, ftype, sev, note = "PASS", "", "None", ""
        else:
            status, ftype, sev, note = "UNREVIEWED", "", "", r["why"]
            unreviewed.append((i, text, auto, r["why"]))
        if status == "UNREVIEWED" or (auto != "PASS" and r["pend_after"] in ("shop_details", "opening_cash") and r["id"].startswith(("BIL", "CAN", "ENG"))):
            if r["pend_after"] in ("shop_details", "opening_cash") and status != "PASS" and (i, text) not in O:
                status, ftype, sev, note = INC, "", "None", "Blocked by a one-time setup question; re-tested in a later group."
                if unreviewed and unreviewed[-1][0] == i:
                    unreviewed.pop()
        r.update(final=status, ftype=ftype, severity=sev, note=note, sgroup=style_group(r["style"], r["feature"]))
        rows.append(r)
    (D / "qa_final.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows, unreviewed


if __name__ == "__main__":
    rows, unreviewed = main()
    print("rows", len(rows))
    print("UNREVIEWED:")
    for u in unreviewed:
        print("  ", u)
