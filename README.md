# Anzen
Safety First across groups of trusted Discord servers. When a member gets banned on one server, other servers in the group are notified if that member is present on their server or joins at a later point in time.

# Overview
Any public Discord server staff knows that, unfortunately, Discord is unable to catch all spam/bot accounts and other problematic users. As such, a problematic account may contaminate (spam, phish, etc.) multiple servers before Discord bans the account. Currently, many groups of Discord servers where the owners / staff knows each other communicate internally to alert each other on problematic accounts. This is a tedious and manual process, which burdens moderation while still allowing many problematic accounts to slip through.

In order to alleviate this burden and to more accurately notify servers in the group of problematic members, we are working on Anzen, a [discord.py](https://discordpy.readthedocs.io/en/stable/) based [Cog](https://discordpy.readthedocs.io/en/stable/ext/commands/cogs.html) which notifies shared servers of banned accounts. Anzen sends a notification if:
- One of your members got banned in another server
- A new member joins your server which was previously banned in another server

The Discord bot is fully configurable from within the server, with many more options planned for the future. It is developed from an OSS, self-deployability, and ease of extendability perspective first:
- Integrate Anzen directly into existing discord.py bots that support Cogs
- Deploy directly with the included [Docker](https://www.docker.com/) files
- Extend existing configuration easily by updating the configuration database with [Alembic](https://alembic.sqlalchemy.org/en/latest/)

# Quick Start
## Self-deployed
1. Register a new (private!) application under [Discord Developers](https://discord.com/developers) with the `Server Members` intent
2. Clone this repo
3. Add your `.env` file, fill it in based on `.env.example`
4. Run the bot with `docker compose up -d`
5. Continue from the next section

## From existing installation
1. If the Discord Application is private, ensure you are the owner of the application or on the same [Developers Team](https://discord.com/developers/teams)
2. Ensure you have permissions to add applications to the server you want to add Anzen to
3. Obtain the installation link from the `OAuth2` section of the application (add scope `bot`)
4. Add Anzen to the server
5. Ensure Anzen has the necessary permissions (see Configuration)
6. Run `/configure` in a private channel on the server

# Configuration
Anzen is configured in two ways. First, the permissions. Anzen needs some basic permissions to function, directly related to ban events. Unfortunately, Discord does not separate the permissions for _reading_ historical bans from _handing out new bans_. This means that, for now, Anzen needs `ban members` permissions. The only safe way to use Anzen is to have ***all*** other members have at least one role, and to have Anzen be the lowest role in the hierarchy. Alternatively, you have to trust in (the security of) whoever hosts the instance of Anzen that you are inviting to your server. This is not uncommon, as many other general purpose bots such as [YAGPDB](https://yagpdb.xyz/), [Dyno](https://dyno.gg/), [Carl](https://carl.gg/), and so on, require similar or even further elevated permissions to function.
## Permissions
- `Ban Members` (See above discussion)
- `View Audit Log`
- `Send Messages`
- `Send Messages in Threads` (Optional, unused for now)
## /configure
Currently, the two main options that can be configured are:
- Which channel to log to
- Whether to ping a role when logging
## Intents
To read the ban history, Anzen requires the `Server Members` intent

# Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md)

Small contributions _strongly preferred_! Feel free to ask if you can help on any of the existing issues or open a new one and start the conversation.

# License
Licensed under the [GNU Affero General Public License v3.0](LICENSE)
