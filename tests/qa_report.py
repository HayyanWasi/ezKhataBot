import json, re
from collections import Counter
rows=json.load(open("qa_final.json",encoding="utf-8"))
sc=[r for r in rows if r["final"] in("PASS","PARTIAL","FAIL")]
def sel(pred): 
    x=[r for r in sc if pred(r)]; c=Counter(r["final"] for r in x)
    return len(x), c["PASS"], c["PARTIAL"], c["FAIL"]
def ids(*pats): 
    rx=re.compile("|".join(pats)); return lambda r: bool(rx.match(r["id"]))
S={
 "Compressed Roman Urdu (intent must be inferred from few words)": ids(r"CMP-",r"RPT-(01|02|14|15|16)$",r"SOC-(07|08|09|11)$",r"EMP-(05|08|09)$",r"PTY-(03|11|19)$",r"CTX-(10|13)$"),
 "Casual report / memory phrases": ids(r"RPT-",r"COR-(07|08|09|10|11)$",r"ENG-03$",r"BIL-(08|09|10|12|18)$",r"EMP-(20|21|22|23)$",r"PTY-(12|13|14|15|16|17|18)$"),
 "Multi-action messages": ids(r"MUL-",r"EMP-(18|19)$",r"PTY-20$",r"CSH-(12|13)$",r"RPT-17$",r"BIL-03$",r"VAR-17$"),
 "Missing-detail follow-ups": ids(r"EMP-(12|13|14|15|16|17|28)$",r"CSH-(08|09|09b|10)$",r"CTX-(1\d|2\d|3[01])$",r"CAN-0[123]$",r"AMB-0[2-7]$"),
 "Context retention / pronouns / references": ids(r"CTX-",r"CAN-",r"EMP-(13|16|17|26)$",r"COR-0[3-6]",r"CMP-0[5-6]$",r"DUP-12$"),
 "Roman Urdu number words": lambda r: r["id"] in("PTY-04","PTY-05","PTY-06","CSH-05","BIL-21","VAR-33","VAR-34"),
 "Ambiguous / unsafe-if-guessed financial commands": ids(r"AMB-",r"COR-0[3-6]",r"VAR-(01|05|08|09|11|12|13|18|19|20|21|22|23|24|25|27|40)$",r"CMP-(11|12|03|04|06)$",r"ACC-",r"ENG-02$",r"CTX-(27)$"),
 "Spelling / orthography variants": lambda r: r["sgroup"].startswith("Misspelled") or r["id"] in ("SOC-02","SOC-06","VAR-06","VAR-07"),
}
out=[]
for k,p in S.items():
    n,a,b,c=sel(p); out.append((k,n,a,b,c))
    print(f"{k:70} n={n:3} pass={a:3} partial={b:2} fail={c:2} pass%={round(100*a/n)}")
# appendix
fixes={"NLU":"Add the labelled phrasing to classifier examples / regression set; add a deterministic phrase rule for high-frequency wording.",
"Entity":"Parse Roman Urdu number words and relative dates in code; validate every number/date in the message is accounted for before saving.",
"Context":"Store partially collected fields in the pending state and merge the next answer; re-ask instead of dropping an unanswered question.",
"Logic":"Detect multi-clause messages; run every clause or ask; never reply as if a part did not exist; echo what was done for each part.",
"Safety":"Ask for the missing direction/source/amount (or show a yes/no card) before saving; add big-amount and duplicate guards.",
"Setup-UX":"", "Backend":"Show 'service busy, retry' instead of 'samajh nahi aaya'."}
def exp(r):
    e=r["exp"]; parts=[]
    if e.get("i"): parts.append("intent in "+"/".join(e["i"]))
    if e.get("w")=="none": parts.append("no record written")
    if e.get("w")=="some": parts.append("record saved")
    if e.get("p") is True: parts.append("ask follow-up")
    if e.get("rx"): parts.append("reply mentions /%s/"%e["rx"])
    return "; ".join(parts) or "sensible, safe reply"
def clip(s,n=140): return (s or "").replace("\n"," / ").replace("|","\|")[:n]
L=["# Appendix – every executed live test case\n",
"Columns: ID | Feature | Style | User message | Expected | Actual intent | Actual bot reply (clipped) | Context kept | Clarification needed / asked | Unsafe assumption | Result | Severity | Type | Explanation | Suggested fix\n",
"| ID | Feature | Style | User message | Expected | Actual intent | Actual reply | Ctx ok | Clarif. needed→asked | Unsafe | Result | Sev | Type | Explanation | Suggested fix |","|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    if r["final"]=="VERIFY": continue
    e=r["exp"]; need = "yes" if (e.get("p") is True or e.get("w")=="none") else "-"
    asked = "yes" if r["pend_after"] else "no"
    unsafe = "YES" if r["ftype"]=="Safety" and r["final"]!="PASS" else "no"
    ctx = "no" if r["ftype"]=="Context" and r["final"]!="PASS" else ("n/a" if not (r["pend_before"] or r["id"].startswith(("CTX","CAN"))) else "yes")
    fix=fixes.get(r["ftype"],"") if r["final"] in("FAIL","PARTIAL") else ""
    L.append("| "+" | ".join([r["id"],r["feature"],r["style"],clip(r["text"],80),exp(r),str(r["intent"]),clip(r["reply"]),ctx,f"{need}→{asked}",unsafe,r["final"],r["severity"] if r["final"]!="PASS" else "-",r["ftype"] or "-",clip(r["note"],200),fix])+" |")
open("QA_ROMAN_URDU_APPENDIX_CASES.md","w",encoding="utf-8").write("\n".join(L))
print("appendix rows",len(L)-4)
# critical list
for r in rows:
    if r["severity"] in("Critical","High") and r["final"]!="PASS": print(r["severity"],r["id"],r["ftype"],"|",r["text"])
