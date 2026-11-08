# SafePause: research notes and sources (checked 6 Nov 2026)

Status labels: **PRIMARY** = read on the official page; **SECONDARY** = news or legal-firm summary of an official source; check the original before quoting it on stage.

## 1. Size of the problem
| Fact | Source | Status |
|---|---|---|
| NCRP frauds reported: 2.6 lakh (2021), 6.9 lakh (2022), 13.1 lakh (2023), 24 lakh (2024), 28 lakh (2025). Value: Rs 551 cr, 2,290 cr, 7,465 cr, 22,848 cr, 22,931 cr | RBI Discussion Paper "Exploring safeguards in digital payments to curb frauds", 9 Apr 2026 (rbi.org.in/Scripts/PublicationsView.aspx?id=23810) | PRIMARY (RBI page summary) |
| Payments above Rs 10,000 = ~45% of reported fraud cases by count but ~98.5% by value; ~92% of value is above Rs 50,000 | same RBI paper | PRIMARY |
| Account takeover is now "negligible"; most cases are Authorised Push Payment (APP) fraud, where the victim makes the payment | same RBI paper | PRIMARY |
| 2025: ~77% of losses from investment scams, ~8% from digital arrest | Fastbull/BrokersView citing I4C/NCRP | SECONDARY, single source |
| Digital arrest complaints: 1,23,672 (2024) to 58,239 (2025) to 16,377 (to 30 Jun 2026) | SC order 4 Aug 2026, via SCC Online blog 10 Aug 2026 | SECONDARY (law report) |

## 2. Regulation (why banks must act now)
| Fact | Source | Status |
|---|---|---|
| RBI options: (1) 1-hour lag on APP payments >= Rs 10,000 with cancel + whitelist; (2) trusted-person authentication for 70+ and PwD above Rs 50,000; (3) credit cap Rs 25 lakh/yr for low-turnover accounts; (4) customer kill switch. Comments closed 8 May 2026. Paper itself asks (Q4) whether the lag should instead be **optional, based on the bank's risk assessment** | RBI DP, 9 Apr 2026 | PRIMARY. Still a proposal; do not say "adopted" |
| RBI notes concerns: lag conflicts with "immediacy", confuses users, fraudsters may make victims whitelist; trusted person may be unavailable | RBI DP | PRIMARY |
| Supreme Court, In Re: Victims of Digital Arrest Related to Forged Documents, 2026 SCC OnLine SC 1532, order 4 Aug 2026: RBI to adopt SOP on temporary debit holds within 4 weeks; implement "delayed transaction safeguard / lagged credit mechanism"; committee to consider shared-liability and victim-compensation framework | SCC Online blog | SECONDARY (law report) |
| Revised RBI customer-protection directions on fraudulent electronic banking transactions, final 24 Jun 2026, apply from 1 Jan 2027 (commercial banks; separate versions for RRBs/co-op banks) | ELP law alert, TaxGuru, Fox Mandal | SECONDARY |
| RBI FREE-AI framework, 13 Aug 2025: 7 principles, 26 recommendations; human oversight for medium/high-risk AI; customers can escalate to a human | law-firm summaries | SECONDARY |
| DoT Financial Fraud Risk Indicator (FRI), May 2025: classifies mobile numbers Medium/High/Very High risk; RBI advisory 30 Jun 2025 asks banks, UPI apps to integrate | DoT Sanchar Saathi PDF, Business Standard | SECONDARY |

## 3. Real cases (for the case replay; "reconstructed from news reports")
1. **Jodhpur, Feb 2026 (ETV Bharat, 24 Feb 2026).** 75-year-old woman, 10-day digital arrest. Sent Rs 1.85 cr by RTGS (18 Feb). Broke FD, moved to savings 2 days before trying a Rs 22 lakh NEFT "for granddaughter's fees". PNB staff saw she was worried and refused to explain; police put Rs 33 lakh on hold, Rs 22 lakh saved.
2. **Hyderabad, Oct 2026 (The420.in).** 80-year-old retired bank manager + wife. Call 19 Oct, WhatsApp video call by fake inspector, threatened children's arrest. Six transfers, 23-27 Oct, > Rs 1.5 cr, to two accounts. No bank intervention. Son told on 28 Oct.
3. **Navi Mumbai, Nov 2024 (Free Press Journal, 29 Nov 2024).** 80-year-old; fake RBI caller + WhatsApp video "house arrest"; broke FDs, Rs 21.94 lakh already sent to various accounts. Unity Small Finance Bank manager stopped Rs 12 lakh: stated reason (medical) did not match payee ("Royal enterprises"); payee account had ~Rs 3 cr in 2 days, all withdrawn. Victim then sent ~Rs 6 lakh from other banks.
4. **Mulki/Kinnigoli, Karnataka (Deccan Herald).** Elderly couple moved Rs 84 lakh FD to savings to transfer; Canara Bank manager questioned them, police stopped it.
5. **Chennai, Jul 2024 (DT Next, 20 Jul 2024).** IT professional, WhatsApp group, fake trading app showing "exponential profit", Rs 1.7 cr to various accounts; found out when withdrawal blocked.

