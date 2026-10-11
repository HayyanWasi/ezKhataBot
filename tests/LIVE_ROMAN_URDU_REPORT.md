# EzKhata live Roman Urdu bot report

Date: 2026-10-05. Tested the **real `handle_message` pipeline**, Groq classifier, Supabase persistence, and CLI reply channel. LangSmith tracing was disabled. All writes were confined to synthetic phone `999000000000001`, shop `EzKhata Roman Urdu Audit Shop`; the confirmed employee uses synthetic phone `999000000000002`. No WhatsApp messages were sent. The shop and its test records remain in Supabase for inspection. This verifies live bot processing, not WhatsApp transport.

The final run covered **33 live messages: 30 passed and 3 failed** against the stated intent and logical expectations. [Single-message results](live_roman_urdu_results.json) contain the full request, stored intent, actual reply, delivery status and pending state for 18 cases. [Multi-turn results](live_roman_urdu_followup_results.json) contain the same evidence for 10 more messages. [Accounting results](live_roman_urdu_accounting_results.json) preserve the exact replies for the other five. A separate [offline audit](ROMAN_URDU_AUDIT_REPORT.md) covers 91 deterministic checks.

## Single-message cases: 17/18 passed

| # | Exact input | Stored intent | Actual result | Verdict |
|---:|---|---|---|---|
| 1 | `kiya kar rha hai tou?` | greeting | Roman Urdu greeting | Pass |
| 2 | `kya krrhe ho aap?` | greeting | Roman Urdu greeting | Pass |
| 3 | `kya krrhe ho tum?` | greeting | Roman Urdu greeting | Pass |
| 4 | `mere bhai tum kiya kaarhe ho?` | greeting | Roman Urdu greeting | Pass |
| 5 | `mere bhi tum kiya karrhe ho?` | greeting | Roman Urdu greeting | Pass |
| 6 | `oye tou kya karha hai?` | help | Roman Urdu feature list | Pass |
| 7 | `abe tu kya kr raha hai?` | unknown | “Maaf kijiye, samajh nahi aaya” | **Fail** |
| 8 | `assalam o alaikum bhai` | greeting | Roman Urdu greeting | Pass |
| 9 | `employee add karo Ali and number` | add_employee | Asked for name and WhatsApp number | Pass, though it could ask only for the missing number |
| 10 | `add employee ali 0333` | add_employee | Rejected incomplete number | Pass |
| 11 | `add ali number` | add_employee | Asked for name and number | Pass |
| 12 | `ali ko add kardo 03323` | add_employee | Rejected incomplete number | Pass |
| 13 | `ali ko add kr oska number ye hai` | add_employee | Asked for name and number | Pass |
| 14 | `oye ali ko employee add kr 999000000000002` | add_employee | Asked for explicit confirmation, no immediate employee write | Pass |
| 15 | `employees dikhao` | list_employees | Reported no employees after #14 was cancelled | Pass |
| 16 | `aaj ka hisaab dikhao` | money_report | Correctly reported no cash entries yet | Pass |
| 17 | `Ali ka udhaar kitna hai?` | party_balance | Correctly reported no Ali party | Pass |
| 18 | `yaar kal ka munafa batao` | profit_report | Correctly reported no sale on 4 Oct | Pass |

## Multi-turn logic: 9/10 passed

| # | Message | Actual bot reply or state | Verdict |
|---:|---|---|---|
| 1 | `Ali ko employee add karo 999000000000002` | Asked to confirm Ali, number and shop | Pass |
| 2 | `haan ji` | Added Ali, cleared pending confirmation | Pass |
| 3 | `employees dikhao` | Listed exactly one employee: Ali | Pass |
| 4 | Repeat add request for Ali and same number | Said Ali is already an employee | Pass |
| 5 | `Ali ko employee se hatao` | Asked for removal confirmation | Pass |
| 6 | `nahi` | Cancelled removal | Pass |
| 7 | `employees dikhao` | Ali still listed | Pass |
| 8 | `employee add karo Sana and number` | Asked for name and number | Pass for safe handling; wording is unnecessarily generic |
| 9 | `999000000000003` | Asked for name and number again, without carrying forward Sana | **Fail** |
| 10 | `employees dikhao` | Ali still the only employee; no accidental Sana account | Pass |

The live `haan ji` success is significant: the deterministic yes/no parser did not recognize this spelling in the offline audit, but the AI pending-answer route recognized it. That leaves the flow dependent on provider availability for this common reply.

## Accounting flow: 4/5 passed

| Message | Stored intent and actual bot result | Verdict |
|---|---|---|
| `chai 200` | `cash_entry`; asked for the shop's opening cash | Pass |
| `0` | `cash_entry`; asked which category to use for Chai | Pass |
| `1` | `cash_entry`; saved Rs 200 expense in Chai, showed cash −Rs 200 | Pass |
| `aaj ka cash dikhao` | `unknown`; replied “samajh nahi aaya” | **Fail** |
| `aaj ka hisaab` | `money_report`; showed opening Rs 0, outgoing Rs 200, closing −Rs 200, Chai Rs 200 | Pass |

The stored state was verified separately: the synthetic shop had **one active employee**, and the saved cash report reflected the expense. The bot did not invent a party balance or profit in the empty shop.

## Reliability issue observed

At a rapid request pace, all three configured Groq keys returned rate-limit/busy errors after the first three successful calls. The bot stored and delivered a generic `unknown`/“not understood” reply for the next messages. After slowing requests and rerunning them, those messages passed except `abe tu kya kr raha hai?`. The initial rate-limited outcomes were excluded from the 33 final case verdicts. The bot should distinguish a temporary provider failure from a genuinely unrecognized phrase so users are not told their wording was wrong when service capacity is the cause.

## Priorities

1. Preserve the known employee name while asking for a missing phone. `Sana` followed by a bare number should lead to a confirmation of Sana and that number.
2. Add `aaj ka cash dikhao` and other natural report variants to live classification evaluation; it is described in the `money_report` intent yet failed in this run.
3. Expand casual and rude phrasing coverage, including `abe tu kya kr raha hai?`, and test neighboring spellings.
4. Make temporary AI rate limits produce a retry message instead of a comprehension failure.
5. Improve the local confirmation parser and phone validation identified in the offline audit.

Roman Urdu has open-ended spelling and regional variation, so no finite suite proves all accents. This report records the exact behavior observed from the live bot for these cases and preserves the full responses in the JSON result files.
