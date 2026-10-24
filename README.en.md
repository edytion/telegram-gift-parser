# Telegram Gift Parser

Version **v0.1.0** · [Changelog](CHANGELOG.md)

[Русский](README.md) · **English**

If you need Telegram collectible gift data in plain files, this parser helps you collect it. It reads information through the Telegram API and writes JSONL files: one per collection and one combined file.

You will need Python and your own Telegram account. There is no paid third-party API to subscribe to.

## What you can collect

The parser saves the owner, model, backdrop, symbol, edition counts and the time each gift was checked. When Telegram does not disclose an owner's name, the record keeps whatever information is available, such as their ID.

You can check a single gift, collect gifts from discovered collections or resume an interrupted run. A normal run skips numbers already saved. Use `--refresh` when you want to check them again.

A note on coverage: this tool cannot promise to find every gift. Some collections cannot be resolved automatically, and individual numbers may be unavailable through the API. Your files reflect the time of each check; owner changes do not arrive automatically.

## Screenshots

Account setup and gift collection in the console. Entered credentials have been hidden in the screenshot.

![Parser startup and collection progress](docs/images/parser-running.png)

Results are saved as JSONL, with a separate file for each collection and a combined database in the `unified` folder.

![Collection files and JSONL output in VS Code](docs/images/output-example.png)

## A recommendation from the author

For larger collections, I recommend using **8 or more accounts**. The parser shares the work between them, which will usually make collection faster than using one account. This is a practical recommendation, not a speed guarantee: results still depend on data availability and Telegram's limits.

If the parser detects a critical error, a lost connection or an authorization problem, it stops collection across all accounts. `FLOOD_WAIT` is handled differently: the program waits for the period specified by Telegram, then continues. These checks help manage collection, but they do not protect accounts from restrictions or bans.

## Before you start, please read this

The parser includes request pauses and stops when it detects critical errors. However, Telegram decides when to restrict or ban an account, and I cannot guarantee that your accounts will be unaffected. Before you start, please follow one simple rule: **do not use your main accounts**.

Use separate secondary accounts whose possible loss would not put your conversations, contacts, gifts or other important data at risk. `FLOOD_WAIT` is a temporary request limit; waiting for it to expire does not guarantee protection from further restrictions. By using the parser, you accept these risks and take responsibility for your accounts. As the author, I cannot guarantee that they will remain accessible or unrestricted.

## Getting started

### Windows

Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/). Select **Add Python to PATH** during installation.

Download and extract the project, then double-click `START.bat`. On its first run, it creates a virtual environment and installs the dependencies. The program will then ask you to choose a language and add an account.

If you prefer PowerShell, open it in the project folder and run:

```powershell
.\START.bat
```

Keep the `.\` at the beginning: PowerShell needs it to run a file from the current folder.

For a manual installation:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\gift-parser.py
```

These commands do not require activating the environment or changing ExecutionPolicy.

### Linux and macOS

