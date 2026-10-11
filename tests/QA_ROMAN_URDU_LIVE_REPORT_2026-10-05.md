# EzKhata – Live Roman Urdu QA Report (strict grading)

**Date:** 5 Oct 2026 · **Build tested:** `main` as of commit `dd1ede6` (employees merged) · **Method:** the real production pipeline (rules → LLM classifier → handlers → Supabase), driven message-by-message from a script, with the LLM key rotation exactly as deployed (Groq + OpenRouter + Gemini). No WhatsApp message was sent: all traffic used synthetic phones `99900000030x–314` and a capture channel.
**Raw data:** `tests/qa_final.json` (every record), `tests/QA_ROMAN_URDU_APPENDIX_CASES.md` (one row per test with all the requested fields), harness `tests/qa_live.py`, `qa_battery.py`, `qa_compile.py`.

> **Bottom line: "broad Roman Urdu coverage" cannot be claimed yet.** Clean and compressed *single* commands work well (~80–90%). But number words ("dhai hazar", "paanch sau") fail 8/8, multi-action messages pass only 35%, missing-detail follow-ups pass 71%, and there are unsafe saves for ambiguous financial commands. Three results are critical because a wrong or missing financial record is created.

---

## 1. Headline numbers

| Measure | Result |
|---|---:|
| Interactions executed and recorded | 356 (plus ~60 unrecorded set-up messages) |
| Scored test cases | **334** |
| **Passed** | **269** (80.5 %) |
| **Partially passed** | **23** |
| **Failed** | **42** |
| Strict pass rate (partial = not a pass) | **80.5 %** (84.0 % if partial counts half) |
| Excluded: inconclusive (blocked by a one-time setup question or consumed by an earlier pending question) | 12 |
| Excluded: state-verification reads after multi-action tests | 10 |
| LLM/backend failures | **0** (no step needed a retry) |

How I graded: a test passes only if the intent, entities, context, clarification behaviour and safety are all right *and* no part of the request is ignored. A yes/no confirmation card before saving counted in the bot's favour. A guessed value that gets **saved** counted against it. Where the same sentence behaved differently on different runs I graded it Partial (see §6).

Failure types (non-pass tests): Logic 16 · NLU 14 · Entity 14 · Safety 12 · Context 9 · Backend 0. Severity: Critical 3 · High 21 · Medium 28 · Low 13.

## 2. Results by feature

| Feature | n | Pass | Partial | Fail | Pass % | Note |
|---|--:|--:|--:|--:|--:|---|
| Employee (add/list/remove) | 43 | 34 | 1 | 8 | 79 | Fully-specified adds 11/11; every missing-detail case fails |
| Party khata | 42 | 31 | 5 | 6 | 74 | Number words and unsafe direction guesses |
| Party/cash variants (extra batch) | 40 | 32 | 4 | 4 | 80 | |
| Stock + bills + sales | 34 | 32 | 0 | 2 | 94 | Strongest area when the sentence is clean |
| Cash book / expenses / banks | 23 | 20 | 1 | 2 | 87 | Plus bank/transfer 3/3 |
| Reports / "casual memory" phrases | 27 | 22 | 3 | 2 | 81 | Date and multi-report problems |
| Reminders, statements, memory, language | 11 | 10 | 1 | 0 | 91 | "kal 5 baje" → 5 AM |
| Context / follow-ups | 30 | 24 | 2 | 4 | 80 | |
| Conversation / greetings | 23 | 19 | 0 | 4 | 83 | |
| Compressed set | 12 | 7 | 1 | 4 | 58 | "ali add kr" for an existing Ali |
| **Multi-action** | 12 | 4 | 3 | 5 | **33** | Worst area |
| Wrong/accidental input, orphan tokens | 21 | 21 | 0 | 0 | 100 | Safe "samajh nahi aaya" with nothing saved |

## 3. Results by Roman Urdu style (by test label)

