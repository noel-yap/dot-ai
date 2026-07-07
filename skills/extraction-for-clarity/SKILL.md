---
name: extraction-for-clarity
description: Use when refactoring TypeScript code that is hard to read because intent is buried - deeply nested conditionals, complex boolean expressions, magic numbers, long functions whose sections are labeled by comments, or mixed levels of abstraction in one body. Trigger on requests like "this function is unreadable", "flatten this nesting", "name this condition", "break this long function up", "what do these numbers mean", or "make this self-documenting". Provides identification heuristics, a step-by-step procedure, before/after TypeScript examples using extract function, guard clauses, explaining variables, and named constants, and anti-patterns.
---

# Extraction for Clarity

A refactoring skill for making code state its intent. The moves are small
and mechanical — extract function, extract explaining variable, guard
clause, named constant — but the motivation is specific: **readability,
not reuse**. A helper with a single caller is a success if it turns a
puzzle into a sentence. The refactor is strictly behavior-preserving:
same inputs, same outputs, same visible effects, same public signatures.

## When to use

Apply this refactor when any of these smells appear:

- A function's phases are labeled by comments (`// compute base`,
  `// apply adjustments`). Each such comment is a function name waiting
  to happen.
- A conditional needs decoding: `a && (b || c) && !(d && e)`, or a
  ternary nested inside a ternary.
- Control flow nests three or more levels deep, and the interesting work
  sits at the bottom of an `if`/`else` staircase.
- Unexplained literals steer the logic (`* 1.075`, `>= 45`, `"gold"`)
  and a reviewer has to ask what they mean.
- Reading the function means holding several intermediate values in your
  head at once, because low-level arithmetic and high-level policy share
  one body.
- Code review keeps producing questions like "what does this block do?"
  — the answer belongs in the code, not in the review thread.

## When NOT to use

- **Code that already reads top-to-bottom at one level of abstraction.**
  Extraction there adds indirection hops without removing any burden.
- **Fragments smaller than their name.** A one-line pass-through
  (`const name = user.name`) or a wrapper that only forwards its
  arguments makes the reader chase a reference to learn nothing.
- **When the real problem is I/O tangled with decisions.** Extracting
  prettier helpers inside a function that also reads the database treats
  the symptom; use [[functional-core-imperative-shell]] to separate the
  decision first, then extract for clarity inside the pure part.
- **Deduplication.** Merging two fragments because they look similar
  today is a different decision with different risks (see
  anti-patterns). This skill extracts to *name one concept*, even when
  nothing is duplicated.
- **Throwaway or generated code** nobody will read again.

## Core idea

Well-factored code reads like prose: the top-level function is a table
of contents, and each name is a claim about *what* is computed, leaving
*how* one level down. Every stumbling point in the reading — a comment
that labels a section, a boolean that needs decoding, a literal without
a unit — marks a concept the code uses but never names.

The moves, smallest first:

- **Named constant**: a literal becomes `UPPER_SNAKE_CASE` with the
  unit or meaning in the name (`SESSION_TTL_SECONDS`, not `86400`).
- **Explaining variable**: a sub-expression gets a name where it is
  computed (`const isRushOrder = ...`) so the branch below reads as a
  sentence.
- **Predicate function**: a reused or complex condition becomes
  `isX`/`hasX`/`canX`, testable and quotable.
- **Guard clause**: disqualifying cases exit early, un-nesting the main
  path.
- **Extract function**: a comment-labeled section becomes a function
  named for what it produces; the comment disappears because the name
  now says it.

None of these change behavior. If a change would alter an output, an
effect, or a caller-visible signature, it is not this refactor.

## Refactoring procedure

1. **Mark the stumbling points.** Read the function once and note every
   place you slowed down: section comments, dense booleans, bare
   literals, deep indents.
2. **Name the numbers.** Replace each meaningful literal with a
   `const UPPER_SNAKE_CASE` whose name carries the unit or policy
   (`FREE_TRIAL_PERIOD_DAYS`). Group them at the top of the
   module.
3. **Name the conditions.** Turn each dense boolean into a predicate
   function or an explaining variable named `is...`/`has...`/`can...`/
   `should...`. Prefer a function when the condition states a domain
   rule; a local variable when it is one-off glue.
4. **Flatten with guard clauses.** Handle rejections and edge cases
   first with early returns, so the happy path runs at indent level one.
   Apply the same discipline inside every helper you extract, not just
   the orchestrator: carrying a nested conditional staircase into a new
   function only relocates the nesting, it doesn't remove it. No
   function, top-level or extracted, should stay several branches deep.
5. **Extract the comment-labeled sections.** Each becomes a function
   named for its result (`baseFare`, `loyaltyDiscount`), taking only the
   values it actually reads. Delete the comment; the name replaces it.
