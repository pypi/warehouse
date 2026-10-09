# Billing

To be in good standing, a company organization must be active. It must also
have a subscription with the status `active`, or a manual
activation that is not expired.

Stripe owns the subscription status. Warehouse keeps a copy in
`StripeSubscription.status`, so it does not call Stripe on every request.

## How the status changes

These paths call `sync_subscription_status` in
`warehouse/subscriptions/services.py`:

- The `customer.subscription.updated` and `customer.subscription.deleted`
  webhooks, in `warehouse/api/billing.py`.
- The `reconcile_stripe_status` task. It runs each night at 23:00 UTC and
  fixes a status that a lost webhook did not update.

Other writes do not use it. A new subscription starts as `active`. The
`checkout.session.completed` webhook sets an existing subscription to
`active` with `update_subscription_status`, and records no status event.

`sync_subscription_status` records an organization event for each change it
makes. It only writes if the stored status still has the value it read. If
not, it writes nothing and records no event. So if a webhook and the task make
the same change at the same time, only one of them records it.

## Reconciliation

The task lists the subscriptions of all statuses in the configured Stripe
account, up to 100 for each request. The list does not include subscriptions
on test clocks.

The task ignores local subscriptions that are `canceled`, because Stripe
cannot reactivate a canceled subscription. It compares each other local
subscription with the Stripe copy. In the table, "local subscriptions" means
these subscriptions that are not canceled.
Metric names start with `warehouse.organizations.subscription.status.`

| Case | Result | Metric |
| ---- | ------ | ------ |
| Stripe has a different status | Updated, if the stored status still has the value the task read | `reconciled`, tag `status` |
| The ID is not in the Stripe list, but the ID of at least one other local subscription is | Skipped | `reconcile.missing` |
| There are local subscriptions, but none of their IDs is in the Stripe list | The task fails before it changes anything. Look for an API key for the wrong account or mode. | - |
| Warehouse does not know the Stripe status, for example `paused` | Skipped | `reconcile.skipped`, tag `remote_status` |
| Stripe returns a temporary error | The task raises `RetryableException` | - |

The task does not cancel a missing subscription. A missing ID does not mean
that the subscription is canceled: the list includes canceled subscriptions,
also the subscriptions of deleted customers. If `reconcile.missing` or
`reconcile.skipped` keeps going up, examine those subscriptions by hand.

## Usage reports

`update_organziation_subscription_usage_record` runs at 00:00 UTC, one hour
after reconciliation. The hour is the only thing that puts them in order, so
usage can go out against a status that is not current.

The task skips canceled subscriptions. A temporary Stripe error makes the task
raise `RetryableException`. Other Stripe errors go to the log and to the
`warehouse.organizations.subscription.usage_record.error` metric, and the task
continues with the next subscription.

## Local development

`dev/environment` sets `BILLING_BACKEND` to `MockStripeBillingService`,
which talks to the `stripe` mock container. The mock does not keep state and
returns fixed data, so it does not show how reconciliation works against Stripe.
