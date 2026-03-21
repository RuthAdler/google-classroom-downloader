"""
Google Classroom Materials Downloader
======================================
Downloads all course materials from your Google Classrooms and organizes
them into Google Drive folders, mirroring the topic/unit structure.

See README.md for full setup instructions.

Usage:
  python3 classroom_downloader.py
  python3 classroom_downloader.py --filter "Machine Learning" "Deep Learning"
  python3 classroom_downloader.py --output "My Backup" --filter "Python"
  python3 classroom_downloader.py --credentials path/to/creds.json --token path/to/token.pickle
  python3 classroom_downloader.py --archived
  python3 classroom_downloader.py --dry-run
"""

import os
import io
import pickle
import time
import argparse

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# ── Defaults (used when no CLI flags are provided) ────────────────────────────

DEFAULT_DRIVE_ROOT_FOLDER_NAME = "Classroom Backup"
DEFAULT_TOKEN_FILE = "token.pickle"
DEFAULT_CREDENTIALS_FILE = "credentials.json"

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

# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Back up Google Classroom materials to Google Drive.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 classroom_downloader.py
  python3 classroom_downloader.py --filter "Machine Learning" "Deep Learning"
  python3 classroom_downloader.py --output "My Backup" --filter "Python"
  python3 classroom_downloader.py --credentials path/to/creds.json
  python3 classroom_downloader.py --archived
  python3 classroom_downloader.py --dry-run
        """,
    )

    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_DRIVE_ROOT_FOLDER_NAME,
        metavar="FOLDER_NAME",
        help=f"Root folder name to create in Google Drive (default: '{DEFAULT_DRIVE_ROOT_FOLDER_NAME}')",
    )
    parser.add_argument(
        "--filter", "-f",
        nargs="+",
        default=[],
        metavar="KEYWORD",
        help="Only download courses whose names contain one of these keywords (case-insensitive). "
             "Leave out to download all courses.",
    )
    parser.add_argument(
        "--credentials", "-c",
        default=DEFAULT_CREDENTIALS_FILE,
        metavar="FILE",
        help=f"Path to your Google OAuth credentials JSON file (default: '{DEFAULT_CREDENTIALS_FILE}')",
    )
    parser.add_argument(
        "--token", "-t",
        default=DEFAULT_TOKEN_FILE,
        metavar="FILE",
        help=f"Path to the cached login token file (default: '{DEFAULT_TOKEN_FILE}')",
    )
    parser.add_argument(
        "--archived",
        action="store_true",
        help="Include archived courses in addition to active ones.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be downloaded without creating any files or folders.",
    )

    return parser.parse_args()


# ── Auth ───────────────────────────────────────────────────────────────────────

def get_credentials(credentials_file, token_file):
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    creds = None
    if os.path.exists(token_file):
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"\n❌ '{credentials_file}' not found!\n"
                    "Please follow the setup instructions in README.md\n"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)
    return creds


# ── Drive helpers ──────────────────────────────────────────────────────────────

def get_or_create_folder(drive, name, parent_id=None, dry_run=False):
    """Find a folder by name (and optional parent), create it if it doesn't exist."""
    if dry_run:
        return f"[dry-run folder: {name}]"
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


def copy_drive_file(drive, file_id, dest_folder_id, file_name, dry_run=False):
    """Copy a Drive file into a destination folder."""
    if dry_run:
        print(f"      [dry-run] Would copy: {file_name}")
        return
    try:
        drive.files().copy(
            fileId=file_id,
            body={"name": file_name, "parents": [dest_folder_id]},
        ).execute()
        print(f"      ✅ Copied: {file_name}")
    except HttpError as e:
        print(f"      ⚠️  Could not copy '{file_name}': {e}")


def download_and_upload(drive, file_id, mime_type, file_name, dest_folder_id, dry_run=False):
    """Export a Google Workspace file and upload to destination folder."""
    export_mime, ext = EXPORT_FORMATS[mime_type]
    full_name = file_name + ext
    if dry_run:
        print(f"      [dry-run] Would export: {full_name}")
        return
    try:
        from googleapiclient.http import MediaIoBaseUpload
        request = drive.files().export_media(fileId=file_id, mimeType=export_mime)
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


