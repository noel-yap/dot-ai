// NOT an FCIS candidate. This is a transactional saga: the I/O *sequence*
// itself is the logic. Each step's result determines whether the next runs
// and what compensation is required on failure. There is no domain decision
// hiding inside that could be hoisted into a pure function — only
// orchestration and compensation.
//
// Per the skill's "When NOT to use" section, splitting this would not
// improve testability; it would just create a fake "pure" function that
// describes the saga as data and a shell that interprets the data, with
// no test-value gain.
//
// This file is a fixture for the functional-core-imperative-shell skill
// evaluation. It is intentionally NOT a refactor candidate.

import { paymentApi, fulfillmentApi, ledgerApi } from './external';

export class SagaError extends Error {
  constructor(
    public readonly step: 'payment' | 'fulfillment' | 'ledger',
    cause: unknown,
  ) {
    super(`saga failed at ${step}: ${(cause as Error)?.message ?? cause}`);
    this.cause = cause;
  }
}

export async function executePaymentSaga(
  orderId: string,
  amount: number,
): Promise<{ paymentId: string; fulfillmentId: string }> {
  let paymentId: string | undefined;
  let fulfillmentId: string | undefined;

  try {
    const payment = await paymentApi.charge(orderId, amount);
    paymentId = payment.id;
  } catch (err) {
    throw new SagaError('payment', err);
  }

  try {
    const fulfillment = await fulfillmentApi.reserve(orderId);
    fulfillmentId = fulfillment.id;
  } catch (err) {
    await paymentApi.refund(paymentId!).catch(() => {});
    throw new SagaError('fulfillment', err);
  }

  try {
    await ledgerApi.record(orderId, paymentId!, fulfillmentId!, amount);
  } catch (err) {
    await fulfillmentApi.release(fulfillmentId!).catch(() => {});
    await paymentApi.refund(paymentId!).catch(() => {});
    throw new SagaError('ledger', err);
  }

  return { paymentId: paymentId!, fulfillmentId: fulfillmentId! };
}