6. **Re-read the orchestrator.** The original function should now read
   as a short sequence of named steps at a single level of abstraction.
   If a step name makes you ask "but how?", the how belongs inside it;
   if it makes you ask "why?", the name is wrong.
7. **Verify behavior is unchanged.** Run the tests (or write
   characterization tests first when there are none). Every move above
   is a pure rearrangement — any diff in outputs or effects means a step
   went wrong.

## TypeScript example 1: paycheck with comment-labeled sections

```typescript
// BEFORE: three phases labeled by comments, unexplained numbers, and a
// nested overtime staircase. Changing any one rule means re-reading all
// of them.
export interface Employee {
  hourlyRate: number;
  unionMember: boolean;
  retirementPct: number;
}

export function calculatePaycheck(
  employee: Employee,
  hoursWorked: number,
): number {
  // base and overtime pay
  let gross = 0;
  if (hoursWorked > 40) {
    if (hoursWorked > 60) {
      gross =
        40 * employee.hourlyRate +
        20 * employee.hourlyRate * 1.5 +
        (hoursWorked - 60) * employee.hourlyRate * 2;
    } else {
      gross =
        40 * employee.hourlyRate +
        (hoursWorked - 40) * employee.hourlyRate * 1.5;
    }
  } else {
    gross = hoursWorked * employee.hourlyRate;
  }

  // deductions
  let deductions = gross * 0.0765;
  if (employee.unionMember) {
    deductions += 19;
  }
  if (employee.retirementPct > 0) {
    deductions += gross * (employee.retirementPct / 100);
  }

  // net, rounded to cents
  return Math.round((gross - deductions) * 100) / 100;
}
```

The comments are doing the job of names. Extract one function per
labeled phase, and one named constant per bare number:

```typescript
// AFTER
export interface Employee {
  hourlyRate: number;
  unionMember: boolean;
  retirementPct: number;
}

const REGULAR_WEEK_HOURS = 40;
const DOUBLE_TIME_THRESHOLD_HOURS = 60;
const OVERTIME_MULTIPLIER = 1.5;
const DOUBLE_TIME_MULTIPLIER = 2;
const FICA_RATE = 0.0765;
const UNION_DUES_PER_PERIOD = 19;

function grossPay(hourlyRate: number, hoursWorked: number): number {
  const regularHours = Math.min(hoursWorked, REGULAR_WEEK_HOURS);
  const overtimeHours = Math.min(
    Math.max(hoursWorked - REGULAR_WEEK_HOURS, 0),
    DOUBLE_TIME_THRESHOLD_HOURS - REGULAR_WEEK_HOURS,
  );
  const doubleTimeHours = Math.max(
    hoursWorked - DOUBLE_TIME_THRESHOLD_HOURS,
    0,
  );
  return (
    (regularHours +
      overtimeHours * OVERTIME_MULTIPLIER +
      doubleTimeHours * DOUBLE_TIME_MULTIPLIER) *
    hourlyRate
  );
}

function totalDeductions(employee: Employee, gross: number): number {
  const fica = gross * FICA_RATE;
  const unionDues = employee.unionMember ? UNION_DUES_PER_PERIOD : 0;
  const retirement = gross * (employee.retirementPct / 100);
  return fica + unionDues + retirement;
}

function roundToCents(amount: number): number {
  return Math.round(amount * 100) / 100;
}

export function calculatePaycheck(
  employee: Employee,
  hoursWorked: number,
): number {
  const gross = grossPay(employee.hourlyRate, hoursWorked);
  return roundToCents(gross - totalDeductions(employee, gross));
}
```

`calculatePaycheck` is now the table of contents. Each helper has a
single caller — and that is fine: the extraction bought a name, not
reuse. The overtime staircase became three named quantities added
together, and every policy number can be found (and changed) by its
name.

## TypeScript example 2: refund eligibility conditional

```typescript
// BEFORE: one boolean expression encodes five rules; the nested ternary
// hides which rule granted or denied the refund.
export interface Purchase {
  daysSince: number;
  kind: "digital" | "physical";
  opened: boolean;
  totalCents: number;
}

export interface Customer {
  standing: "good" | "flagged";
  refundsThisYear: number;
}

export function isRefundEligible(
  purchase: Purchase,
  customer: Customer,
): boolean {
  return (
    customer.standing !== "flagged" &&
    (purchase.kind === "digital"
      ? purchase.daysSince <= 14 && !purchase.opened
      : purchase.daysSince <= 30 &&
        (purchase.totalCents < 5000 || customer.refundsThisYear < 3))
  );
}
```

Name each rule as a predicate and let guard clauses state the policy in
reading order:

