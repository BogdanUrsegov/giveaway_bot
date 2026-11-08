# Giveaway Bot

<<<<<<< HEAD
Telegram giveaway bot built with **Python 3.10**, **aiogram 3**, **SQLite/aiosqlite** and **Docker Compose**. The structure follows the modular layout used in `BogdanUrsegov/samb`: `bot/handlers`, `bot/database`, `bot/services`, `bot/states.py`, `bot/keyboards.py`, with the entry point `python -m bot.main`.

## Included in this MVP

- Admin-only `/admin` panel.
- FSM creation flow: title, description, ticket price in Telegram Stars, winner count, maximum tickets per participant, closing date/time, optional photo and target public channel.
- Draft preview before publication. The bot publishes directly to the selected channel after confirmation; the post has a deep link to the giveaway. Direct publication is used so the inline participation button is guaranteed to be attached to the channel post.
- Participant flow with channel-subscription check, already-participating status and the option to buy more tickets.
- Per-user ticket cap. Pending invoices reserve ticket capacity; the limit is revalidated at checkout and again when the successful payment is committed.
- Pre-checkout revalidates invoice ownership, exact Stars amount/currency, giveaway state, expiry and current channel subscription. Repeated valid pre-checkout updates are handled idempotently.
- Telegram Stars invoices (`XTR`), pre-checkout validation, successful-payment processing, idempotency by Telegram charge ID, unique ticket numbers and automatic refund if a successful payment cannot be fulfilled.
- Participant history with `waiting`, `won` and `lost` states.
- Admin statistics: unique participants, tickets sold, total Stars received, participant list and a link to the channel post.
- Background scheduler that closes due giveaways, selects unique winners weighted by ticket count, publishes results and notifies participants.
- `/terms` and `/paysupport` commands and versioned Terms acceptance before the purchase flow.
- SQLite WAL mode, foreign keys, busy timeout and persistent Docker volume.

## Important: paid random giveaways

`PAID_GIVEAWAYS_ENABLED` defaults to `false`. The bot will not publish or sell paid entries while this switch is disabled. A paid chance-based draw may be subject to Telegram platform rules and local lottery/gambling, consumer-protection and advertising laws. The software does **not** determine whether a particular giveaway is lawful. Before enabling paid mode, obtain an appropriate review for the jurisdictions and audiences you serve, publish complete rules and privacy information, configure a real `TERMS_URL`, and set a support contact. Do not treat accepting Telegram Stars as proof that the underlying draw is permitted.

When paid mode is enabled, `LEGAL_REVIEW_CONFIRMED=true`, a non-empty `LEGAL_REVIEW_REFERENCE`, `TERMS_URL` and `PRIVACY_URL` are required. Participants must accept the configured `TERMS_VERSION`. Increment `TERMS_VERSION` whenever the terms materially change so users must accept the new version. The confirmation is an operator attestation, not an automated legal opinion or a guarantee that the draw is lawful. `TERMS_URL` and `PRIVACY_URL` must be valid public HTTPS URLs. Paid mode remains off by default; this repository does not contain the operator's legal approval and must not silently assert that review has happened.

Telegram documents Stars as payment for digital goods and services, and requires bots to provide accessible terms, support and refund handling. That documentation alone does not establish that selling entries into a random prize draw is an allowed digital service. Check the current [Bot Developer Terms](https://telegram.org/tos/bot-developers), [Stars payment documentation](https://core.telegram.org/bots/payments-stars), and local law before switching on paid chance-based entries.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather).
2. Copy the environment template and edit it:

   ```bash
   cp .env.example .env
   ```

3. Set `BOT_TOKEN` and `ADMIN_IDS` (comma-separated numeric Telegram user IDs).
4. Add the bot as an administrator to each target **public channel** and grant permission to post messages.
5. Start the service:

   ```bash
   docker compose up -d --build
   ```

6. Follow logs:

   ```bash
   docker compose logs -f bot
   ```

The SQLite database is stored in `./data/giveaways.db` on the host and survives container recreation.

## Environment variables

| Variable | Required | Default | Description |
|---|---:|---|---|
| `BOT_TOKEN` | yes | — | Token from BotFather |
| `ADMIN_IDS` | yes | — | Comma-separated Telegram user IDs allowed to manage giveaways |
| `DB_PATH` | no | `/app/data/giveaways.db` | SQLite database path |
| `TIMEZONE` | no | `Europe/Moscow` | Timezone used for admin date input |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `PAID_GIVEAWAYS_ENABLED` | no | `false` | Paid Stars flow gate; remains false until the operator has independently verified platform and legal eligibility |
| `LEGAL_REVIEW_CONFIRMED` | when paid mode is enabled | `false` | Operator attestation that platform/legal review has been completed |
| `LEGAL_REVIEW_REFERENCE` | when paid mode is enabled | — | Internal reference to the legal review or authorization; never put confidential legal advice here |
| `TERMS_URL` | when paid mode is enabled | — | Public full terms page |
| `PRIVACY_URL` | when paid mode is enabled | — | Public privacy notice |
| `TERMS_VERSION` | no | `1` | Version of accepted terms |
| `REQUIRED_CHANNEL_URL` | no | — | Public URL for the general channel button |
| `SUPPORT_CONTACT` | no | `the bot administrator` | Contact displayed by `/paysupport` |

## Admin flow

1. Send `/admin` to the bot.
2. Press **Create giveaway** and enter all requested fields.
3. Send a photo or skip it.
4. Enter a public channel username such as `@example_channel`. The bot verifies that it is an administrator with posting rights.
5. Review the preview. Once paid mode is enabled, confirm publication. The bot publishes the actual post with the participation button.
6. Open a giveaway in **My giveaways** to inspect participants, tickets, revenue and the published post.

## User flow

- A channel post opens the bot with `/start join_<giveaway_id>`.
- The bot checks subscription to that giveaway's channel.
- Users can purchase multiple tickets in separate purchases, up to the giveaway-wide per-user cap.
- A pending Stars invoice reserves capacity; an expired or failed invoice releases that reservation.
- `/start` without a giveaway link opens the welcome screen and participation history.
- After a giveaway ends, every participant receives a win/loss message and can inspect their ticket numbers in history.

## Development and tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

`tests/test_database.py` covers ticket-limit reservation and idempotent Stars payment processing. The production container uses the same dependency set from `requirements.txt`.

## MVP limitations

- Target channels must be public (`@username`) for now.
- One bot process should run against the SQLite database; do not start multiple replicas.
- Admin cancellation/refund UI, multi-admin roles and CSV export are not included yet.
- The legal terms page is external and must be supplied by the operator before paid mode is enabled.
=======
Source package: download `giveaway_bot.tar.xz`, extract it, and follow `giveaway_bot/README.md` for setup and deployment.

The archive contains the complete Python 3.10 + aiogram 3 + SQLite + Docker Compose project. Paid chance-based draws are disabled by default and must not be enabled until the operator has verified Telegram platform eligibility and applicable law. See the detailed README inside the archive.
>>>>>>> efc020fcf7562448d2f343beb3d15d4975b35873