**Pattern across all five:** pressure + secrecy, FD broken or savings drained, new payees, several rising transfers over days, victim gives a false reason. In 3 of 5 the money was saved only because **a human noticed in person**. In mobile/net banking there is no such person.

## 4. Market (Slide 6)
- Urban co-operative banks: 1,457 (end-Mar 2025, RBI Co-operative Banks publication, 29 Dec 2025). PRIMARY-ish.
- Regional rural banks: 28; small finance banks: 11 (mid-2025, secondary lists).
- Existing tools: DoT FRI (number risk), RBIH MuleHunter.AI (mule accounts, receiving side), BioCatch / Feedzai / FICO Falcon (commercial fraud/behaviour platforms). SafePause works on the **sending side, at the moment of payment, for manipulated genuine customers**, and can use FRI as one input.

## 5. Not verified / do not put on slides as fact
- Rs 1.3 cr consumer-forum award against five banks (not re-checked).
- Exact share of losses by scam type (single secondary source; say "about three-quarters, per reported I4C data").
- Any pricing numbers (ours are proposals).

## 6. Round 2 research (6 Nov 2026): public statements and precedents (used in place of our own interviews until those are done)
These are PUBLISHED statements and reports, credited to their source. They are NOT our interviews.

| Item | Source | Use |
|---|---|---|
| CJI Surya Kant, hearing 9 Feb 2026: "why your AI operated tools in the bank did not deem it fit to alarm him, that this transaction is suspicious?"; also "banks must realise they are trustees of public money"; Justice Joymalya Bagchi: "banks are more into business mode" | LiveLaw, 9 Feb 2026 | Slide 2 hook |
| Agra, 8 Sep 2026: Canara Bank (Awas Vikas Colony) manager Ravi Kumar held an ~Rs 81 lakh RTGS of an 80-year-old who had closed FDs; he claimed "son's property purchase" but could not give payee or son's number; bank **contacted his daughter-in-law**, who revealed the fake-police calls; transfer stopped | Shunyatax blog (secondary, no original cited) | Validates trusted-contact step |
| Kinnigoli/Mulki, 1-5 Dec 2025: Canara Bank manager Royston stopped Rs 84 lakh FD transfer; couple said it was for **buying land in Bengaluru** (coached cover story); police: fraudsters "digitally arrested the elderly couple for many days" | ETV Bharat 5 Dec 2025; Deccan Herald | Victims lie -> asking the victim fails |
| UK Payment Services (Amendment) Regulations 2024 (in force Oct 2024): banks may delay an outbound payment up to **4 business days** only where there are reasonable grounds to suspect fraud (risk-based, not blanket) | FCA FG24/6; gov.uk policy note | Precedent for risk-based pause |
| Google Android in-call scam protection: warns when a financial app is opened while screen sharing on a call with a number not in contacts; 30-second wait; pilots UK, Brazil, **India** (Dec 2025) | Google blog, 3 Dec 2025 | Feasibility of the call signal |
| Singapore Protection from Scams Act 2025 (in force 1 Jul 2025): police restriction orders make banks block a scam victim's transfers, up to 30 days | MHA Singapore | Precedent: protecting a victim from their own payment |
| UPI users onboarded: 55.49 crore (June 2026, Lok Sabha reply); FY26 UPI value Rs 314 lakh crore | PIB / Lok Sabha | Market sizing |
| Rs 22,931 cr / 55.49 cr users = about Rs 413 lost per UPI user per year (our arithmetic, rough) | derived | Pricing logic |

**Correction, 8 Nov 2026:** the Agra case was rechecked at The420.in ("Bank Stops ₹81 Lakh Digital Arrest Transfer", updated 9 Sep 2026), which confirms the bank reached the daughter-in-law. The Hyderabad report does not say the transfers were made through an app. RBI's revised directions (from 1 Jan 2027) cover payments made under coercion and put the burden of proving negligence on the bank, per the ELP law note; check the RBI text before final use.
