# EzKhata Roman Urdu and logic audit

Date: 2026-10-05. Code revision: working tree at audit time.

## Scope and result

I ran 91 offline, read-only checks against the current Python code. **74 passed and 17 failed.** Every input, expected value, actual value, and pass/fail result is in [roman_urdu_audit_results.json](roman_urdu_audit_results.json). The reproducible runner is [roman_urdu_audit.py](roman_urdu_audit.py).

| Area | Passed | Failed | What was exercised |
|---|---:|---:|---|
| Language fallback | 41 | 4 | 45 Roman Urdu and English spellings, including casual, direct and rude wording |
| Phone normalization | 7 | 2 | Pakistani formats, incomplete numbers and implausible digit strings |
| Confirmation parsing | 11 | 9 | 20 ways to accept or reject an action |
| Employee flow | 14 | 1 | Missing name/number, short number, confirmation, cancel and valid acceptance, with the classifier output supplied by the test |
| Owner permission | 1 | 0 | Staff member attempting to add an employee |
| Pending answer routing | 0 | 1 | Whether `haan ji` is recognized as a direct answer |

The audit did **not** establish actual AI intent recognition. The configured AI provider was unreachable from the sandbox. A request for external access was rejected by automatic approval review because the call would send the user text and the bot's internal prompt and intent definitions to an external AI provider whose destination and payload had not been explicitly approved. I did not bypass that rejection. There was no WhatsApp delivery test and no live Supabase write. Consequently, the examples below marked as language checks prove only the local language fallback, while employee flow checks start after supplying plausible extracted fields.

## Findings

### 1. Common Roman Urdu phrases can fall back to English

The local fallback is a fixed word list. It classified these Roman Urdu inputs as English when the prior conversation language was English:

| Input | Expected | Actual |
|---|---|---|
| `assalam o alaikum` | `roman_ur` | `en` |
| `add employee ali 03331234567` | `roman_ur` | `en` |
| `add ali number` | `roman_ur` | `en` |
| `mujhse roman urdu me baat kro` | `roman_ur` | `en` |

The five user examples beginning `kiya kar rha hai tou?`, `kya krrhe ho aap?`, `kya krrhe ho tum?`, `mere bhai tum kiya kaarhe ho?`, and `mere bhi tum kiya karrhe ho?` all passed this **language fallback** check. So did `oye tou kya karha hai?`. Their greeting/help intent and reply were **not** verified because those need the AI classifier.

The fallback matters when a command or short answer skips AI, and before an AI result is available. In normal classified messages the model can override this guess, so these four failures do not by themselves prove the final reply language will be wrong.

### 2. Confirmation wording is too narrow

`hanji`, `haan ji`, `han g`, `kr do`, and `kar do` were not accepted as yes. `na ji`, `mat karo`, `rehne do`, and `nahin` were not accepted as no. The parser returned `None` for all nine, so the add employee resolver asked for yes/no again. `haan ji` also failed the trivial answer routing check, meaning it would require the AI path instead of the reliable local resolver.

Positive checks included `haan`, `han`, `haa`, `ji`, `jee`, `theek`, and `yes`. Negative checks included `nahi`, `nhi`, `nai`, and `no`.

### 3. Plausible looking but invalid phone numbers are accepted

`normalize_phone` accepted `1234567890` and `999999999999999` because it checks only that there are 10 to 15 digits. In the mocked employee flow, `Ali ko add karo 1234567890` proceeded to a confirmation prompt. This could create an unusable employee account if the owner confirms. The test expected rejection under a Pakistani WhatsApp number policy. If international employee numbers are intentionally supported, use a country aware validation rule and define the accepted formats explicitly.

Incomplete numbers `0333` and `03323` were correctly rejected, while `03001234567`, `0333-1234567`, `+92 300 1234567`, and `00923001234567` normalized to the same canonical form as intended.

### 4. Employee safeguards that passed

With extracted name and phone supplied to the handler, a complete request produced an explicit name, number and shop confirmation with no immediate write. `nahi` cancelled without a commit callback. `haan` prepared the commit callback. Missing phone produced a request for both name and number; short numbers produced an invalid number reply. A staff member was blocked from adding an employee.

The request `employee add karo Ali and number` receives a generic request for name and number rather than a question solely for the missing phone. The handler does not keep a pending employee detail action here. A later bare number is therefore dependent on conversational AI inference; that continuation remains unverified.

## User phrasing coverage

The full result file includes 45 language cases: greetings, `kya/kiya/kia` and `kr/karrhe/kaarhe` variants, `aap/tum/tm/tou`, politeness and rude prefixes, employee additions in both word orders, cash, credit, stock, balances, and language requests. These are samples of writing styles, not a proof of coverage for all Roman Urdu accents or spellings. The important next step is a live intent and field extraction evaluation on a broader labelled corpus, followed by multi-turn WhatsApp tests using an isolated test shop.

## Recommended fixes and acceptance gates

1. Add the failed confirmation variants to the local answer parser and rerun the audit. Avoid treating a standalone `na` or `ha` as a response if context makes it ambiguous.
2. Validate employee numbers against the product's actual supported countries and reject implausible or placeholder strings before confirmation.
3. Expand language detection for `assalam o alaikum`, `me`, `kro`, and Roman Urdu mixed with English actions. Keep a conversation language preference when text is too short to identify reliably.
4. Persist a pending question for missing employee details so a follow-up like `03331234567` completes the named employee safely.
5. Run the live classifier against a labelled Roman Urdu suite when external AI calls are approved. Measure intent, language, extracted fields, and pending answer behavior separately. Exercise actual replies and database effects in an isolated test shop, including duplicate employees, wrong-owner attempts, cancellations, and ambiguous names.

Pass target before claiming broad Roman Urdu readiness: all deterministic safety checks pass; live classification and field extraction are measured on the expanded corpus; every money or account mutation requires the correct entity and amount and has a verified cancel path.
