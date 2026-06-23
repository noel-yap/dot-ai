// NOT a DI candidate. This is a pure function: data in, data out, no
// I/O, no time, no randomness, no global access, no collaborators to
// inject. Adding a `deps` parameter would be pure ceremony — there is
// nothing to swap between production and test.
//
// Per the skill's "When NOT to use" section, applying DI here would
// introduce indirection with zero test-value gain. This file is a
// fixture for the dependency-injection skill evaluation
// and is intentionally NOT a refactor candidate.

export interface CartLine {
  unitPrice: number;
  quantity: number;
}

export interface Discount {
  kind: "percent" | "flat";
  amount: number;
}

export function subtotal(lines: readonly CartLine[]): number {
  return lines.reduce((acc, line) => acc + line.unitPrice * line.quantity, 0);
}

export function applyDiscount(amount: number, discount: Discount): number {
  if (discount.kind === "percent") {
    return amount * (1 - discount.amount / 100);
  }
  return Math.max(0, amount - discount.amount);
}

export function totalWithTax(amount: number, taxRate: number): number {
  return amount * (1 + taxRate);
}

export function computeCartTotal(
  lines: readonly CartLine[],
  discount: Discount | undefined,
  taxRate: number,
): number {
  const base = subtotal(lines);
  const discounted = discount ? applyDiscount(base, discount) : base;
  return totalWithTax(discounted, taxRate);
}