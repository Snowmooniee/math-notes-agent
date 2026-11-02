# Topology review evaluation

The first review workflow targets point-set topology claims in text-based notes, with exact tools for finite spaces and maps. A review must identify the claim and its assumptions, distinguish source material from mathematical evidence, and report the calculation or reasoning behind its conclusion. General proof certification is outside this scope.

## Success criteria

Evaluate each applicable item separately. A relevant passage alone does not establish that a claim is correct.

| Item | Required evidence |
| --- | --- |
| Retrieval | The returned pages contain the reference information needed for the task. Record relevant pages that were missed. |
| Citation support | The cited passage supports the statement attributed to it, including its assumptions. |
| Mathematical judgment | The reported conclusion and identified problem agree with the reviewed reference answer. |
| Calculation | Tool inputs match the claim; the results and their interpretation are correct. |
| Uncertainty | The review identifies the specific missing information or unresolved step. It does not treat missing evidence as a counterexample. |
| Execution | Tool errors and unfinished runs are recorded, rather than reported as completed mathematical checks. |

A task succeeds when its required findings and applicable criteria pass. An unresolved answer does not pass a task whose answer is available. For an insufficient-information task, explaining what is missing can be the correct outcome.

Citation faithfulness and mathematical correctness are separate judgments: accurately quoting an erroneous note does not validate it. A trusted definition or theorem must have checked provenance and applicable assumptions; an exact calculation may provide an independent check for a supported class of claims.

## Task set to review and freeze

Start with a target of 10 development cases and 10 held-out cases. Reference answers need human review before these cases can support a quality claim. No reviewed task set or model accuracy result is available yet.

| Category | Example task | Required finding |
| --- | --- | --- |
| Correct claim | An identity map from a finer finite topology to a coarser one is continuous | Verify every codomain open-set preimage. |
| Missing assumption | A note claims every continuous bijection is a homeomorphism | Give a valid counterexample or applicable additional conditions, distinguishing sufficient from necessary conditions. |
| Invalid derivation | A proof uses openness of images to assert continuity | Identify the unsupported inference; continuity concerns open-set preimages. |
| Calculation error | An open set's preimage is computed incorrectly | Return the correct preimage and its membership in the domain topology. |
| Insufficient information | The codomain topology or necessary reference information is absent | State what is missing without assuming an unspecified topology. |
| Tool failure | A calculation tool returns an error | Preserve the error and distinguish an execution failure from a false mathematical claim. |

Keep numerical variants of the same task family in the same split. Freeze source versions, reference answers and the split before held-out evaluation. Development examples may guide changes; held-out answers must not guide prompt tuning. Keep operational fault-injection results separate from naturally occurring model failures.

## Comparisons and records

First compare the same model reviewing the same supplied claim and reference material with and without the calculation tool. Keep the prompt, model configuration and resource limits fixed apart from tool availability. Compare retrieval changes separately on fixed queries and reviewed relevant pages. Add embeddings or hybrid retrieval only in response to observed retrieval failures.

Record per case:

- case ID, split, task/source version, code revision, model and configuration;
- retrieved pages, citations and the separate judgments above;
- tool requests, actual results and errors, final output and reviewer notes;
- model requests and API attempts including retries, tool calls, elapsed time and token usage;
- price source/date and cost when available; unknown usage or prices remain unknown.

Report counts and denominators, individual failures and unchanged results. Invalid output and exhausted runs remain visible. A deterministic software test or scripted tool trace is integration evidence, not a model-quality measurement. Small task sets support observations about those tasks, not broad reliability claims.

## Current executable example

`examples/math-notes/continuity-claim.json` describes a two-point identity map from a discrete to an indiscrete space. `python -m scripts.demo_topology` checks that it is continuous and its inverse is not, with a concrete failed-open-set witness. Tool requests are scripted and the calculations are real. This is an integration example, not an evaluated model-driven note review.