def save_links_file(drive, links, folder_id, filename="_links.md", dry_run=False):
    """Save a markdown file of external links into a Drive folder."""
    if not links:
        return
    if dry_run:
        print(f"      [dry-run] Would save links file: {filename} ({len(links)} link(s))")
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

def process_materials(drive, materials, dest_folder_id, dry_run=False):
    """Process a list of Classroom material objects and save to a Drive folder."""
    links = []

    for mat in materials:
        if "driveFile" in mat:
            df = mat["driveFile"].get("driveFile", mat["driveFile"])
            file_id = df.get("id")
            mime = df.get("mimeType", "")
            name = df.get("title", "Untitled")
            if not file_id:
                print(f"      ⚠️  Skipping driveFile with no id: {df}")
                continue
            if mime in EXPORT_FORMATS:
                download_and_upload(drive, file_id, mime, name, dest_folder_id, dry_run)
            else:
                copy_drive_file(drive, file_id, dest_folder_id, name, dry_run)

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

    save_links_file(drive, links, dest_folder_id, dry_run=dry_run)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print("\n🎓 Google Classroom Downloader")
    print("=" * 40)

    if args.dry_run:
        print("🔍 DRY RUN MODE — nothing will be created or downloaded\n")

    creds = get_credentials(args.credentials, args.token)
    classroom = build("classroom", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    # Create root backup folder in Drive
    root_folder_id = get_or_create_folder(drive, args.output, dry_run=args.dry_run)
    print(f"\n📁 Drive folder ready: '{args.output}'")

    # Fetch courses
    course_states = ["ACTIVE", "ARCHIVED"] if args.archived else ["ACTIVE"]
    courses_result = classroom.courses().list(courseStates=course_states).execute()
    courses = courses_result.get("courses", [])

    if not courses:
        print("\nNo courses found.")
        return

    state_label = "active + archived" if args.archived else "active"
    print(f"\nFound {len(courses)} {state_label} course(s):")
    for i, c in enumerate(courses):
        print(f"  {i+1}. {c['name']}")

    # Apply course filter
    if args.filter:
        courses = [
            c for c in courses
            if any(f.lower() in c["name"].lower() for f in args.filter)
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

        course_folder_id = get_or_create_folder(drive, course_name, root_folder_id, dry_run=args.dry_run)

        # Get topics
        topics_result = classroom.courses().topics().list(courseId=course_id).execute()
        topics = topics_result.get("topic", [])
        topic_map = {t["topicId"]: t["name"] for t in topics}
        topic_order = {t["topicId"]: i for i, t in enumerate(topics)}

        topic_folder_ids = {}
        for t in topics:
            folder_name = f"{topic_order[t['topicId']]+1:02d} - {t['name'].replace('/', '-').strip()}"
            topic_folder_ids[t["topicId"]] = get_or_create_folder(
                drive, folder_name, course_folder_id, dry_run=args.dry_run
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
                process_materials(drive, item.get("materials", []), folder_id, dry_run=args.dry_run)
                time.sleep(0.3)

        # Process items with no topic
        if no_topic:
            print(f"\n  📂 General (no topic)")
            general_folder = get_or_create_folder(drive, "00 - General", course_folder_id, dry_run=args.dry_run)
            for item in no_topic:
                print(f"    → {item.get('title', 'Untitled')}")
                process_materials(drive, item.get("materials", []), general_folder, dry_run=args.dry_run)
                time.sleep(0.3)

    if args.dry_run:
        print(f"\n\n🔍 Dry run complete. Run without --dry-run to actually download.")
    else:
        print(f"\n\n✅ Done! Check '{args.output}' in your Google Drive.")
        print("🔗 https://drive.google.com/drive/my-drive\n")


if __name__ == "__main__":
    main()
