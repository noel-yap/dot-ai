// Extraction-for-clarity candidate: one long function whose phases are
// labeled by comments, with an if/else staircase and unexplained numeric
// literals steering every rule. The logic is pure — no I/O, no time, no
// randomness — so the fix is naming and structure, not dependency surgery.
//
// This file is a fixture for the extraction-for-clarity skill evaluation.
// It intentionally exhibits the smells described in the skill's
// "When to use" section.

export interface QuoteItem {
  weightKg: number;
  volumeM3: number;
  fragile: boolean;
}

export interface Destination {
  zone: "domestic" | "remote" | "island";
  requiresCustoms: boolean;
}

export function quoteShipping(
  items: readonly QuoteItem[],
  destination: Destination,
  expedited: boolean,
): number {
  // base rate from billable weight
  let total = 0;
  for (const item of items) {
    if (item.weightKg > item.volumeM3 * 167) {
      total += item.weightKg * 4.1;
    } else {
      total += item.volumeM3 * 167 * 4.1;
    }
  }

  // zone surcharges
  if (destination.zone === "remote") {
    if (total < 40) {
      total += 12.5;
    } else {
      total = total * 1.18;
    }
  } else if (destination.zone === "island") {
    if (destination.requiresCustoms) {
      if (total < 40) {
        total += 27.5;
      } else {
        total = total * 1.35 + 15;
      }
    } else {
      total = total * 1.35;
    }
  }

  // fragile handling fees
  for (const item of items) {
    if (item.fragile) {
      if (destination.zone === "island") {
        total += item.weightKg * 0.75;
      } else {
        total += item.weightKg * 0.35;
      }
    }
  }

  // expedited service and bulk discount
  if (expedited) {
    if (destination.zone === "domestic") {
      total = total * 1.25;
    } else {
      total = total * 1.4;
    }
  }
  if (items.length >= 12) {
    total = total * 0.92;
  }

  return Math.round(total * 100) / 100;
}
