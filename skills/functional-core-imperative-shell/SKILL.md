---
name: functional-core-imperative-shell
description: Use when refactoring TypeScript code that mixes business decisions with I/O, state, time, or randomness into a pure functional core plus a thin imperative shell. Trigger on requests like "this is hard to test without mocks", "extract the pure logic", "separate business rules from the database", or "split decisions from side effects". Provides identification heuristics, a step-by-step procedure, before/after TypeScript examples, and anti-patterns.
---

# Functional Core, Imperative Shell

A refactoring skill for separating pure business decisions (the **functional
core**) from side-effecting orchestration (the **imperative shell**). The core
is referentially transparent — given the same inputs, it always returns the
same outputs and performs no I/O. The shell reads inputs, calls the core, and
applies the resulting effects.

## When to use

Apply this refactor when any of these smells appear:

- A function performs a database/network/file call **and** branches on
  business rules in the same body.
- Tests for a function require mocking a database, clock, RNG, or HTTP client
  just to exercise pure logic.
- Adding a new business rule requires touching code that also handles I/O.
- The same business rule is duplicated across handlers because each one
  re-implements it next to its own I/O.
- A function reads `Date.now()`, `Math.random()`, `process.env`, or a
  module-level singleton mid-computation.

## When NOT to use

- Trivial CRUD passthroughs with no real decisions (`getUser(id)` that just
  returns a row). Splitting these adds noise without test value.
- Code where the I/O sequence itself **is** the logic (e.g., a transactional
  saga). Express the saga's decisions as data, but don't pretend it's pure.
- One-shot scripts that will not be tested or reused.

## Core idea

Think of every function as: `(inputs, world) -> (outputs, effects)`.

- **Pure core**: a function from data to data (and optionally to a description
  of effects). No `await`, no `db.`, no `fetch`, no `Date.now()`, no logging.
- **Imperative shell**: reads from the world, calls the core, applies the
  resulting effects. Contains no branching on business rules. (See
  "Legitimate branching in the shell" below for what the shell *may*
  branch on.)

The shell becomes boring (and small). The core becomes trivially testable
(and grows as new rules arrive).

## Refactoring procedure

1. **Find the I/O boundary.** Mark every line that touches the outside world
   (DB, network, filesystem, clock, RNG, env, mutable globals).
2. **Hoist reads to the top.** Move all reads to the start of the function so
   the body operates on plain data.
3. **Defer writes.** Replace each write with a value the function will
   *return* describing what should happen. Either return a discriminated
   union of `Effect` values, or return new state plus a list of effects.
4. **Extract the pure decision.** Pull the now-pure middle into a separate
   function with an explicit signature. This is the core.
5. **Rewrite the original as a shell.** It reads, calls the core, and applies
   the returned effects.
6. **Move tests.** Delete mock-heavy tests of the old function. Write
   input/output tests against the core. Keep one or two integration tests for
   the shell to ensure the wiring works.
7. **Inject anything still impure.** If the shell is awkward to test, accept
   collaborators (db, clock, mailer) as parameters rather than importing them
   directly.

## TypeScript example 1: order processing

```typescript
// BEFORE: decisions and I/O entangled — needs db + emailService mocks to test
async function processOrder(orderId: string) {
  const order = await db.getOrder(orderId);
  if (order.total > 1000 && order.country !== "US") {
    await emailService.send(order.email, "Large international order alert");
  } else if (order.total > 1000) {
    await emailService.send(order.email, "Large order alert");
  }
  await db.updateStatus(orderId, "processed");
}
```

The decision ("which alert, if any?") is mixed with two I/O calls. Every
test needs a fake `db` and a fake `emailService` even though the logic is
pure arithmetic and string selection.

```typescript
// AFTER

// functional core: data in, data out, no I/O
type Alert =
  | { kind: "none" }
  | { kind: "large"; email: string }
  | { kind: "large-international"; email: string };

function decideAlert(order: { total: number; country: string; email: string }): Alert {
  if (order.total <= 1000) return { kind: "none" };
  if (order.country !== "US") return { kind: "large-international", email: order.email };
  return { kind: "large", email: order.email };
}

// imperative shell: reads, calls core, applies effects
async function processOrder(orderId: string) {
  const order = await db.getOrder(orderId);
  const alert = decideAlert(order);
  if (alert.kind === "large") {
    await emailService.send(alert.email, "Large order alert");
  } else if (alert.kind === "large-international") {
    await emailService.send(alert.email, "Large international order alert");
  }
  await db.updateStatus(orderId, "processed");
}
```

Tests for `decideAlert` are pure functions of plain objects. The shell gets
one happy-path integration test that exercises the wiring.

## TypeScript example 2: rate limiter with time and randomness

```typescript
// BEFORE: time + randomness baked in; tests must monkey-patch globals
class RateLimiter {
  private hits = new Map<string, number[]>();

  allow(userId: string): boolean {
    const now = Date.now();
    const window = this.hits.get(userId)?.filter((t) => now - t < 60_000) ?? [];
    if (window.length >= 10) {
      console.warn(`rate limit hit for ${userId}`);
      return false;
    }
    // jitter so concurrent clients don't synchronize
    if (Math.random() < 0.01) console.info(`sampling ${userId}`);
    window.push(now);
    this.hits.set(userId, window);
    return true;
  }
}
```

