# Fraud Handling Procedure

## Scoring
Every transaction is scored from 0 to 100 using fixed rules and an anomaly model. A score of 50 or more goes to review. A score of 70 or more is recommended for blocking. The score always comes with reason codes so the customer and staff can see why.

## Customer reports
When a customer says they do not recognise a transaction the bank locates the transaction, shows its risk score, and proposes two actions: block the card if the risk is elevated, and open a dispute. Both actions need the customer's confirmation.

## Alerts
High-risk transactions raise an alert to the customer immediately. Alerts are informational and never move money.
