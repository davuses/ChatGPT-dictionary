import hashlib
import subprocess
import time

import schedule

# TODO:
# check md5 of db file

db_file_md5 = ""


def back_up_db_file():
    global db_file_md5
    new_md5 = hashlib.md5(open("dictionary.db", "rb").read()).hexdigest()
    print(new_md5)
    if new_md5 == db_file_md5:
        return
    subprocess.run(["bash", "./sync-backup-db.sh"])
    db_file_md5 = new_md5


schedule.every().hour.do(back_up_db_file)

while True:
    schedule.run_pending()
    time.sleep(10)  # Sleep for 1 second to avoid high CPU usage
