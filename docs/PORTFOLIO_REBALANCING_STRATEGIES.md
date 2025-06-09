# Portfolio Rebalancing Strategies

This document introduces the basic approaches supported by this project.

## Fixed Leverage
The portfolio maintains a constant leverage ratio. It is easy to reason about and works well for most accounts.

## Enhanced Fixed Leverage
Batch execution with margin validation and hanging protection for larger orders. Use the `--batch-execution` and `--smart-orders` flags.