| Style | n | Pass % | Verdict |
|---|--:|--:|---|
| Misspelled / alternate spellings (kia/kiya, sey/nay/dey, CAPS, hy/h) | 9 | 100 | Strong |
| Compressed / very short (single commands) | 51* | 92 | Strong (*includes 14 orphan tokens that must be refused) |
| Casual / Karachi / slang | 38 | 89 | Good |
| Normal / clean | 117 | 82 | Good, but includes first-run cases |
| Follow-up / context / missing detail | 74 | 81 | Mixed |
| Mixed Urdu-English | 10 | 80 | Good |
| Ambiguous / unsafe-if-guessed | 44 | 59 | **Weak** |
| Multi-action | 20 | 35 | **Weak** |
| **Roman Urdu number words** | 8 | **0** | **Total failure** |

## 4. Required focus areas

| Area | n | Pass | Partial | Fail | Pass % |
|---|--:|--:|--:|--:|--:|
| Compressed Roman Urdu where intent must be inferred (`ali add kr`, `2k udhr`, `kl ki sale`, `5k aya`) | 29 | 24 | 1 | 4 | 83 |
| Casual report/memory phrases (`aj ka scene bta`, `kya record kiya tha`, `is month ka kya scene hai`) | 50 | 44 | 3 | 3 | 88 |
| Multi-action messages | 20 | 7 | 4 | 9 | **35** |
| Missing-detail follow-ups | 41 | 29 | 3 | 9 | 71 |
| Context retention, pronouns, references | 60 | 48 | 5 | 7 | 80 |
| Ambiguous / unsafe-if-guessed financial commands | 44 | 26 | 10 | 8 | **59** |
| Roman Urdu number words | 8 | 0 | 0 | 8 | **0** |
| Spelling / orthography variants | 9 | 9 | 0 | 0 | 100 |

**Compressed.** Good at intent: `aj ka hisab`, `cash kitna`, `ali ka khata`, `uska hisab bta`, `kitna bnta` (it used the last-named party), `ali ko 3k udhr de dia`, `2k ali` (asks direction). Failures: `ali add kr` and `ali ko dal` when Ali already exists reply "Ali naya hai" and offer a duplicate; `5k aya` / `3k gya` are saved instantly as cash in/out; `kl ki sale` returned a profit report.

**Casual report/memory.** Better than expected: `aj kya hua`, `aj ka scene bta`, `kitna gaya`, `pichle hafte ka scene`, `mene ali ka kuch dala tha?`, `kya record kiya tha`, `kal jo entry ki thi wo dikhao` all work. Failures: `wo 500 wala entry dikha` → party list; `parso ki sale` → today's profit; `kal ka profit` returned today's date in one run; `kal ki sale … aur aj ka expense` answered only half.

**Multi-action (worst).** From the 12 follow-through chains: fully correct 4 (`Ahmed ko customer add karo aur 2500 udhar`, `5000 sale aur 1000 expense`, `Ali ko 100 diye aur Ahmed se 200 liye`, 3 expenses in one line – all with a confirm card, which is the right design). Partially correct 3. **Failed 5 by silently dropping a part:**
- `Ali ko 300 diye aur kal yaad dila dena…` → only the reminder was created; the Rs 300 entry vanished (**Critical**).
- `2 charger 3000 ke sell kiye aur 500 delivery wale ko diye` → run A: bill ok, delivery expense saved as **Rs 1** (**Critical**); run B: qty dropped, rate=3000, the 500 became "paid_amount"; run C: asked for a customer for udhaar nobody mentioned.
- `socks ka rate 35 kar do aur charger ka 1600` → charger ignored.
- `ali ka khata dikhao aur ahmed ka bhi` → Ahmed ignored.
- `Rizwan ko employee add karo … aur uski salary 30000 rakhdo` → salary ignored; confirm card does not even mention it.

**Missing-detail follow-ups.** Works for money drafts (bot asks "Kitne paise?", "Ali ko diye / Ali se liye?", "naya customer/supplier?", stock "udhaar/cash/online?") and answers like `pehla wala`, `liye`, `nahi supplier hai`, `cash se`, `2 hazar` are understood. **Fails completely for employees**: `usman ko staff me dal` → generic how-to, nothing stored; the next message (`03331000015`) → "samajh nahi aaya". Same for `employee add krdo` → `Rizwan` → `0333…` (and `Rizwan` is answered in *English*). Also `han` to a 1/2 question → "samajh nahi aaya" and the question is silently dropped; `chai` after the amount 500 made the bot forget the 500.

