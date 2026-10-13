# Feedback loop for edited replies

Use this reference when the user supplies both an earlier Codex draft and the version they manually edited, or when they say that a reply was only 70%-80% correct.

## What to compare

Compare the drafts along these dimensions:

1. Scope: what information was removed, added, or deliberately not answered.
2. Audience: whether the recipient is a customer or an internal colleague, and which internal terms were translated, softened, or omitted for that audience.
3. Certainty: where "is" became "more likely", "cannot confirm", or another evidence-bounded phrase.
4. Structure: whether the conclusion moved earlier, whether bullets became a shorter list, and whether repeated points were merged.
5. Action: whether the final version gave a concrete test or next step.
6. Product boundary: whether the user corrected a recommendation, API capability, network option, or support limitation.
7. Tone: greeting, directness, amount of apology, formality, and whether the reply sounds like a support engineer rather than an internal report.
8. Language: whether the reply followed the host application's target-language and delivery contract, including any customer-language reference or post-approval translation, while product/API names and links remained accurate.
9. Source discipline: whether a documentation link was requested, whether the cited page actually supports the statement, and whether an inference was incorrectly presented as a documented requirement.
10. Integration: whether the user wanted a complete regenerated reply after revisions instead of an incremental patch.
11. Delivery form: whether a local customer-reply edit still needed the complete sendable reply, or whether the user explicitly requested only a fragment.
12. Information collection: whether the reply separated already-recorded information from genuinely missing or unconfirmed fields, and avoided asking the customer to repeat known answers.
13. Precision: whether planning questions asked for an estimate, range, or rough proportion instead of unnecessary exact future values.
14. Framing: whether the reason for the request described the customer-visible outcome instead of an internal reporting or operational process.

## When the source is another Codex thread

When the user provides a `codex://threads/...` link:

1. Read the thread before proposing a rule change. Use the user's messages to identify the intended audience, the original request, and any manually edited wording.
2. Separate the user's draft and corrections from Codex's drafts, reasoning, tool output, and final polish. The user's explicit correction is stronger evidence than an assistant inference.
3. If the thread has multiple pages or older turns, continue reading until the relevant draft/revision sequence is complete. Do not infer a preference from the preview alone.
4. Keep customer data, IDs, URLs, logs, and other case-specific material out of the skill. Convert the observed difference into an abstract writing rule.

## Output format for feedback analysis

When asked to learn from a revision, produce:

```text
稳定偏好（可复用）
- ...

本案例特例（不要泛化）
- ...

需要确认的偏好
- ...

建议加入 skill 的规则
- ...
```

Only classify a preference as stable when the user states it explicitly or it is repeated across examples. A single changed sentence is evidence of a possible preference, not proof of a universal rule.

## How to update the skill

Do not write to the skill merely because a manual edit was observed. If the user explicitly asks to absorb the feedback, first show the proposed rule in the format above, then make the smallest targeted edit to `SKILL.md` or this reference. Avoid copying customer names, IDs, URLs, dates, raw logs, or other case data into the skill. Prefer an abstract rule and, when useful, a short redacted before/after pattern.

## Confirmed workflow preferences

The following are explicit default preferences for future drafting:

- For a customer reply, a request to change one sentence, bullet, or section still requires returning the complete revised reply. Output only a fragment when the user explicitly asks for one.
- Customer replies follow the host application's target-language and delivery contract. Do not add a Chinese or English default at the Skill layer; preserve product names, API names, code literals, and official links accurately while translating or rendering the surrounding explanation.
- Ground customer-facing product explanations in checked official documentation whenever practical, and include the relevant official documentation link next to the supported statement. If the source cannot be checked or does not support the claim, preserve the uncertainty instead of inventing a link or overstating the documentation.
- For multi-case investigation replies, organize each case as evidence, bounded conclusion, and focused recommendation, followed by one concise overall conclusion.
- Keep the distinction between successful initial media setup and a later interruption, freeze, reconnect, or leave. Do not collapse a later symptom into "never received video" or another persistent-failure claim.
- Keep internal investigation mechanics out of the customer version. When the remaining uncertainty is about what the end user experienced, ask for the observable symptom and occurrence time before requesting internal identifiers, raw logs, or investigation-specific details.
- Preserve scoped exceptions in the final wording: acknowledge a verified short-lived quality issue even when the evidence does not support a continuous failure or a general SDK/service defect.
- For customer information requests, show the information already recorded and ask only for missing or genuinely unconfirmed items. Normalize fields that the user has confirmed are equivalent, and do not ask for known negative answers again.
- For event planning, capacity estimates, and resource preparation, prefer expected values, approximate ranges, and rough proportions unless exact data is operationally necessary.
- Describe information collection in terms of the customer-visible outcome, such as preparing appropriate resources and supporting a smooth event, rather than leading with an internal reporting process.
- When the user supplies a narrowed near-final question list, polish within that scope and do not restore questions that the user deliberately removed.

## This example's initial lessons

The BCM thread suggests these candidate preferences for customer mode:

- The customer version should be shorter than the internal investigation and should lead with "not related to device volume; current evidence points to the student's network path" when that is the chosen conclusion.
- A final polish should preserve the user's chosen bullet structure and should not add a VPN narrative merely because the internal investigation considered it.
- The customer should receive a Wi-Fi-to-cellular comparison and SDK-log collection request, while raw VOS event cadence, node names, and internal query limitations belong in the internal report unless requested.
- A Native SDK direct connection should not be described as solvable by a fixed firewall allowlist; Cloud Proxy can be presented as the relevant controlled option when supported by the current product facts.
- General transport guidance and case-specific testing guidance should be written together without contradiction: explain why UDP is normally preferred, then why TCP is being tested in a network-restriction case.
- Product documentation claims need source-level verification. In particular, do not invent or overstate Cloud Proxy calling order, Automatic-mode pricing/free status, Force UDP/TCP billing separation, PCU semantics, or published prices.
- When a metric is central and the user requests a source, include the checked official metric documentation link.
- When the user asks for the complete reply after iterative changes, return a fresh integrated version with all confirmed revisions included.

These are seeded from one example. Promote them to stronger universal rules only after the user confirms them or they recur in later edited replies.
