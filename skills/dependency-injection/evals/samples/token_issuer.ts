// DI candidate: hidden randomness (Math.random), hidden env
// (process.env.JWT_SECRET), and hidden logging (console.log) inside a
// module-level function. Testing it requires monkey-patching Math,
// poking process.env, and silencing/inspecting console — all global
// mutations. Function-style parameter injection is the natural fix.
//
// This file is a fixture for the dependency-injection
// skill evaluation.

import { sign } from "jsonwebtoken";

export function issueToken(userId: string): string {
  const nonce = Math.random().toString(36).slice(2, 10);
  const secret = process.env.JWT_SECRET!;
  const token = sign({ sub: userId, nonce }, secret, { expiresIn: "1h" });
  console.log(`issued token for ${userId} (nonce=${nonce})`);
  return token;
}