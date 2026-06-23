---
name: dependency-injection
description: Use when refactoring TypeScript code whose tests require monkey-patching modules, swapping globals, or stubbing imports because collaborators (database, HTTP client, clock, RNG, env, logger) are hardcoded inside the unit. Trigger on requests like "I can't test this without mocking the import", "this depends on a global singleton", "inject the clock/db", "pass the X in", or "decouple from the X module". Provides identification heuristics, a step-by-step procedure, before/after TypeScript examples using constructor and parameter injection, and anti-patterns.
---

# Dependency Injection

A refactoring skill for replacing hardcoded collaborators (module-level
imports, singletons, `Date.now()`, `Math.random()`, `process.env`,
`console.*`, `new Db()` inside a constructor) with **injected** ones. After
the refactor, the unit receives its collaborators by parameter; tests
construct it with lightweight stand-ins (fakes, stubs) instead of
monkey-patching module imports.

## When to use

Apply this refactor when any of these smells appear:

- Tests for a unit require `vi.mock("./db")` / `jest.mock("./email")` of
  module imports just to substitute a collaborator.
- The unit reaches a module-level singleton (`db`, `logger`, `cache`) by
  direct import and uses it mid-computation.
- The unit reads `Date.now()`, `Math.random()`, `process.env`, or calls
  `console.*` inside its body.
- A class news up its own collaborators (`new HttpClient()`, `new Db()`)
  inside the constructor or a method.
- Multiple tests redefine the same module mock — the seam that should be a
  parameter is missing.
- A feature flag or config knob requires editing every call site because
  the config is a globally-imported module.

## When NOT to use

- **Trivial passthroughs / pure functions.** Nothing to inject; adding
  `deps` is noise.
- **Hot inner loops** where the cost of a virtual dispatch / property
  read measurably matters. Rare, but real.
- **Already a pure functional core.** Prefer
  [[functional-core-imperative-shell]] to extract the decision, then DI
  the surrounding shell if needed.
- **Cases where the dependency is genuinely owned by the unit** (e.g., a
  private utility with no I/O and no time/random/env access). Injecting
  it leaks internals into the unit's signature.

## Core idea

A unit should **receive** its collaborators, not **create** or **find**
them. The unit names what it needs (`db`, `clock`, `mailer`) via parameter
types; a composition root wires concrete implementations at the edge of
the system.

This inverts control: instead of the unit knowing where to get `db`,
callers tell it. The seam that was previously "edit the module import" or
"monkey-patch this global" becomes a normal argument.

The unit also depends on a **narrow interface** — the minimum surface it
actually uses — not the concrete class. `Clock = () => number` is enough;
the unit does not need to know about `Date`.

## Refactoring procedure

1. **Identify the seams.** Mark every reference inside the unit to a
   module-level import, singleton, `Date.now()`, `Math.random()`,
   `process.env`, `console.*`, or `new X()` of an I/O-bearing class.
2. **Name each collaborator.** For each seam, give it a parameter name
   (`db`, `clock`, `rng`, `log`, `config`, `http`).
3. **Define a narrow interface per collaborator.** Type each by only the
   operations the unit actually uses. Avoid exposing the whole concrete
   API surface.
4. **Choose an injection style:**
   - **Constructor injection** (class): take collaborators once at
     construction. Default for stateful services.
   - **Parameter injection** (function): take a `deps` object as a final
     argument. Default for module-level functions.
   - **Method injection** (per call): the collaborator legitimately
     varies per call (rare).
5. **Wire production at the boundary.** A composition root (module
   bottom, `main`, route handler, factory) constructs the real
   collaborators and hands them to the unit. The unit itself imports no
   I/O modules.
6. **Rewrite tests to pass fakes.** Construct the unit with in-memory or
   canned doubles. Delete `vi.mock` / `jest.mock` of production modules.
7. **Make injected deps required.** Avoid `constructor(db = realDb)`
   defaults — they silently re-couple the unit to the production module
   when callers forget.

