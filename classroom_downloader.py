"""
Google Classroom Materials Downloader
======================================
Downloads all course materials from your Google Classrooms and organizes
them into Google Drive folders, mirroring the topic/unit structure.

See README.md for full setup instructions.
"""

import os
import io
import pickle
import time

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# ── Configuration ─────────────────────────────────────────────────────────────

# Root folder name to create in your Google Drive
DRIVE_ROOT_FOLDER_NAME = "Classroom Backup"

# Only download courses whose names contain one of these strings (case-insensitive)
# Leave empty [] to download ALL active courses
COURSE_FILTER = []
# Example:
# COURSE_FILTER = ["Machine Learning", "Deep Learning", "Python"]

# File to cache your login token (so you don't log in every time)
TOKEN_FILE = "token.pickle"
CREDENTIALS_FILE = "credentials.json"

# Google API scopes needed
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/classroom.topics.readonly",
    "https://www.googleapis.com/auth/drive",
]

# Google Workspace export formats (converts to standard Office formats)
EXPORT_FORMATS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}

# ── Auth ───────────────────────────────────────────────────────────────────────

def get_credentials():
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"\n❌ '{CREDENTIALS_FILE}' not found!\n"
                    "Please follow the setup instructions in README.md\n"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return creds


# ── Drive helpers ──────────────────────────────────────────────────────────────

def get_or_create_folder(drive, name, parent_id=None):
    """Find a folder by name (and optional parent), create it if it doesn't exist."""
    # Escape single quotes in folder names
    safe_name = name.replace("'", "\\'")
    query = f"mimeType='application/vnd.google-apps.folder' and name='{safe_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = drive.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = drive.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def copy_drive_file(drive, file_id, dest_folder_id, file_name):
    """Copy a Drive file into a destination folder."""
    try:
        drive.files().copy(
            fileId=file_id,
            body={"name": file_name, "parents": [dest_folder_id]},
        ).execute()
        print(f"      ✅ Copied: {file_name}")
    except HttpError as e:
        print(f"      ⚠️  Could not copy '{file_name}': {e}")


def download_and_upload(drive, file_id, mime_type, file_name, dest_folder_id):
    """Export a Google Workspace file and upload to destination folder."""
    try:
        from googleapiclient.http import MediaIoBaseUpload
        export_mime, ext = EXPORT_FORMATS[mime_type]
        request = drive.files().export_media(fileId=file_id, mimeType=export_mime)
        full_name = file_name + ext

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)

        file_metadata = {"name": full_name, "parents": [dest_folder_id]}
        media = MediaIoBaseUpload(buffer, mimetype=export_mime)
        drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print(f"      ✅ Exported: {full_name}")
    except HttpError as e:
        print(f"      ⚠️  Could not export '{file_name}': {e}")


def save_links_file(drive, links, folder_id, filename="_links.md"):
    """Save a markdown file of external links into a Drive folder."""
    if not links:
        return
    from googleapiclient.http import MediaIoBaseUpload
    content = "# External Links & Videos\n\n"
    for title, url in links:
        content += f"- [{title}]({url})\n"
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")), mimetype="text/plain"
    )
    drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
    print(f"      📄 Saved links: {filename}")


# ── Material processing ────────────────────────────────────────────────────────

