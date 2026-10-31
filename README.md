# Click Heatmap Tracker

A desktop app for your own computer that records **where you click** and **how often you
press each key**, and shows:

- a **heatmap** of your clicks drawn over a picture of your screen(s), and
- a **keyboard** with a counter on every key.

Everything stays on your computer.

---

## Features

- **Start and stop recording** in several ways:
  - the big button,
  - the system-tray icon (left-click it, or right-click for a menu),
  - a **global hotkey** (default **Shift+F12**) that works in any app.
- **Named sessions**, e.g. "Work" or "Gaming".
- **Click heatmap**:
  - filter by session, mouse button and time (all time, hour by hour, or a custom range);
  - show the heat map, the individual clicks, or both.
- **Key-press counter**: how often each key is pressed, shown on a keyboard. The order of keys
  is never stored.
- **Idle auto-stop (optional)**: stops recording when there has been no input for a set time.
- **Console mode**: run without a window and control recording with the hotkey.
- **Remembered settings**: window size, filters and options are kept between runs.
- **Dark mode** throughout.

---

## Installation

You need **Python 3.10 or newer**.

```bash
cd click_heatmap
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Starting the app

| Mode | Command |
|---|---|
| Window (normal) | `python main.py` |
| Window, no console window behind it (Windows) | `pythonw main.py` |
| Console mode, no window | `python main.py --console` |

Only one copy can run at a time, whether it's the window, the tray or the console.

---

## Using the app

### Recorder tab
- **Session name**
  - Type a name before you press Start. It's used for the new session.
  - While recording, editing the name (then pressing Enter or clicking elsewhere) renames the
    current session.
  - The box clears when the session ends, so each session gets its own name.
  - Leave it empty and the session is called "Session #5" and so on.
- **Switch to Console Mode**: closes the window and keeps the app running in a terminal
  (see *Console mode* below).
- **Rename Sessions…**: change the name of any earlier session.
- **Start / Stop Recording**: you can also use the hotkey or the tray icon.
- The tab shows the current session's duration, clicks, key presses and last click, plus a
  list of recent clicks.
- Minimize the window, or close it to the tray, while you work.

### Heatmap tab
- **Data**: pick a session (or all sessions) and a mouse button.
- **Time**:
  - *All time*: every click.
  - *Hour by hour*: pick a day (or *Every day*) and an hour. Use ◀ ▶ to step through the hours.
    Each hour shows how many clicks it has.
  - *Custom range*: pick start and end times, or use a preset (Last hour, Today, Last 7 days,
    Fit to data).
- **Layers**: heat map, individual clicks (coloured by mouse button), and screenshot
  background. Turn each on or off.
- **Appearance**: colours, blur, opacity, dot size, and "boost low-density areas".
- **File ▸ Capture Screen Background** takes a picture of your screen to draw the heatmap on.

### Keyboard tab
- Every key shows how many times it was pressed. Hover over a key for the exact number and
  its share of all presses.
- **Filters**: choose a **session** and a **period** (all time, today, last 24 hours,
  7 days, 30 days).
- **Numpad** shows or hides the number pad.
- **Color by frequency** shades the most-used keys from blue to orange to red.
- Keys that aren't on the drawn keyboard (media keys, browser keys and so on) are listed
  underneath.
- Holding a key down counts as one press. `1` and `!` both count toward the `1` key.

### System-tray icon
The tray icon shows a red dot while recording.

| Action | What it does |
|---|---|
| Left-click | Start or stop recording |
| Middle-click | Open the window |
| Right-click | Menu: Start/Stop Recording, Show Window, Switch to Console Mode, Quit |

If you'd rather have left-click open the window, change it in **File ▸ Settings**.
On macOS, clicking the icon always opens the menu.

### Menu bar

| Menu | What's in it |
|---|---|
| **File** | Capture Screen Background, Export Current View as PNG, Open Data Folder, Settings…, Switch to Console Mode, Quit |
| **Recording** | Start/Stop, Write Buffer to Database Now, Global Hotkey, Count Key Presses, Auto-Stop When Idle, Ignore Clicks on This Window |
| **View** | Recorder (Ctrl+1), Heatmap (Ctrl+2), Keyboard (Ctrl+3) |
| **Help** | About |

### Settings (File ▸ Settings…)

| Setting | Default | What it does |
|---|---|---|
| Global hotkey | On, **Shift+F12** | Start/stop recording from any app. Presets: Shift+F12, Ctrl+Alt+R, Ctrl+Shift+F12, Pause |
| Idle auto-stop | **Off**, 60 min | Stops recording after this long with no keyboard or mouse input |
| Ignore clicks on this window | On | Clicks on the app itself (like pressing Stop) aren't recorded |
| Count key presses | On | Counts how often each key is pressed (never the order) |
| Database write interval | 10 s | How often recorded data is saved |
| Tray icon / left-click starts and stops / notifications / close to tray / start hidden | On / On / On / Off / Off | System-tray behaviour |

---

## Console mode

Console mode runs without any window, which is handy if you just want to record in the
background. It uses the settings you chose in the window app:

- the hotkey,
- key counting,
- idle auto-stop,
- the database write interval.

```bash
python main.py --console                          # wait for the hotkey
python main.py --console --start                  # start recording straight away
python main.py --console --name "Work"            # name the sessions recorded in this run
python main.py --console --verbose                # also show every database save
```

You can also get here from the window app with **Switch to Console Mode** (Recorder tab,
File menu or tray menu):

- If the app was started from a terminal, the window closes and the app carries on in that
  terminal. A recording in progress continues without a break.
- Otherwise a new terminal window opens. A recording in progress is saved and continues
  there as a new session with the same name.

### The status line

The bottom line of the console always shows what's happening, followed by a `>` prompt where
you can type commands:

```
[ready] Press Shift+F12 or type 'start' to record > _
[REC 00:12:31] Work: 1,204 clicks, 9,877 key presses (saving in 7s) > _
[REC 00:12:45] Work: 1,204 clicks, 9,877 key presses (saved) > _
```

- **saving in 7s**: new clicks or key presses are waiting, and will be saved in 7 seconds.
- **saved**: everything is in the database. You'll see this whenever there has been no input
  for about 10 seconds.

### Commands

Press the **hotkey** to start and stop recording, or type a command and press Enter:

| Command | What it does |
|---|---|
| `start` / `stop` / `toggle` | Control recording |
| `name Work` | Name the current session and the ones after it |
| `name` | Clear the name |
| `status` | Print a summary line |
| `help` | List the commands |
| `quit` | Stop recording, save and exit |

To exit cleanly, press **Ctrl+C** or type `quit`. If you close the console window instead,
up to the last 10 seconds of key counts may be lost. Clicks are always kept.

## Your data

Everything is saved in the `data` folder (**File ▸ Open Data Folder**).

| File | What it is |
|---|---|
| `clicks.db` | All sessions, clicks and key counts (an SQLite database) |
| `click_buffer.json` | Clicks waiting to be saved to the database. It only exists while recording |
| `settings.ini` | Your settings |
| `background.png` | The screenshot drawn behind the heatmap |
| `app.lock` | Stops two copies of the app running at once |

- **How clicks are saved**: each click goes into `click_buffer.json` first. The buffer is
  moved into the database every 10 seconds and when you stop recording. If the app or
  computer crashes, those clicks are imported automatically the next time it starts.
- **How key counts are saved**: key counts are kept in memory and saved on the same schedule.
- **Deleting sessions**: use **Delete selected session** on the Heatmap tab.

---

## Privacy

- Nothing is sent anywhere. All data stays in the `data` folder.
- Key counting stores only **which key** was pressed and **how many times per hour**. The
  order is never saved, so typed text, including passwords, can't be rebuilt from it.
- You can switch key counting off under **Recording ▸ Count Key Presses**.
- The hotkey only listens for its own key combination and records nothing.

---

## Starting with your computer (optional)

**Window app**: turn on **Settings ▸ Start hidden in the tray**, then:

- **Windows**: press `Win+R`, type `shell:startup`, and create a shortcut in that folder to
  `"<project folder>\.venv\Scripts\pythonw.exe" "<project folder>\main.py"`.
- **macOS**: System Settings ▸ General ▸ Login Items.
- **Linux**: add a `.desktop` file to `~/.config/autostart/`.

**Console mode**: use the same steps, but with `python.exe` (not `pythonw.exe`) and add
`--console` at the end.

---

## Before you start (by system)

- **Windows**: works straight away. Apps running *as administrator* can only be recorded if
  this app also runs as administrator.
- **macOS**: allow your terminal (or Python) in **System Settings ▸ Privacy & Security**:
  - **Accessibility**, for clicks;
  - **Input Monitoring**, for the hotkey and key counting;
  - **Screen Recording**, for the screenshot background.
- **Linux**: you need an **X11** session. Wayland blocks recording from other apps.

---

## Troubleshooting

| Problem | What to try |
|---|---|
| The hotkey does nothing | Check **File ▸ Settings** for a hotkey message. If your F-keys control media or the browser, try **Shift+Fn+F12** or choose another preset. On macOS, allow *Input Monitoring*. |
| "Already running" message | Another copy is open. Check the system tray and any console windows. |
| Clicks appear in the wrong place | After changing monitors or display scaling, capture a new background and record a new session. |
| "Database write failed" | Another program may have `clicks.db` open. Your clicks are safe in `click_buffer.json` and will be saved automatically once it's free. |
| Some keys show 0 | The drawn keyboard is a US layout. On other layouts some keys may appear in the "not on the layout" list instead. On Windows, Numpad Enter counts as Enter. |

---
## Project files

```
click_heatmap/
├── main.py                      Starts the app (window or console mode).
├── requirements.txt             Python packages to install.
├── README.md                    This file.
├── clicktracker/
│   ├── __init__.py              Marks the folder as a Python package.
│   ├── app.py                   Chooses window or console mode and sets everything up.
│   ├── config.py                File locations and fixed values.
│   ├── preferences.py           The settings from File ▸ Settings.
│   ├── settings.py              Saves and loads settings.ini.
│   ├── capture/                 Listening to the computer
│   │   ├── __init__.py          Marks the folder as a Python package.
│   │   ├── recorder.py          Starts/stops recording, saves every 10 s, handles idle auto-stop.
│   │   ├── tracker.py           Listens for mouse clicks.
│   │   ├── keycounter.py        Listens for key presses.
│   │   ├── keynames.py          Gives every key a consistent name.
│   │   ├── hotkey.py            The global start/stop hotkey.
│   │   ├── idle.py              Finds out how long the computer has been idle.
│   │   └── screens.py           Monitor sizes and screenshots.
│   ├── storage/                 Saving and loading data
│   │   ├── __init__.py          Marks the folder as a Python package.
│   │   ├── models.py            Click data and session display names.
│   │   ├── jsonfmt.py           Writes the JSON buffer safely, one click per line.
│   │   ├── buffer.py            Holds clicks until they're saved to the database.
│   │   ├── database.py          Reads and writes the SQLite database.
│   │   ├── filters.py           Session, button and time filters for clicks.
│   │   └── store.py             Connects the buffer and database; answers questions about the data.
│   ├── cli/                     Console mode
│   │   ├── __init__.py          Marks the folder as a Python package.
│   │   ├── console.py           Console mode: hotkey, commands and the live status line.
│   │   ├── terminal.py          Reads typed keys and draws the status line.
│   │   └── launch.py            Opens console mode in a new terminal window.
│   └── ui/                      The window
│       ├── __init__.py          Marks the folder as a Python package.
│       ├── main_window.py       The main window, menu bar and tray wiring.
│       ├── recorder_tab.py      Session name, Start/Stop button and live statistics.
│       ├── heatmap_tab.py       Heatmap filters and controls.
│       ├── heatmap.py           Calculates and draws the heatmap.
│       ├── keyboard_tab.py      Keyboard tab controls and summary.
│       ├── keyboard_widget.py   Draws the keyboard with a counter on each key.
│       ├── keyboard_layout.py   Where each key sits on the drawn keyboard.
│       ├── rename_dialog.py     The Rename Sessions window.
│       ├── settings_dialog.py   The Settings window.
│       ├── tray.py              The system-tray icon and its menu.
│       ├── theme.py             Dark-mode colours and styles.
│       └── widgets.py           Small shared interface helpers.
└── data/                        Created automatically: your recordings and settings.
```