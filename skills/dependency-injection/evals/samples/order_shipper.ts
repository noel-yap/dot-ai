// DI candidate: collaborators are hardcoded module imports and the
// wall clock is read mid-function. Tests for `shipOrder` currently
// require `vi.mock("./db")`, `vi.mock("./email")`, and a Date.now()
// stub just to exercise the (otherwise simple) orchestration.
//
// This file is a fixture for the dependency-injection
// skill evaluation. It intentionally exhibits the smell described in
// the skill's "When to use" section.

import { db } from "./db";
import { emailService } from "./email";

export interface Order {
  id: string;
  email: string;
  region: "domestic" | "international";
}

export async function shipOrder(orderId: string): Promise<void> {
  const order = await db.getOrder(orderId);
  const shippedAt = Date.now();

  const subject =
    order.region === "international" ? "Shipped (intl)" : "Shipped";

  await emailService.send(
    order.email,
    subject,
    `Order ${order.id} shipped at ${shippedAt}`,
  );

  await db.markShipped(orderId, shippedAt);
  console.log(`shipped ${orderId} at ${shippedAt}`);
}