**Context / pronouns.** Strengths: `uska number …` and `uska hisab bta` correctly resolve to the party just used; `nahi 900 the`-style corrections become "Rs 450 → Rs 540, theek hai?" cards; `usko 500 de` / `2 hazar uske account me` with no antecedent ask "Kis ka hisaab hai?". Weaknesses: `purana wala hata do` proposed the *latest* entry; `kal wala change krdo` guessed the opening-balance row; `rehne do` with nothing pending produced a **delete-entry card** once (and "samajh nahi aaya" in another run).

## 5. Most common failure patterns

1. **Number words are not parsed at all.** `dhai hazar`, `paanch sau`, `dedh hazar`, `teen hazar`, `do sau`, `ek hazar`, `teen socks aur do charger` – 8/8 fail ("kitne paise?"). Cause: `app/services/amounts.py` only reads digits (`k`, `hazar`, `lakh` after a digit work). Safe, but this is everyday shopkeeper speech.
2. **Multi-action: the second clause is dropped without telling the user**, in 9 of 20 tests. The reply talks only about the part that ran.
3. **Missing-detail answers are not remembered for employees** (no pending state is stored); money drafts do store it.
4. **Guessing direction/source when the message is thin and saving anyway** (`ali ko 500 daldo`, `Ali ko 500`, `500rs ali ko`, `5k aya`, `3k gya`, `ali nay kaha kal dega` → reminder, `ali ko 500 pay kardo`).
5. **Same sentence, different result on different runs** (5 documented cases, §6). Likely cause: calls rotate across 3 providers / many models, with no deterministic rule layer for high-frequency phrases.
6. **Dates in casual words**: `parso`, `kal ka profit` – wrong date or wrong report in some runs (`pichle mangal` → 29 Sep worked).
7. **One-time setup questions interrupt real actions** and can swallow the user's next message: opening cash, "kis category?" for every new expense word, shop address/phone for bills. `skip` for the shop details is **not remembered** (`draft["shop_asked"]` lives only in the draft), so every sale asks again.

## 6. Non-determinism evidence (matters for any "coverage" claim)

| Message | Result A | Result B |
|---|---|---|
| `boss kal ka profit?` | profit for **5 Oct** (wrong) | profit for 4 Oct |
| `bro aaj ki sale kitni hui` | profit report | bills/sale report |
| `5k add kr` | cash entry + opening-cash question | asks "Kis ka hisaab hai?" |
| `500` after `expense add kr` | saved as expense out | asks cash in/out first |
| `rehne do` (nothing pending) | delete-entry card | "samajh nahi aaya" |

## 7. Critical and high-severity failures

**Critical (wrong/missing financial record):**
- **AMB-01** `ali ko 500 daldo` → saved as "Ali ko Rs 500 diye" with no question.
- **MUL-01** delivery expense of Rs 500 saved as **Rs 1**.
- **MUL-12** `Ali ko 300 diye aur kal yaad dila dena…` → the Rs 300 entry silently lost.

**High:** CTX-27 `50 socks aye bilal se` saved as udhaar (Bilal ko dene hain Rs 1,000) though payment was never stated · ACC-01 `Ali ko 5000000 diye` saved instantly (cash went −Rs 4.99 M) · MUL-11 / RPT-17 dropped second clause · number words (8) · RPT-25 `parso ki sale` · employee missing-detail chain (EMP-12/13/14/16/17) · EMP-18 salary ignored.

## 8. Entity-extraction problems
- Number words (above). `Ali ko 5oo diye` (letter o) correctly asks for the amount.
- `500 delivery wale ko` inside a sale sentence extracted as paid_amount / Rs 1 / lost.
- Quantity dropped when a price follows (`2 charger 3000 ke` → qty null, rate 3000) – this also appeared in the earlier session as `20 cost 100 pieces`.
- Generic noun taken as a name (`3k supplier ko diya` created a party literally named "supplier").
- Relative dates: `parso` ignored; `kal 5 baje` → 05:00 **AM**.
- Correct: `2k`, `1.5k`, `1 lakh`, `5 hazar`, `500.50`, `0 / -500` (refused), phones in `0333-1234567`, `+92 333…`, `3331234567`, short/invalid phones rejected, `pichle mangal`, `kal`, `parso Ali ko 400 diye the` (3 Oct), CAPS names.