```typescript
// AFTER

type LimiterState = ReadonlyMap<string, readonly number[]>;
type LimiterDecision =
  | { kind: "allow"; nextState: LimiterState }
  | { kind: "deny" };

// functional core: state + inputs -> decision + next state
function decideLimit(
  state: LimiterState,
  userId: string,
  now: number,
  windowMs: number,
  maxHits: number,
): LimiterDecision {
  const recent = (state.get(userId) ?? []).filter((t) => now - t < windowMs);
  if (recent.length >= maxHits) return { kind: "deny" };
  const next = new Map(state);
  next.set(userId, [...recent, now]);
  return { kind: "allow", nextState: next };
}

// imperative shell: owns the mutable map, the clock, and the logger
class RateLimiter {
  private state: LimiterState = new Map();
  constructor(
    private readonly clock: () => number = Date.now,
    private readonly log: (msg: string) => void = console.warn,
  ) {}

  allow(userId: string): boolean {
    const result = decideLimit(this.state, userId, this.clock(), 60_000, 10);
    if (result.kind === "deny") {
      this.log(`rate limit hit for ${userId}`);
      return false;
    }
    this.state = result.nextState;
    return true;
  }
}
```

Note that randomness — sampling logs — was dropped. It was decoration, not
business logic. If sampling matters, the shell can do it after the core
decides; the core stays pure.

## Legitimate branching in the shell

"No branching on business rules" does not mean the shell is straight-line
code. The shell legitimately branches on three things, none of which are
domain decisions:

1. **Effect-kind dispatch** — the core returned a discriminated union of
   effects; the shell knows how to physically perform each kind.
2. **Error-class dispatch** — "is this retryable?" is a transport concern,
   not a domain decision (`AuthError` vs `RateLimitError` vs
   `TransientNetworkError`).
3. **Transport hints** — backoff math, `Retry-After` headers, connection
   state. Mechanical, driven by what the network told us.

```typescript
// functional core: decides WHAT to send (business rules live here)
type Notification =
  | { kind: "none" }
  | { kind: "email"; to: string; subject: string; body: string }
  | { kind: "sms"; to: string; body: string };

function decideNotification(
  user: { prefersChannel: "email" | "sms" | "off"; email?: string; phone?: string },
  event: { kind: "order-shipped" | "password-reset"; orderId?: string },
): Notification {
  if (user.prefersChannel === "off") return { kind: "none" };
  const body = event.kind === "order-shipped"
    ? `Your order ${event.orderId} has shipped.`
    : "A password reset was requested.";
  if (user.prefersChannel === "email" && user.email)
    return { kind: "email", to: user.email, subject: "Update", body };
  if (user.prefersChannel === "sms" && user.phone)
    return { kind: "sms", to: user.phone, body };
  return { kind: "none" };
}

type Deps = {
  loadUser: (id: string) => Promise<{ prefersChannel: "email" | "sms" | "off"; email?: string; phone?: string }>;
  email: { send: (to: string, subject: string, body: string) => Promise<void> };
  sms: { send: (to: string, body: string) => Promise<void> };
  sleep: (ms: number) => Promise<void>;
};

// imperative shell: three legitimate branches, zero business rules
async function notify(
  userId: string,
  event: { kind: "order-shipped" | "password-reset"; orderId?: string },
  deps: Deps,
) {
  const user = await deps.loadUser(userId);
  const n = decideNotification(user, event);

  // (1) Effect-kind dispatch — the core already chose; the shell just performs.
  switch (n.kind) {
    case "none":  return;
    case "email": return sendWithRetry(() => deps.email.send(n.to, n.subject, n.body), deps.sleep);
    case "sms":   return sendWithRetry(() => deps.sms.send(n.to, n.body), deps.sleep);
  }
}

async function sendWithRetry(send: () => Promise<void>, sleep: (ms: number) => Promise<void>) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try { await send(); return; }
    catch (err) {
      // (2) Error-class dispatch — "should this be retried?" is a transport concern.
      if (err instanceof AuthError) throw err;
      if (err instanceof RateLimitError) {
        // (3) Transport hint — backoff driven by what the network told us.
        await sleep(err.retryAfterMs ?? 1000);
        continue;
      }
      if (err instanceof TransientNetworkError) {
        await sleep(2 ** attempt * 100);
        continue;
      }
      throw err;
    }
  }
  throw new Error("send failed after 3 attempts");
}
```

A business-rule branch — the kind that *belongs in the core* — would look
like `if (user.prefersChannel === "email")` or
`if (event.kind === "password-reset")`. Both appear only inside
`decideNotification`.

## Anti-patterns to avoid

- **Pseudo-pure core.** A "pure" function that takes a `db` parameter and
  awaits it is still a shell. The core must not depend on collaborators that
  perform I/O.
- **Effects as callbacks passed in.** Passing `onAlert: () => Promise<void>`
  into the core moves the boundary back inside. Return effect descriptions
  instead; let the shell perform them.
- **Hidden time and randomness.** Reading `Date.now()` or `Math.random()`
  inside what you call the core defeats the point. Pass them in as values.
- **Splitting one function into two co-located halves.** If the "core" is
  only ever called by one shell and tested through it, you have not gained
  testability — you have only added a function. Split when the core has
  meaningful behavior worth testing in isolation.
- **Over-decomposition.** Not every line of a handler needs to become a pure
  helper. Aim for a core that captures the *decisions*, not every expression.

## Validation checklist

After refactoring, verify:

- [ ] The pure core has no `await`, `db.`, `fetch(`, `Date.now()`,
      `Math.random()`, `process.env`, `console.`, or imports of I/O modules.
- [ ] Tests for the core run in milliseconds and use no test doubles.
- [ ] The shell is short enough to read in one screen and contains only
      orchestration, not branching on business rules. Any branches in the
      shell fall into effect-kind dispatch, error-class dispatch, or
      transport hints.
- [ ] Removing the shell does not change the core's tests.
- [ ] At least one integration test exercises the shell end-to-end.

## Running the skill's own tests

This skill ships with pytest tests that validate its structure (frontmatter,
required sections, and BEFORE/AFTER example pairing):

```bash
pytest skills/functional-core-imperative-shell/tests
```
