# EzKhata live Roman Urdu QA report

**Test date:** 2026-10-05  
**Target:** real EzKhata message pipeline, configured `openai/gpt-oss-120b` Groq classifier, Supabase-backed synthetic shop, and CLI delivery channel.  
**Isolation:** synthetic owner `999000000000001`, shop `EzKhata Roman Urdu Audit Shop`, synthetic employees only. No WhatsApp message was sent to a real person. LangSmith tracing was disabled.

## Executive result

| Measure | Result |
|---|---:|
| Live interactions executed | 71 |
| Passed | 62 |
| Partially passed | 1 |
| Failed | 8 |
| Strict pass rate | 87.3% |
| Roman Urdu live classifier decisions | 38 |
| Full end-to-end bot messages | 33 |

The bot is usable for many everyday Karachi shopkeeper phrases: greetings, help, party entries, adding parties, cash entries, transfers, stock in/out, bills, reminders, employee actions, account reports, corrections, statements, and language/shop controls. It is **not ready to claim broad Roman Urdu coverage**. Very compressed wording, some casual memory/report phrases, multi-action messages, and missing-detail follow-ups fail or become unsafe. Groq token throttling also becomes user-visible as “not understood.”

## Evidence and exact test-case records

Every executed classifier case contains the requested test ID, feature, user message, Roman Urdu style, expected intent/entities/behavior, actual classifier JSON, intent/entity judgement, status, severity, explanation, and suggested fix:

- [38 live classifier cases and exact outputs](roman_urdu_live_matrix_results.json)
- [60-case adversarial source matrix, including cases not completed because the live provider throttled](roman_urdu_live_matrix.jsonl)
- [18 end-to-end single-message cases](live_roman_urdu_results.json)
- [10 end-to-end context and employee-flow cases](live_roman_urdu_followup_results.json)
- [5 end-to-end accounting-flow cases](live_roman_urdu_accounting_results.json)
- [reproducible live classifier runner](run_live_roman_urdu_matrix.py)

The test source has 60 diverse Roman Urdu cases. Thirty-eight completed live classifier runs. The remaining 22 are explicitly **not counted as passes**; the configured Groq model needs about 7,400 tokens per full intent prompt and repeatedly returned 429 token-per-minute errors despite 25–45 second pacing. The 33 end-to-end cases fill key workflow coverage, but do not convert unexecuted matrix cases into passes.

## Results by feature

| Feature | Live result | Notes |
|---|---|---|
| Conversation and help | 14 pass, 2 fail | `kia krra` and `abe tu kya kr raha hai?` were not understood. Other `kya/kiya`, `kr rha`, `aap/tum`, polite, casual and rough examples passed. |
| Language and shop selection | 4 pass | English/Roman Urdu preference plus current/switch-shop recognition passed. |
| Memory | 3 pass, 1 fail | Save and forget variants passed. `kya kya yaad hai tmhe` was misclassified as reminder list. |
| Party khata | 8 pass, 1 fail | Entries, customer add, party phone, balance, correction, deletion and statement passed. `sab udhar dikhao` became `statement`, not party list. |
| Cash and transfers | 8 pass, 1 fail | Cash entry and cash report flow work. `aaj ka cash dikhao` was not understood; `aaj ka hisaab` showed the saved Chai expense correctly. |
| Stock | 2 pass, 1 partial, 1 operational fail | Stock in/out passed. Item add confused purchase price and quantity. Stock-report classifier run hit a provider 429. |
| Billing | 2 pass | Bill creation and bill retrieval passed. Cancellation remains in the uncompleted live matrix. |
| Profit and recent activity | 1 pass | The live pipeline correctly reported no prior-day sale. The live matrix’s casual latest-customer variant remains uncompleted. |
| Reminders | 1 pass | Creating a reminder passed. List/cancel variants remain in the uncompleted matrix. |
| Employees | 18 pass, 1 fail | Add, confirmation, duplicate prevention, list, removal prompt and cancelled removal passed. Missing-number follow-up discarded the employee name. |
| Multiple actions | 1 fail | Two requested entries were reduced to only the first party entry. |
| Pending context | 1 pass | `haan ji` was resolved as a confirmation in the live employee flow and classified as a pending answer. |

## Roman Urdu writing-style coverage

| Style | Observed live result |
|---|---|
| Normal Roman Urdu | Passed across greetings, party, cash, stock, bills, reminders, employees. |
| Karachi casual | Mostly passed: `mere bhai...`, `bhai dusri shop...`, stock-in phrasing. |
| Very short and compressed WhatsApp | Mixed: `kya kr rhy` passed; `kia krra` failed. |
| Missing vowels and spelling variants | Mostly passed for `kr`, `rhy`, `udhar`, `hogye`, `remider`; not reliable enough for all compressed forms. |
| Repeated letters | `kyaa kr rhe ho` passed after rate-limit-aware retry. |
| Urdu–English / English–Urdu mix | Passed for language, employee add, customer add, bank/transfer and stock examples tested. |
| Informal grammar and no punctuation | Passed for several party, cash and stock actions. |
| Polite requests | Passed for help, statement, bill retrieval and reminder. |
| Rough non-abusive tone | `oye tou kya karha hai` gave help; one `abe...` variation failed. |
| Names, numbers, amounts, quantities and dates | Phone and amount extraction passed for party, employee, cash and transfer cases. Stock item add failed to preserve both cost and quantity. |
| Context-dependent replies | `haan ji` worked. Bare employee phone after a missing-phone request failed. |