## 9. Context-understanding problems
Employee follow-ups not stored · `han` to a numbered question drops the question · `chai` after an amount forgets the amount · `rehne do`/`cancel` replies "samajh nahi aaya" instead of acknowledging · single-word replies (`Rizwan`, `cash`) sometimes answered in English even when the user writes Roman Urdu.

## 10. Unsafe assumptions (serious by the brief's definition)
AMB-01, AMB-11, VAR-08 (direction guessed) · CMP-11/12 (`5k aya`, `3k gya` saved with no source/purpose) · CTX-27 (payment method guessed = credit) · ACC-01 (Rs 5 M with no sanity check) · VAR-09 (a remark created a reminder) · ENG-02 (`pay kardo` saved as paid) · VAR-40 (`kaam tamam 200 aaye hain`) · DUP-02/DUP-11 (identical entry saved twice with no warning) · VAR-13 (`bijli ka bill aya hai 4000` treated as paid expense).
Good safety behaviour observed: asks direction for `ali 500`, `ali k 500 likh lo`; asks name for `usko 500 de`, `usko payment krdi`; refuses `-500`, `0`, `5oo`; asks before a new party is created (`aly`, `alii`, `Kokab`, `Zeeshan` – no silent duplicate); asks yes/no before delete/edit/cancel; refuses overselling (`1000 charger` when 20 in stock); `sab kuch delete kr do` / `mera sara record mita do` → nothing deleted.

## 11. Backend / system failures
**None.** 331 messages reached the LLM classifier; no step returned an AI error or needed a retry. (The earlier Groq-only run hit 429 throttling; the key rotation fixes that.) Note in the other direction: two replies were English for Roman Urdu input, and the generic "samajh nahi aaya" is shown for genuine non-understanding only – I found no case where infrastructure failure hid behind it in this run.

## 12. Broad Roman Urdu coverage assessment

| Category | Evidence | Rating |
|---|---|---|
| Clean Roman Urdu | stock/bills 94 %, cash 87 %, employee full commands 11/11 | **Good** |
| Casual Karachi Roman Urdu | 89 % | **Good** |
| Misspellings / alternate spellings | 100 % (9/9) | **Good** |
| Compressed Roman Urdu | 83 % | **Fair** – intent mostly right, a few unsafe saves |
| Mixed Urdu-English | 80 % | **Fair** |
| Slang | 89 %, but `kaam tamam 200 aaye hain` guessed | **Fair** |
| Casual accounting/report language | 88 %, date and double-report gaps | **Fair** |
| **Multi-action messages** | 35 % | **Fail** |
| **Missing-detail conversations** | 71 % (employees ~0 %) | **Fail for employees / Fair elsewhere** |
| Follow-up messages | ~80 % | **Fair** |
| Context-dependent references (uska/woh) | pronouns for last party work; "purana/kal wala" guessed | **Fair** |
| Entity extraction | digits good; **number words 0/8**; relative dates weak | **Fail** |
| Ambiguous financial commands | 59 % | **Fail** |
| Safe clarification | strong for names/direction in drafts, weak for bare amounts and big amounts | **Fair** |

**Can this bot reasonably claim broad Roman Urdu coverage?** **No.** It understands normal, misspelled, casual and compressed *single-intent* Roman Urdu well. It does not reliably handle number words, multi-action messages, missing-detail follow-ups for employees, ambiguous financial commands, or casual dates, and it behaves differently on repeated runs. Claim instead: **"works with everyday single commands in Roman Urdu, including common spelling variants and shorthand."**