## TypeScript example 1: order shipper with constructor injection

```typescript
// BEFORE: hardcoded module imports + hidden clock; tests must vi.mock
// both `./db` and `./email` AND stub Date.now to exercise the unit.
import { db } from "./db";
import { emailService } from "./email";

export async function shipOrder(orderId: string): Promise<void> {
  const order = await db.getOrder(orderId);
  const shippedAt = Date.now();
  await emailService.send(
    order.email,
    "Shipped",
    `Order ${order.id} shipped at ${shippedAt}`,
  );
  await db.markShipped(orderId, shippedAt);
}
```

Three seams: `db`, `emailService`, `Date.now()`. None are named in the
signature, so every test reaches for module mocks.

```typescript
// AFTER

// Narrow interfaces — only the operations this unit actually uses.
export interface OrderStore {
  getOrder(id: string): Promise<{ id: string; email: string }>;
  markShipped(id: string, at: number): Promise<void>;
}
export interface Mailer {
  send(to: string, subject: string, body: string): Promise<void>;
}
export type Clock = () => number;

// SUT (under test): collaborators arrive by construction.
export class OrderShipper {
  constructor(
    private readonly store: OrderStore,
    private readonly mailer: Mailer,
    private readonly clock: Clock,
  ) {}

  async ship(orderId: string): Promise<void> {
    const order = await this.store.getOrder(orderId);
    const at = this.clock();
    await this.mailer.send(
      order.email,
      "Shipped",
      `Order ${order.id} shipped at ${at}`,
    );
    await this.store.markShipped(orderId, at);
  }
}
// end SUT (under test)

// Composition root: production wiring lives at the edge, not inside the
// unit. This is the only place that imports the I/O modules.
import { db } from "./db";
import { emailService } from "./email";
export const productionOrderShipper = new OrderShipper(
  db,
  emailService,
  Date.now,
);
```

Tests construct `OrderShipper` directly with fakes — no `vi.mock`, no
global stubs:

```typescript
const sent: Array<[string, string]> = [];
const shipper = new OrderShipper(
  {
    getOrder: async (id) => ({ id, email: "x@y.z" }),
    markShipped: async () => {},
  },
  { send: async (to, subject) => void sent.push([to, subject]) },
  () => 1_700_000_000_000,
);
await shipper.ship("o1");
// expect(sent).toEqual([["x@y.z", "Shipped"]]);
```

## TypeScript example 2: token issuer with parameter injection

```typescript
// BEFORE: hidden randomness, hidden env, hidden logger. To test, callers
// must monkey-patch Math.random, set process.env.JWT_SECRET, and
// silence/inspect console.log via global hooks.
import { sign } from "jsonwebtoken";

export function issueToken(userId: string): string {
  const nonce = Math.random().toString(36).slice(2, 10);
  const secret = process.env.JWT_SECRET!;
  const token = sign({ sub: userId, nonce }, secret, { expiresIn: "1h" });
  console.log(`issued token for ${userId} (nonce=${nonce})`);
  return token;
}
```

```typescript
// AFTER

export interface TokenDeps {
  rng: () => string;        // nonce source
  secret: string;           // injected, not read from env
  sign: (payload: object, secret: string, opts: { expiresIn: string }) => string;
  log: (msg: string) => void;
}

// SUT (under test): pure orchestration over a deps argument.
export function issueToken(userId: string, deps: TokenDeps): string {
  const nonce = deps.rng();
  const token = deps.sign({ sub: userId, nonce }, deps.secret, {
    expiresIn: "1h",
  });
  deps.log(`issued token for ${userId} (nonce=${nonce})`);
  return token;
}
// end SUT (under test)

// Composition root wires production values once, at module load.
import { sign } from "jsonwebtoken";
import { randomBytes } from "crypto";
export const productionTokenDeps: TokenDeps = {
  rng: () => randomBytes(6).toString("hex"),
  secret: process.env.JWT_SECRET!,
  sign,
  log: (m) => console.log(m),
};
export const issueProductionToken = (userId: string) =>
  issueToken(userId, productionTokenDeps);
```