Open a terminal in the project folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python gift-parser.py
```

The examples below use Windows commands. On Linux and macOS, use `.venv/bin/python gift-parser.py` with the same arguments.

## Adding your account

The program walks you through setup on the first launch.

1. Open [my.telegram.org/apps](https://my.telegram.org/apps), sign in and create an application. You will find your **API ID** and **API hash** there.
2. Choose a local name for the account, such as `main`. Names accept up to 64 ASCII letters, digits, `_` and `-`.
3. Enter the API ID and API hash in the console. Nothing appears while you type the hash; this is expected.
4. When connecting, enter your phone number with the country code, your login code and your two-step verification password if you have one. The code may arrive in Telegram rather than by SMS.

Account settings go in `sessions/asessions.json`. Authorization is stored in a separate file under `sessions`, so you normally will not need to sign in again. If you interrupt sign-in, the next collection run will try again.

To save account settings without connecting or starting collection:

```powershell
.\START.bat --setup
```

You can add another account later:

```powershell
.\START.bat --add-account
```

To list saved names or collect with a particular account:

```powershell
.\START.bat --list-accounts
.\START.bat --account main
```

The list does not show API credentials. If you connect the same Telegram account through different sessions in a shared run, the program stops and explains the problem.

## Choosing a language

English and Russian are available on the first launch. Your choice is saved in `config.json`.

To change it, stop the parser and run this in PowerShell:

```powershell
.\START.bat --lang en
```

For Russian:

```powershell
.\START.bat --lang ru
```

These are launch commands, not input for a running parser. The program continues with a normal run after changing the language. To save your choice and exit without collecting, add `--list-accounts`:

```powershell
.\START.bat --lang en --list-accounts
```

The program's own messages are translated. Errors returned by Telegram or Telethon may remain in English. Database field names stay the same in both languages.

## Your first collection run

I suggest starting with one gift to check that sign-in works and records are being saved:

```powershell
.\START.bat https://t.me/nft/PlushPepe-1 --single
```

For a normal run across all discovered collections:

```powershell
.\START.bat
```

Passing a link without `--single` sets the starting collection; it does not limit the run to one gift.

For a short check of the first ten numbers in each discovered collection:

```powershell
.\START.bat --first 1 --last 10
```

Press **Ctrl+C** to stop. Records already written stay on disk. To resume, run the same command without `--refresh`.

## Where your data goes

| Path | Contents |
|---|---|
| `gifts_database/<Collection>.jsonl` | Records for one collection |
| `gifts_database/unified/unified.jsonl` | Combined database |
| `sessions/asessions.json` | Your accounts' API settings |
| `sessions/*.session` | Saved Telegram authorization |
| `config.json` | Run settings and language |
| `logs/` | Logs, catalog and latest run state |

Each JSONL line is a separate JSON record. You can process the files with your own scripts or import them into a database.

## Settings

The program creates `config.json` automatically. You can look at `config.example.json` in the repository to see its structure beforehand.

| Field | Default | Purpose |
|---|---|---|
| `language` | Chosen on first launch | `en` or `ru`; pressing Enter at the language prompt selects English |
| `url` | `https://t.me/nft/PlushPepe-1` | Starting gift and priority collection |
| `scan` | `true` | Discover collections; `false` checks a single gift |
| `first` | `1` | Number to start collecting from |
| `interval` | `0.3` | Minimum seconds between requests from one account |

To set the interval for one run:

```powershell
.\START.bat --interval 1
```

To check saved gifts again:

```powershell
.\START.bat --refresh
```

Refreshing appends new snapshots rather than deleting old lines. If you need the latest data, select the record with the most recent `checked_at` for each `slug`.

The `--scan` argument is kept for compatibility. It does not override `scan: false` in your settings.

To see all available arguments:

```powershell
.\START.bat --lang en --help
```

## If something goes wrong

**The program does not recognize `--lang`.** You are probably running an older version. Update the source files, including the `collector` folder. Keep your existing `sessions` folder, database and `config.json`.

**PowerShell cannot find START.bat.** Check that you are in the project folder and use `.\START.bat` rather than just `START.bat`.

**API ID or API hash error.** Check your credentials at my.telegram.org. Stop the parser and correct the account entry in `sessions/asessions.json`.

**FloodWait.** Telegram has requested a pause. The parser waits for the specified duration. A shorter request interval does not guarantee a faster run: Telegram controls the limits.

**Connection or sign-in failure.** Collection stops. Check `logs/errors.log`, resolve the issue and run the program again.

**Corrupt account file.** The parser will not overwrite it. Repair the JSON, or back up the file before setting up your accounts again.

**A collection is incomplete.** Check the logs. Some numbers may be unavailable, or a collection may not have been resolved. This alone does not prove that a gift does not exist.

Exit codes: `0` means the run finished, `2` means some collections are incomplete, `1` means an error and `130` means the user interrupted the run. Command-line argument errors may also return `2`; in that case, follow the message printed in the console.

## Before publishing your changes

Do not upload `sessions`: session files grant account access, and API hashes are stored in plaintext JSON. Keep logs and personal exports to yourself as well. These paths are already in `.gitignore`, but that does not remove files previously committed to Git history.

To remove an account from the parser, stop the program, delete its entry from `sessions/asessions.json` and remove the corresponding session file. To revoke the authorization itself, open Telegram → **Settings → Devices**.

To check your changes:

```bash
python -m unittest discover -s tests -v
```

Tests use temporary folders and do not connect to Telegram. GitHub Actions checks are configured for Windows and Linux.

This project is not affiliated with Telegram. It does not include a prebuilt gift database or a hosted API. Please follow Telegram's rules and applicable data requirements when using it.

The code is available under the [MIT license](LICENSE). You are welcome to use it in your projects and adapt it to your needs.

---

Author: **thugger / edytion** · [github.com/edytion](https://github.com/edytion)
