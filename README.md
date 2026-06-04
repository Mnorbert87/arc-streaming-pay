# arc-streaming-pay

Recurring and scheduled USDC payments on Arc. "Pay this address 50 USDC every 7 days for 12
weeks." Set up a schedule, call `run_due` on a cron or loop, and it sends whatever is due.
It catches up if a run is late, and it never pays twice. Exposed as
[MCP](https://modelcontextprotocol.io) tools.

Use it for subscriptions, payroll, vesting, allowances, or any USDC drip. It is part of an
agent payments stack on Arc, alongside
[arc-agent-guard](https://github.com/Mnorbert87/arc-agent-guard) and
[arc-conditional-pay](https://github.com/Mnorbert87/arc-conditional-pay).

## How it works

A schedule pays a fixed amount to a payee at a fixed interval, starting at `start_ts`, with
an optional end date and an optional payment cap. The due-payment calculation is pure: given
how many payments have been made, it returns exactly the scheduled times that are now due,
in order. The engine sends one payment per due time and advances the count.

That gives two properties worth caring about: if `run_due` is late and several intervals
have passed, every missed payment is made (catch-up), and if it runs often, nothing is paid
twice (idempotent). A failed send stops that schedule for the run and is retried next time,
so a payment is never silently skipped.

## Tools

| Tool | What it does |
|------|--------------|
| `stream_create` | create a recurring schedule (payee, amount, interval, optional end and cap) |
| `stream_run_due` | send everything due now; call on a cron or loop |
| `stream_cancel` | stop an active schedule |
| `stream_get` / `stream_list` | inspect schedules and their payment history |
| `stream_wallet` | the paying wallet and whether a key is set |

## Example

```
stream_create(payee="0x...", amount_usdc=50, interval_seconds=604800, max_payments=12, memo="weekly payroll")
# then, every hour or so:
stream_run_due()
```

A cron entry:

```bash
0 * * * * cd /path/to/arc-streaming-pay && uv run -m streampay.run_due_cli
```

(or just call the `stream_run_due` tool from your agent on a schedule).

## Run

```bash
cp .env.example .env
# set ARC_PRIVATE_KEY to a throwaway testnet key, funded at https://faucet.circle.com
uv run -m streampay.server
```

## Tests

The scheduling and run logic (due times, catch-up, no-double, completion, cancel, failed
send retried) is covered by a deterministic suite that runs without a chain:

```bash
uv run -m pytest
```

## License

MIT, see [LICENSE](LICENSE). Part of an agent payments stack for Arc.