## 13. Recommended improvements (priority order)
1. **Never drop a clause silently.** If a message contains more than one amount-bearing clause or verb group and the classifier returns one intent, route to the confirm-card path or say "pehle X kar diya, Y bhi karun?". Echo every action performed. Fixes MUL-01/11/12, RPT-17, MUL-08, EMP-18.
2. **Parse Roman Urdu number words in code** (`amounts.py`): ek, do, teen … das, bees, tees, chalis, pachas, saath, sattar, assi, nabbe, sau, dhai (2.5), dedh (1.5), sawa (1.25), paune, hazar, lakh, "paanch sau", "dhai hazar", "sawa sau". Extend "amount must appear in the message" accordingly.
3. **Ask, don't guess, direction/source**: `X ko 500`, `500rs X ko`, `X ko N daldo`, `5k aya`, `3k gya`. Show "1) Ali ko diye 2) Ali se liye" like `ali 500` already does.
4. **Store partial details in the pending state for employees** (and any intent that says "how to write"). Merge the next message (name or number). Re-ask on invalid answers (`han` to 1/2) instead of dropping the question.
5. **Sanity guards**: confirm amounts above a per-shop threshold (e.g. > 10× the recent largest, or > Rs 1,000,000); warn on an identical entry within 2 minutes; payment method for stock-in with a named supplier must be asked.
6. **Deterministic phrase layer before the LLM** for high-frequency forms (`aj ka hisab`, `cash kitna`, `X ka khata`, `rehne do`/`cancel`/`chor do`, `shukriya`, relative dates `kal/parso/pichle <weekday>`). Reduces cross-run variance.
7. **Dates and times**: handle `parso`; resolve `5 baje` to PM for shop hours or ask AM/PM.
8. **Persist `skip` for shop details**, ask category once with a default ("Rickshaw (nayi)" auto-accept) or save and ask later; make opening-cash a non-blocking question.
9. **Existing party**: `ali add kr` for an existing Ali → "Ali pehle se hai"; "party" word `supplier`/`customer` must not become a name.
10. **`rehne do` / `cancel` with nothing pending** → "Theek hai" (never a delete card); `shukriya`, `tm kon ho`, mild rude text → friendly help.

## 14. Additional Roman Urdu training / regression examples
```
ali ko dhai hazar udhaar diye            -> party_entry gave 2500
paanch sau ali se liye                   -> party_entry got 500
dedh hazar ka maal bilal se udhaar       -> party_entry got 1500
teen socks aur do charger bech diye      -> create_bill 3 socks, 2 charger
sawa sau chai ka kharcha                 -> cash_entry out 125
ali ko 500 daldo / ali ko 500 / 500rs ali ko   -> party_entry direction=null (ask)
5k aya / 3k gya                          -> cash_entry direction known, source asked
kal ki sale dikhao aur aj ka expense bhi batao -> bill_report(kal) + money_report(aj)
ali ka khata dikhao aur ahmed ka bhi     -> party_balance x2
Ali ko 300 diye aur kal yaad dila dena   -> party_entry + set_reminder
socks ka rate 35 aur charger ka 1600     -> edit_item x2
usman ko staff me dal                    -> add_employee name=Usman phone=null (ask phone)
parso ki sale                            -> bill_report 3 Oct
kal 5 baje yaad krwana                   -> set_reminder 17:00 (or ask AM/PM)
rehne do / chor do / bas karo            -> cancel pending, "Theek hai"
shukriya bhai / tm kon ho bhai / mere bhai tum kiya karhe ho  -> greeting/help
```

## 15. Areas needing more testing
Urdu-script messages; voice-note transcripts; photos / OCR with Roman Urdu captions; two people (owner + employee) messaging at once and message ordering per phone (**reminder: you asked to be reminded about this**); staff permissions; PDF content correctness; reminders actually firing; bank/wallet flows beyond JazzCash; multi-shop owners; long conversations (> 5 messages of history); rate-limit behaviour at production volume; repeating this suite 3× to quantify run-to-run variance.

## 16. Readiness for real Karachi shopkeepers
**Not ready for unsupervised use.** Safe to pilot with a few friendly shops *only if* (a) items 1–5 above are fixed first (silently dropped clauses, number words, thin-message direction guesses, employee follow-ups, big-amount guard) and (b) shopkeepers are told to write one action per message. Today a shopkeeper who says "dhai hazar" gets re-asked, one who says two things gets half of it recorded without being told, and a thin message like "ali ko 500 daldo" can write a wrong khata entry.

## 17. Final decision
**"Broad Roman Urdu coverage" cannot currently be claimed.** Claim "everyday single commands in Roman Urdu with common spellings and shorthand". Re-run this suite after fixes 1–5; the target for the claim should be ≥ 90 % on multi-action, missing-detail, number-word and ambiguous-command categories with **zero** critical safety failures.

---
*Housekeeping:* the run created 15 synthetic users/shops in the live database (phones `999000000201` and `999000000301`–`314`) with test entries; delete them if you do not want them kept. No real number was contacted.