```typescript
// AFTER
export interface Purchase {
  daysSince: number;
  kind: "digital" | "physical";
  opened: boolean;
  totalCents: number;
}

export interface Customer {
  standing: "good" | "flagged";
  refundsThisYear: number;
}

const DIGITAL_RETURN_WINDOW_DAYS = 14;
const PHYSICAL_RETURN_WINDOW_DAYS = 30;
const NO_QUESTIONS_ASKED_LIMIT_CENTS = 5000;
const YEARLY_REFUND_ALLOWANCE = 3;

function isWithinReturnWindow(purchase: Purchase): boolean {
  const windowDays =
    purchase.kind === "digital"
      ? DIGITAL_RETURN_WINDOW_DAYS
      : PHYSICAL_RETURN_WINDOW_DAYS;
  return purchase.daysSince <= windowDays;
}

function isSmallPurchase(purchase: Purchase): boolean {
  return purchase.totalCents < NO_QUESTIONS_ASKED_LIMIT_CENTS;
}

function hasRefundAllowance(customer: Customer): boolean {
  return customer.refundsThisYear < YEARLY_REFUND_ALLOWANCE;
}

export function isRefundEligible(
  purchase: Purchase,
  customer: Customer,
): boolean {
  if (customer.standing === "flagged") return false;
  if (!isWithinReturnWindow(purchase)) return false;
  if (purchase.kind === "digital") return !purchase.opened;
  return isSmallPurchase(purchase) || hasRefundAllowance(customer);
}
```

The public function now reads as the policy: flagged customers never;
outside the window never; digital must be unopened; physical needs a
small total or remaining allowance. Each predicate is independently
testable and quotable in a review.

## How this relates to sibling skills

- **[[functional-core-imperative-shell]]** separates decisions from
  I/O. If the unreadable function also awaits a database or sends
  email, do that split first; extraction for clarity then applies
  inside the pure core.
- **[[dependency-injection]]** makes collaborators swappable. It
  changes signatures and wiring; this skill deliberately changes
  neither.

Extraction for clarity is the zero-risk member of the family: no
signature changes, no dependency changes, no behavior changes — only
names where there was noise.

## Anti-patterns to avoid

- **Vague names.** `processData`, `handleStuff`, `helper2`, `doCalc` —
  extraction without a meaningful name spends indirection and buys
  nothing. If you cannot name what the fragment computes, you have not
  understood it yet; understand first, extract second.
- **Shallow pass-throughs.** A helper that is shorter than its call
  site, or that only forwards arguments, makes readers chase a
  reference to learn nothing. Inline it back.
- **Parameter blizzard.** If the extracted fragment needs six values
  from the enclosing scope, the signature now carries the complexity
  the body used to. Either pass the one object those values live on, or
  reconsider the extraction boundary.
- **Hiding the important rule.** Burying the one branch reviewers must
  see inside a blandly-named helper *reduces* clarity. Extract the
  noise and leave the signal visible, not the other way around.
- **Premature deduplication.** Two fragments that look alike today may
  diverge tomorrow. Merging them couples their futures; that is a
  separate decision from naming. Extract each for what *it* means, and
  merge only when the domain says they are the same rule.
- **Over-fragmentation.** Twenty three-line functions read as a
  scavenger hunt. Extract the concepts a reader needs named, not every
  line; the orchestrator should shrink to a page, not explode into
  confetti.
- **Behavior drift.** "While I'm here" fixes — reordering side effects,
  tightening a comparison, correcting a perceived off-by-one — turn a
  safe rename into a risky change. Fix bugs in a separate change with
  its own tests.

## Validation checklist

After refactoring, verify:

- [ ] Behavior is unchanged: same outputs for the same inputs, same
      effects in the same order, no public signature changed.
- [ ] The orchestrating function reads as named steps at a single level
      of abstraction, with nesting at most two deep.
- [ ] No section comments remain; each became a function name.
- [ ] No unexplained literals remain in the logic; each meaningful
      number or string is a named constant with its unit or policy in
      the name (a magic number survives only where it is self-evident,
      like `* 100` next to `roundToCents`).
- [ ] Complex conditions read as sentences: guard clauses for exits,
      `is`/`has`/`can`/`should` predicates for rules.
- [ ] Every new helper name states *what* it computes; none are named
      like `helper`, `util`, `process`, or `data`.
- [ ] No new helper needs more than a handful of parameters; none is a
      one-line pass-through.

## Running the skill's own tests

This skill ships with pytest tests that validate its structure
(frontmatter, required sections, BEFORE/AFTER pairing, and that each
AFTER example actually extracts named helpers, names its constants, and
reduces nesting):

```bash
pytest skills/extraction-for-clarity/tests
```
