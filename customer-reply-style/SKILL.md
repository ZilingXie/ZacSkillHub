---
name: customer-reply-style
description: Use when drafting, shortening, translating, or polishing technical replies for customers or internal colleagues, including when the user provides an edited draft or a Codex thread as feedback.
---

# Customer Reply Style

Use this skill for customer-facing or internal-colleague replies, not for a full internal investigation report. The goal is an accurate, audience-appropriate reply that is limited to the current case's questions and evidence.

## Select the audience mode

- **Customer mode:** Follow the host application's language contract for the customer-facing reply. The host may provide a target language, a customer-language reference, or a post-approval translation step; use that contract instead of imposing a Chinese or English default. Do not infer the customer-facing language from an internal engineer's language, and do not perform a second translation when the host owns delivery translation. Use plain language, lead with the practical conclusion, keep the reply short, and remove internal-only investigation detail, raw query output, and unrelated hypotheses. Keep product names, API names, log fields, code literals, and required official links in their original form when translating the surrounding explanation.
- **Internal-colleague mode:** Keep the evidence chain and relevant technical terms when they help a colleague make a decision. Still separate confirmed facts, likely explanations, unknowns, and next actions; do not turn an internal message into an unstructured investigation dump.
- If the audience is not explicit and cannot be inferred from the thread, ask before drafting. Do not combine customer-safe wording and internal-only details in one unlabeled reply.

## Choose the operation

- If the user provides a draft and asks to polish, edit for clarity, grammar, flow, and tone. Preserve the user's technical conclusion, scope, length preference, and requested omissions. Do not restart the investigation or add a new diagnosis.
- If the user asks how to reply or asks for a complete reply, first map the recipient's actual questions, then draft an audience-ready answer.
- If the user asks for a complete or full reply after several revisions, regenerate one integrated reply from the current confirmed facts. Do not return only a patch, replacement paragraph, or list of incremental changes.
- In customer mode, when the user points out a local change or asks to revise one part, regenerate and return the complete revised reply by default so the user can send it directly. Return only the changed fragment when the user explicitly asks for a fragment, a single paragraph, or "只改这一段".
- If the user gives an original draft and a manually revised final version and asks the skill to learn from it, compare the two and extract reusable preferences. Separate stable rules from case-specific edits. Do not silently change this skill; propose a rule update and wait for an explicit request to write it.

## Evidence boundary

Before writing, classify each material claim as confirmed, likely, or unknown.

- State confirmed observations as facts.
- Use calibrated language such as "目前更可能", "符合...特征", and "现有数据无法确认" for hypotheses and limitations.
- Do not turn a correlation, a missing metric, a log ordering, or a customer's hypothesis into a proven root cause.
- Do not say that a customer action was manual merely because an API call appears in logs. Distinguish the observed call from who or what triggered it.
- If the available evidence does not answer a customer question, say so directly and provide the next useful log, test, or comparison.

## Product facts and documentation

- When the reply contains a product capability, API calling constraint, metric definition, pricing, billing, plan, or support-status claim, verify it against the current authoritative documentation or the evidence supplied in the case when verification is in scope.
- For customer replies, prefer conclusions and explanations grounded in checked official documentation. When an official page supports a material product, API, metric, network, or configuration statement, include that page's link in the reply so the customer can verify the information. Keep the link close to the statement it supports rather than adding an unanchored link list.
- Separate three levels explicitly: what the documentation states, what is a reasonable implementation recommendation derived from it, and what is still unverified. Do not present an inferred call sequence as a verbatim documentation requirement.
- Do not infer that a mode is free, that two modes are billed independently, or that a particular price applies from a table, label, or general description unless the authoritative source actually says so. For contract-specific pricing or entitlement, defer to the contract or the appropriate commercial owner.
- If the user asks where a statement comes from, re-open the cited source and either quote or accurately paraphrase the relevant support. If the source does not support the statement, correct the wording and say the stronger claim was an inference.
- When a relevant official page cannot be found or checked, do not fabricate a URL or imply that the documentation confirms the claim; state the verification limit and keep the wording bounded.

## Customer-visible writing rules