Tests pass a deterministic `deps`:

```typescript
const calls: string[] = [];
const token = issueToken("u1", {
  rng: () => "fixed-nonce",
  secret: "test-secret",
  sign: (payload) => `signed:${JSON.stringify(payload)}`,
  log: (m) => calls.push(m),
});
// expect(token).toBe('signed:{"sub":"u1","nonce":"fixed-nonce"}');
// expect(calls).toEqual(["issued token for u1 (nonce=fixed-nonce)"]);
```

## How DI relates to Functional Core, Imperative Shell

DI and FCIS are complementary, not competing:

- **FCIS** separates pure decisions from I/O. After FCIS, the core needs
  no collaborators at all — it's data in, data out.
- **DI** makes the remaining I/O collaborators in the shell swappable
  for tests, configuration, and dual production wirings.

If a unit mixes decisions *and* I/O, prefer FCIS first (extract the
decision; test it directly). Then DI the shell that performs the I/O if
the shell itself needs testing or alternate wiring.

If a unit is mostly orchestration over collaborators with thin
decision-making — typical of services, handlers, repositories — DI is
the right tool on its own.

## Anti-patterns to avoid

- **Service locator masquerading as DI.** Passing a single `Container`
  parameter that the unit then queries (`container.get("db")`) is just
  hidden globals with extra steps. Inject named, typed collaborators.
- **Optional with production default.** `constructor(db = realDb)` reads
  cleaner but re-couples the unit to the production module the moment a
  caller forgets to pass `db`. Tests can silently hit real I/O. Make
  injected deps required; let the composition root supply them.
- **Newing collaborators in the constructor.** `constructor() { this.db
  = new Db() }` is identical to a hardcoded import — no seam. Move the
  `new` to the composition root.
- **Defaulted clock that reads the wall clock.** `clock: Clock = () =>
  Date.now()` puts the wall clock back as the default. Same problem as
  the previous bullet; same fix.
- **Fat interface injection.** A 30-method `IDataAccess` defeats the
  point: the unit now depends on the whole module's surface area. Inject
  only the operations the unit actually calls.
- **Setter / property injection in production code.** An object that can
  exist half-constructed (deps not yet set) is a bug magnet. Reserve
  setter injection for circular-dependency edge cases; default to
  constructor injection.
- **Injecting where there is nothing to swap.** A pure function that
  takes a `deps` parameter it doesn't use, or a class injected purely so
  tests can swap a private utility that has no I/O, is ceremony. Inject
  what genuinely varies between production and test.
- **Faking the whole world for pure arithmetic.** If a test wires an
  elaborate fake just to exercise pure logic, extract a functional core
  first (see [[functional-core-imperative-shell]]); the fake disappears.

## Validation checklist

After refactoring, verify:

- [ ] The unit's body contains no bare module references (`db.`,
      `emailService.`) or bare globals (`Date.now(`, `Math.random(`,
      `process.env`, `console.`, raw `fetch(`). Only `this.X` /
      `deps.X` member access for collaborators.
- [ ] The unit does not `new` an I/O-bearing collaborator inside its
      constructor or methods.
- [ ] Each injected collaborator is typed by a narrow interface, not by
      the concrete production class.
- [ ] Required deps have no production defaults. The composition root
      supplies them.
- [ ] Unit tests construct the SUT with fakes/stubs and pass; no
      `vi.mock` / `jest.mock` of production modules is required.
- [ ] A single composition root (factory, `main`, or module-level
      `const`) is the only place that imports the real I/O modules and
      wires them into the unit.
- [ ] At least one integration test exercises the unit with real (or
      near-real) collaborators to verify production wiring works.

## Running the skill's own tests

This skill ships with pytest tests that validate its structure
(frontmatter, required sections, BEFORE/AFTER pairing, SUT markers, and
that the `// SUT (under test)` code blocks contain no bare I/O tokens):

```bash
pytest skills/dependency-injection/tests
```