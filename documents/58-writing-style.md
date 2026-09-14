# Writing style for published work

Applies to every document intended for an outside reader: the paper draft (doc 56), the replication guide (doc 55), dataset cards, and any post. Internal notes and ADRs keep the existing house style.

## Voice

- No first person. Never "we", "our", "I". State what the method does and what the data shows. "The gate runs the official verifier twice" rather than "we ran the verifier twice".
- Active voice. "Stage one removed 5,316 candidates", not "5,316 candidates were removed".
- Technical, but pitched at the level of a reader who has not seen the repository. Define a term once, then use it.
- Short sentences. One claim each. No em-dashes, no semicolons joining clauses.

## Structure of a claim

Every result states, in this order: what was measured, what the number is, and what follows from it. The method belongs after the result, not before it.

## Defensibility

Defensibility comes from the strength of the experiment and the clarity of the statement, not from hedging. Do not pre-empt objections in the prose. Do not stack qualifiers on a result that the limits section already bounds.

Write the number, its interval, and its population. Put every limitation in one honest limits section and leave it there. A reader who checks the limits section should find nothing that contradicts the results section, and the results section should read as if it has nothing to hide, because it does not.

Two failure modes to avoid:

| Failure | Example | Fix |
| --- | --- | --- |
| Defensive hedging | "While this may be considered preliminary, it could arguably suggest..." | State the number and its interval. Move the caveat to limits. |
| Unbounded claim | "Generated tasks are higher quality." | Name the defect class and the populations measured. |

## Numbers

Every number carries its population, its sample size, and its interval where one exists. A point estimate without a denominator does not appear in published text. Bounds state which scheduling and which protocol produced them.

## The thesis line

One sentence, used as the abstract's first line and as the standalone summary:

> Brokenness is a solved, cheap, bounded problem, and quality is not, because quality does not transfer between populations and therefore has to be measured inside each one.
