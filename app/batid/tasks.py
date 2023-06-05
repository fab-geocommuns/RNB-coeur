from celery import shared_task

from jobs.dl_source import Downloader


@shared_task
def test_all() -> str:
    print("test_all")
    return "done"


@shared_task
def dl_source(src, dpt):
    dl = Downloader(src, dpt)
    dl.download()
    dl.uncompress()
    return "done"