def process_materials(drive, materials, dest_folder_id):
    """Process a list of Classroom material objects and save to a Drive folder."""
    links = []

    for mat in materials:
        if "driveFile" in mat:
            # Classroom API nests driveFile info under mat["driveFile"]["driveFile"]
            df = mat["driveFile"].get("driveFile", mat["driveFile"])
            file_id = df.get("id")
            mime = df.get("mimeType", "")
            name = df.get("title", "Untitled")
            if not file_id:
                print(f"      ⚠️  Skipping driveFile with no id: {df}")
                continue
            if mime in EXPORT_FORMATS:
                download_and_upload(drive, file_id, mime, name, dest_folder_id)
            else:
                copy_drive_file(drive, file_id, dest_folder_id, name)

        elif "youtubeVideo" in mat:
            yt = mat["youtubeVideo"]
            links.append((yt.get("title", "YouTube Video"), yt.get("alternateLink", "")))
            print(f"      🎥 YouTube: {yt.get('title', '')}")

        elif "link" in mat:
            lk = mat["link"]
            links.append((lk.get("title", lk.get("url", "Link")), lk.get("url", "")))
            print(f"      🔗 Link: {lk.get('title', lk.get('url', ''))}")

        elif "form" in mat:
            fm = mat["form"]
            links.append((fm.get("title", "Form"), fm.get("formUrl", "")))
            print(f"      📝 Form: {fm.get('title', '')}")

        else:
            print(f"      ⚠️  Unknown material type: {list(mat.keys())}")

    save_links_file(drive, links, dest_folder_id)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("\n🎓 Google Classroom Downloader")
    print("=" * 40)

    creds = get_credentials()
    classroom = build("classroom", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    # Create root backup folder in Drive
    root_folder_id = get_or_create_folder(drive, DRIVE_ROOT_FOLDER_NAME)
    print(f"\n📁 Drive folder ready: '{DRIVE_ROOT_FOLDER_NAME}'")

    # Fetch all active courses
    courses_result = classroom.courses().list(courseStates=["ACTIVE"]).execute()
    courses = courses_result.get("courses", [])

    if not courses:
        print("\nNo active courses found.")
        return

    print(f"\nFound {len(courses)} active course(s):")
    for i, c in enumerate(courses):
        print(f"  {i+1}. {c['name']}")

    # Apply course filter
    if COURSE_FILTER:
        courses = [
            c for c in courses
            if any(f.lower() in c["name"].lower() for f in COURSE_FILTER)
        ]
        print(f"\n→ Downloading {len(courses)} filtered course(s):")
        for c in courses:
            print(f"  • {c['name']}")
    else:
        print(f"\n→ Downloading all {len(courses)} course(s)")

    print("\nStarting...\n")

    for course in courses:
        course_id = course["id"]
        course_name = course["name"].replace("/", "-").strip()
        print(f"\n{'='*50}")
        print(f"📚 {course_name}")
        print(f"{'='*50}")

        course_folder_id = get_or_create_folder(drive, course_name, root_folder_id)

        # Get topics
        topics_result = classroom.courses().topics().list(courseId=course_id).execute()
        topics = topics_result.get("topic", [])
        topic_map = {t["topicId"]: t["name"] for t in topics}
        topic_order = {t["topicId"]: i for i, t in enumerate(topics)}

        topic_folder_ids = {}
        for t in topics:
            folder_name = f"{topic_order[t['topicId']]+1:02d} - {t['name'].replace('/', '-').strip()}"
            topic_folder_ids[t["topicId"]] = get_or_create_folder(
                drive, folder_name, course_folder_id
            )

        # Fetch course materials and assignments
        course_materials, coursework = [], []
        try:
            res = classroom.courses().courseWorkMaterials().list(courseId=course_id).execute()
            course_materials = res.get("courseWorkMaterial", [])
        except HttpError as e:
            print(f"  ⚠️  Could not fetch materials: {e}")
        try:
            res = classroom.courses().courseWork().list(courseId=course_id).execute()
            coursework = res.get("courseWork", [])
        except HttpError as e:
            print(f"  ⚠️  Could not fetch coursework: {e}")

        all_items = course_materials + coursework

        if not all_items:
            print("  No materials found.")
            continue

        # Group by topic
        by_topic, no_topic = {}, []
        for item in all_items:
            tid = item.get("topicId")
            if tid and tid in topic_folder_ids:
                by_topic.setdefault(tid, []).append(item)
            else:
                no_topic.append(item)

        # Process topic folders
        for tid, items in by_topic.items():
            print(f"\n  📂 {topic_map.get(tid, tid)}")
            folder_id = topic_folder_ids[tid]
            for item in items:
                print(f"    → {item.get('title', 'Untitled')}")
                process_materials(drive, item.get("materials", []), folder_id)
                time.sleep(0.3)

        # Process items with no topic
        if no_topic:
            print(f"\n  📂 General (no topic)")
            general_folder = get_or_create_folder(drive, "00 - General", course_folder_id)
            for item in no_topic:
                print(f"    → {item.get('title', 'Untitled')}")
                process_materials(drive, item.get("materials", []), general_folder)
                time.sleep(0.3)

    print(f"\n\n✅ Done! Check '{DRIVE_ROOT_FOLDER_NAME}' in your Google Drive.")
    print("🔗 https://drive.google.com/drive/my-drive\n")


if __name__ == "__main__":
    main()