## Confirmed failures and severity

| ID / flow | User message | Actual behavior | Severity | Suggested fix |
|---|---|---|---|---|
| RU-006 | `kia krra` | `unknown` | Medium | Add compressed conversational variants and a semantic greeting/help fallback. |
| Pipeline social | `abe tu kya kr raha hai?` | “samajh nahi aaya” | Medium | Add casual Karachi rough-tone paraphrases; preserve a calm help response. |
| RU-015 | `kya kya yaad hai tmhe` | `list_reminders` | Medium | Separate `yaad hai` (memory) from `reminder` terms in examples and evaluation. |
| RU-022 | `sab udhar dikhao` | `statement` | High | Route plural credit/balance requests to party list/balances; reserve statement for explicit statement wording. |
| Stock entity extraction | `socks add karo 30 sale rate 20 cost 100 pieces` | Cost=`100`, quantity absent | High | Add examples where cost and quantity appear consecutively; validate that all stated numeric tokens are represented before committing. |
| Multi-action | `Ali ko 500 diye aur chai 100 ka kharcha likh do` | Only `party_entry`; Chai expense lost | Critical | Detect two financial clauses and route to `many_entries`; block commit or ask confirmation when an amount-bearing clause is unparsed. |
| Employee context | `employee add karo Sana and number` → `999000000000003` | Asked for both fields again; Sana lost | High | Store pending `add_employee_details` with known name, then merge the bare number safely. |
| Cash report wording | `aaj ka cash dikhao` | `unknown`; supported `aaj ka hisaab` works | High | Add direct cash-report variants to classifier examples and regression suite. |
| Provider capacity | Several requests | 429 then a generic unknown reply | High operational | Reply “service busy, please retry” and do not label it as comprehension failure. Reduce classifier prompt size or use a provider/model with adequate token capacity. |

## Entity extraction findings

Correct extraction was verified live for party names, customer name, employee name/phone, party phone, Rs 500/Rs 1,200/Rs 3,000/Rs 5,000 amounts, 50 and 5 stock quantities, JazzCash, bill 3, and reminder party Ali. The important exception was item creation: `20 cost 100 pieces` became purchase price 100 and omitted quantity 100. The downstream write guard should compare every number in the message with extracted fields and ask a clarification before mutating stock.

## Context and logical behavior

The bot safely asks for confirmation before employee add/removal, prevents a duplicate employee, preserves the employee after `nahi` cancels removal, and records a cash expense only after opening-cash/category questions. The audited cash report showed opening Rs 0, outgoing Rs 200 and closing −Rs 200 after the Chai entry.

The bot does not retain `Sana` during a later bare-number reply. This is a real conversational-state defect. It also incorrectly treats provider rate limits as comprehension failures, which makes real users blame their own wording.

## Recommended improvements

1. Add the confirmed failing phrases to regression data: `kia krra`, `abe tu kya kr raha hai`, `kya kya yaad hai tmhe`, `sab udhar dikhao`, `aaj ka cash dikhao`, and the multi-action example.
2. Add deterministic phrase guards before the LLM for high-frequency flows: cash report, employees, party balance/list, and yes/no confirmations.
3. Store partially collected fields in pending state. A detail prompt should retain `Sana` and accept a later number.
4. Validate all amount/quantity tokens before commit. If two numbers appear in item creation, the bot must account for both or clarify.
5. Make multi-action parsing safety-first: never silently drop a money clause.
6. Replace the generic unknown response after LLM errors with a retry message. The Groq 8,000 TPM limit cannot reliably support a classifier request reserving about 7,400 tokens each time.
7. Complete the 22 pending live cases after upgrading capacity or shrinking the production intent prompt. These include stock reporting/edit/delete/photo, bill cancellation, reminder list/cancel, extra employee spellings/removal, unknown input, and cancellation phrasing.

## Additional Roman Urdu training examples

```text
kia krra bhai
abe tu kya kr raha h bot
kya kya yaad hy tmhe
sab udhar walay dikha do
aaj ka cash dikha
Sana ko employee add karo, number baad mein deta hun
Sana ka number 03001234567
Ali ko 500 diye aur chai ka 100 kharcha bhi likh
socks add 30 sale 20 cost 100 pcs
50 jurab ayi Bilal se udhar
bill 3 ko radd krdo bhai
meri remider list dikha
Ali wali yaad-dihani hata do
```

## Final assessment

EzKhata has a solid base for normal Roman Urdu business messages and cautious financial workflows. It is **not yet ready for unrestricted real Karachi shopkeeper traffic** because the failures are concentrated in exactly the kind of compressed, casual, multi-action, and follow-up messages common on WhatsApp. Resolve the critical multi-action loss, missing-detail context loss, cash-report phrasing gap, and provider-error handling before broader rollout. Then rerun the saved 60-case matrix plus a WhatsApp transport test on an isolated number.
