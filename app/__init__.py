from flask import Flask, session
from .methods import find_and_post_rc_calls_to_close, refresh_rc_platform
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os

log = logging.getLogger('apscheduler.executors.default')
logging.getLogger('apscheduler.executors.default').propagate = False
log.setLevel(logging.WARNING)

fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
h = logging.StreamHandler()
h.setFormatter(fmt)
log.addHandler(h)

def job1():
    find_and_post_rc_calls_to_close()

def job2():
    refresh_rc_platform()

scheduler = BackgroundScheduler()
scheduler.add_job(job1,"interval", seconds=int(os.environ.get('seconds')))
scheduler.add_job(job2, "interval", seconds=3400)
scheduler.start()
app = Flask(__name__)
if __name__ == '__main__':
    app.run(use_reloader=False, debug=True)
