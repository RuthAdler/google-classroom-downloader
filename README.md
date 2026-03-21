# 📥 google-classroom-downloader

A Python script that backs up all your Google Classroom materials to Google Drive - organized by course and topic, exactly like your classroom structure.

Built for students whose courses are losing access and want to keep their materials.

---

## ✨ What it does

- Loops through all (or selected) active Google Classroom courses
- Mirrors the topic/unit folder structure into your Google Drive
- Copies PDFs, Google Docs, Slides, and Sheets directly to Drive
- Saves YouTube links, external links, and forms into a `_links.md` file per topic
- Skips courses you don't want via a `--filter` flag

### Output structure in Drive

```
📁 Classroom Backup
  📁 Course Name
    📁 01 - Topic One
       file.pdf
       slides.pptx
       _links.md
    📁 02 - Topic Two
       ...
```

---

## 🚀 Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/google-classroom-downloader.git
cd google-classroom-downloader
```

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Create Google Cloud credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Library** and enable:
   - **Google Classroom API**
   - **Google Drive API**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth 2.0 Client ID**
6. Application type: **Desktop app** → give it any name → click Create
7. Download the JSON file → rename it `credentials.json`
8. Place `credentials.json` in the same folder as the script

### 4. Add yourself as a test user

> This is required because the app is in "Testing" mode on Google Cloud.

1. Go to **APIs & Services → OAuth consent screen**
2. Scroll down to **Test users**
3. Click **+ Add Users** → enter your Google account email
4. Click **Save**

---

## ▶️ Usage

```bash
# Download all active courses
python3 classroom_downloader.py

# Download only specific courses (partial match, case-insensitive)
python3 classroom_downloader.py --filter "Machine Learning" "Deep Learning"

# Change the output folder name in Drive
python3 classroom_downloader.py --output "My Backup"

# Include archived courses as well
python3 classroom_downloader.py --archived

# Preview what would be downloaded without touching Drive
python3 classroom_downloader.py --dry-run

# Use a credentials file from a different path
python3 classroom_downloader.py --credentials path/to/credentials.json
```

---

## ⚙️ CLI Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--output` | `-o` | `"Classroom Backup"` | Root folder name to create in Google Drive |
| `--filter` | `-f` | _(all courses)_ | Only download courses matching these keywords |
| `--credentials` | `-c` | `credentials.json` | Path to your Google OAuth credentials file |
| `--token` | `-t` | `token.pickle` | Path to the cached login token file |
| `--archived` | | _(off)_ | Also include archived courses |
| `--dry-run` | | _(off)_ | Preview without downloading anything |

---

## 📁 Files

| File | Purpose |
|---|---|
| `classroom_downloader.py` | Main script |
| `credentials.json` | Your Google OAuth credentials (**don't commit this!**) |
| `token.pickle` | Auto-generated after first login — don't delete |
| `requirements.txt` | Python dependencies |

> ⚠️ **Never commit `credentials.json` or `token.pickle` to GitHub.** They are already in `.gitignore`.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: pip` | Use `pip3` instead |
| `credentials.json not found` | Make sure the file is in the same folder as the script, or use `--credentials path/to/file.json` |
| "Access blocked" in browser | Add your email as a Test User (Setup step 4) |
| Folders created but empty | Make sure materials are attached to posts in Classroom, not just typed text |
| Scope warning in terminal | Already handled — the script sets `OAUTHLIB_RELAX_TOKEN_SCOPE=1` |
| `HttpError 403` on a file | The teacher restricted download permissions on that file |

---

## 🔒 Permissions

The script requests these Google API scopes:

- `classroom.courses.readonly` — read your course list
- `classroom.coursework.me.readonly` — read assignments
- `classroom.courseworkmaterials.readonly` — read posted materials
- `classroom.topics.readonly` — read topic/unit names
- `drive` — create folders and copy files in your Drive

No data is sent anywhere — everything runs locally on your machine.

---

## 🤝 Contributing

PRs welcome! Some ideas for improvements:

- [ ] Support for downloading Zoom recording links
- [ ] Progress bar with `tqdm`
- [ ] Support for archived (not just active) courses ✅ done via `--archived`
- [ ] Dry-run mode to preview what would be downloaded ✅ done via `--dry-run`
- [ ] CLI arguments for course filter and output folder ✅ done

---

## 📄 License

MIT
