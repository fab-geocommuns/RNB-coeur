from logic.source import Source

class Downloader:

    def __init__(self, src, dpt):
        self.src = Source(src)
        self.src.set_param('dpt', dpt)

    def download(self):
        self.src.download()

    def uncompress(self):
        self.src.uncompress()