1. Put the audience-relevant conclusion first. For a network/audio case, answer the practical concern before explaining the mechanism.
2. Answer the questions the recipient actually asked. In customer mode, do not import unrelated internal investigation threads, suspected VPN use, raw event codes, node names, query details, or lengthy timelines unless they are necessary to answer the question or the customer explicitly asked for them.
3. Keep internal and customer versions separate. Translate internal evidence into plain language for customers; retain only decision-relevant technical detail for colleagues.
4. Prefer a short opening paragraph followed by a small number of bullets or numbered answers. Remove repeated conclusions and implementation-level detail that does not change the customer's next action.
5. Give concrete next steps. A useful recommendation should say what to test, under what comparison condition, and what result would support the hypothesis.
6. Preserve customer-facing terminology and links supplied by the user. Do not invent product behavior, API support, allowlists, ports, timelines, or promised fixes.
7. Do not overstate exclusions. Prefer "目前不支持...是主要原因" or "现有数据更支持..." when the evidence is not conclusive.
8. When the user has already selected a concise direction, follow it. Do not make the reply longer merely because more internal evidence exists.
9. For a multi-case investigation, use a compact and repeatable structure for each case: decisive observations, a bounded judgment, and the relevant recommendation. Give one short overall conclusion afterward instead of repeating the same conclusion in every section.
10. When the evidence shows that a session successfully subscribed, received a first frame, or decoded/rendered media before a later freeze, reconnect, or leave, distinguish those phases explicitly. Do not describe the case as "never received video" or as a persistent failure.
11. Translate investigation limitations into the least burdensome customer-facing request. Do not expose internal account-mapping failures, sampled-user details, query limitations, raw event codes, or tool workflow unless they are necessary to answer the customer. Prefer asking for the user's observable symptom and occurrence time, with concrete examples such as black screen, no first frame, playback freeze, automatic exit, or audio without video.
12. Keep known exceptions visible while keeping the conclusion scoped: a short freeze or reconnect should remain acknowledged even when the evidence does not support a continuous stream failure or a common SDK/service defect.

## Customer information requests

When the reply asks a customer to provide or confirm information:

- Start with a compact list of information already recorded, then ask only for fields that are missing or genuinely need confirmation. Do not make the customer repeat confirmed values, known negative answers, or two labels that have already been established as the same field.
- Normalize equivalent customer and product terms to one clear label. If the user confirms that one supplied identifier is the requested identifier, record it under the useful label and remove the redundant question.
- For event planning, capacity estimation, and resource preparation, ask for expected values, approximate ranges, or rough proportions unless an exact value is operationally required. Avoid wording that implies the customer must already know precise future figures.
- Explain the request through the customer-visible outcome, such as preparing appropriate resources or helping the event run smoothly. Avoid leading with internal workflow names, reporting terminology, or operational bureaucracy unless the customer needs that context.
- If the user has reduced the question list or supplied a near-final draft, preserve that scope during polishing. Improve clarity and confirmation wording without restoring fields the user deliberately removed.

## Technical support patterns learned from the example

These are writing and scope preferences, not substitutes for current product verification:

- For a customer reply about successful join followed by missing two-way media, lead with the distinction between signaling/join success and an unstable media path. Keep the likely network direction concise unless the customer asks for the full evidence chain.
- If the customer asks about a metric that sounds like system volume, answer the metric's actual meaning and explicitly state whether it is or is not the device volume. Do not infer received media from that metric alone.
- For Native SDK direct-connection network restrictions, do not casually promise a fixed firewall IP/port allowlist. If the current evidence and product documentation support it, describe Cloud Proxy as a controlled comparison or mitigation path; verify current details before stating ports or addresses.
- A same-device Wi-Fi versus cellular/hotspot A/B test is a preferred next step when the suspected difference is the access network. Explain what a recovery on cellular would and would not establish.
- If the customer did not ask about VPN, do not introduce VPN as the headline explanation. Mention device-side filtering, MDM, Network Extension, or VPN only when the customer asked, the evidence is central, or the next test specifically requires checking it.
- When explaining transport choices, state the general principle and the case-specific reason separately so the recommendation is not internally contradictory: UDP is generally preferable for real-time media when the network allows it; TCP may be a useful diagnostic or mitigation path when the current network may restrict UDP or the direct media path. Do not describe TCP as inherently more secure.
- When a test changes the result, phrase the conclusion proportionally: recovery on mobile data supports a problem in the original Wi-Fi path, but does not by itself prove every other possible cause is excluded.

## Final self-check

Before returning a customer-ready reply, silently check:

- Does the first paragraph answer the customer's practical question?
- Does the customer reply follow the host application's target-language and delivery contract, while required product/API names and links remain accurate?
- Did I preserve the user's requested conclusion and level of detail?
- Did I answer every requested item, or clearly mark what is unknown?
- Did I separate evidence from inference?
- Did I remove internal-only details and unrelated hypotheses?
- Are the recommended tests actionable and consistent with the stated product constraints?
- Are there unsupported promises, fixed network details, or claims stronger than the evidence?
- If this is a customer reply, did I return the complete revised text after a local edit request unless a fragment was explicitly requested?
- Did I include checked official documentation links for material product claims where such sources exist, and avoid fabricated or unchecked links?
- If I am requesting information, did I separate recorded facts from missing items, avoid duplicate questions, and ask for only the precision actually needed?
- Did I frame the request around the customer's outcome rather than an internal process?

Return only the polished reply unless the user asks for the reasoning, change log, or feedback analysis.

For the feedback-extraction workflow, read [references/feedback-loop.md](references/feedback-loop.md).
