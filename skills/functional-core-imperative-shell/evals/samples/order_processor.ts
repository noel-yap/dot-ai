// FCIS candidate: business decisions (discount tiers, alert routing) are
// entangled with database reads, email sends, and database writes. Tests for
// the discount math currently require mocking both `db` and `emailService`.
//
// This file is a fixture for the functional-core-imperative-shell skill
// evaluation. It intentionally has the smell described in the skill's
// "When to use" section.

import { db } from './db';
import { emailService } from './email';

export interface Order {
  id: string;
  email: string;
  total: number;
  country: string;
  customerTier: 'standard' | 'gold' | 'platinum';
  itemCount: number;
}

export async function processOrder(orderId: string): Promise<void> {
  const order = await db.getOrder(orderId);

  let discountPct = 0;
  if (order.customerTier === 'platinum') {
    discountPct = 15;
  } else if (order.customerTier === 'gold' && order.total > 500) {
    discountPct = 10;
  } else if (order.itemCount >= 10) {
    discountPct = 5;
  }

  const finalTotal = order.total * (1 - discountPct / 100);

  if (finalTotal > 1000 && order.country !== 'US') {
    await emailService.send(
      order.email,
      'Large international order alert',
      `Order ${order.id} for $${finalTotal.toFixed(2)}`,
    );
  } else if (finalTotal > 1000) {
    await emailService.send(order.email, 'Large order alert', `Order ${order.id} for $${finalTotal.toFixed(2)}`);
  } else if (discountPct >= 10) {
    await emailService.send(order.email, 'Discount applied', `You saved ${discountPct}% on order ${order.id}`);
  }

  await db.updateOrderTotal(orderId, finalTotal);
  await db.updateStatus(orderId, 'processed');
}
