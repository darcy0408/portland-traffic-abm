"""Publish a generated .twbx to Tableau Public through Tableau Desktop Public Edition.

Why: Tableau Public has no publishing API and its web editor cannot import a workbook
file, so the only way to publish a code-generated workbook is the free desktop app's
"Save to Tableau Public As" command. This script drives that one menu path with
pywinauto (Windows UI Automation), so a republish is a command, not a click sequence.
It never touches sheets or data; the workbook is built by tableau_workbook.py.

What it does, in order: closes any running Tableau Public instance, opens the app on
the .twbx, dismisses the "File Recovery" offer if one appears (never opens the backup),
opens File > Save to Tableau Public As, types the workbook title (the dialog prefills
the file name), clicks Save, answers Yes to the overwrite prompt, then polls the site's
workbook API until the revision changes and prints it.

Requirements: Windows, Tableau Desktop Public Edition installed and signed in with
"Remember me" (the first publish on a machine shows a sign-in box: the person signs in,
this script does not handle credentials), `pip install pywinauto psutil`.

Example:
  python src/tableau_publish.py --twbx outputs/tableau/rosequarter_workbook.twbx
      --title "When I-5 Closes: Preregistered Predictions for the Rose Quarter Closure"
      --repo WhenI-5ClosesPreregisteredPredictionsfortheRoseQuarterClosure
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

import psutil
from pywinauto import Desktop

APP = r"C:\Program Files\Tableau\Tableau Public 2026.2\bin\Tabpublic.exe"
API = "https://public.tableau.com/profile/api/single_workbook/{repo}"


def app_windows():
    pids = {p.pid for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower().startswith("tabpublic")}
    return [w for w in Desktop(backend="uia").windows() if w.process_id() in pids]


def main_window(stem, timeout=120):
    """The app window once THIS workbook has loaded: the title carries the file name. A
    workbook the app refuses opens as "Book1", and matching the name keeps that empty
    book from being published over the live one."""
    for _ in range(timeout // 5):
        for w in app_windows():
            if w.window_text().startswith(f"Tableau Public - {stem}"):
                return w
        time.sleep(5)
    raise SystemExit("Tableau Public did not open the workbook in time")


def close_recovery(w):
    for d in w.descendants(control_type="Window"):
        if "File Recovery" in d.window_text():
            d.close()
            print("  dismissed the File Recovery offer (backup not opened)")
            time.sleep(1)


def revision(repo):
    with urllib.request.urlopen(API.format(repo=repo), timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--twbx", required=True)
    ap.add_argument("--title", required=True, help="exact workbook title; matching an existing one overwrites it")
    ap.add_argument("--repo", required=True, help="the workbook's RepoUrl (the /viz/<RepoUrl>/ segment)")
    ap.add_argument("--app", default=APP)
    a = ap.parse_args()

    before = revision(a.repo).get("revision")
    print(f"current revision {before}")
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower().startswith("tabpublic"):
            p.kill()
    time.sleep(3)
    subprocess.Popen([a.app, os.path.abspath(a.twbx)])
    w = main_window(os.path.splitext(os.path.basename(a.twbx))[0])
    w.set_focus(); time.sleep(1)
    close_recovery(w)

    w.menu_select("File->Save to Tableau Public As...")
    time.sleep(5)
    if any("Sign In" in d.window_text() for d in w.descendants(control_type="Window")):
        raise SystemExit("Tableau Public wants a sign-in; sign in (Remember me) and rerun")
    field = next(e for e in w.descendants(control_type="Edit")
                 if os.path.splitext(os.path.basename(a.twbx))[0] in (e.window_text() or ""))
    field.click_input(); time.sleep(0.3)
    field.type_keys("^a", pause=0.1)
    field.type_keys(a.title, with_spaces=True, pause=0.02); time.sleep(0.5)
    assert field.window_text() == a.title, f"title field reads {field.window_text()!r}"
    next(b for b in w.descendants(control_type="Button") if b.window_text().strip() == "Save").click_input()
    time.sleep(4)
    yes = next((b for b in w.descendants(control_type="Button") if b.window_text().strip() == "Yes"), None)
    if yes:
        yes.click_input(); print("  confirmed the overwrite prompt")
    time.sleep(3)
    close_recovery(w)

    for _ in range(30):
        time.sleep(10)
        j = revision(a.repo)
        if j.get("revision") != before:
            print(f"published: revision {j['revision']}, showInProfile {j['showInProfile']}, "
                  f"default view {j['defaultViewName']}")
            return
    raise SystemExit(f"revision still {before} after 5 minutes; look at the app window")


if __name__ == "__main__":
    main()
