"""Heat map direction loop, phase 1 (research only): the evaluator and optimizer behind research/heat_direction/PREREG.md.

Nothing here touches the bot, the protected heat curves, an order or Kalshi data. Binance spot 1-minute bars only.
The evaluator is the only reader of 2026 minutes, and `guards` decides which window it may read."""
