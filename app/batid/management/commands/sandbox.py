from django.core.management.base import BaseCommand

class Command(BaseCommand):



    def handle(self, *args, **options):

        # print(celery_app)

        # print('send task')

        # res = chain(
        #     Signature('tasks.dl_soure', args=["bdnb_7", "31"]), Signature('tasks.add', args=[8,4], immutable=True))()
        # print(res.get())


        # task = celery_app.send_task('tasks.import_bdtopo', args=["38"])
        # task = celery_app.send_task('tasks.inspect_candidates')
        # print(task.get())

        # celery_app.control.purge()
        pass




































