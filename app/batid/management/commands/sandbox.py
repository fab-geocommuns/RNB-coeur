import os

from django.core.management.base import BaseCommand
from django.db.models import QuerySet

from batid.models import BuildingWithHistory, BuildingImport, Contribution, DataFix

import graphviz

class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        # rnb_id = "MPAKKY3AXP9K" # one row in history, merge
        # rnb_id = "8HZRANXWJB9E" # no event type
        # rnb_id = "ZDAABCX1DJG3" # just imported, nothing else
        # rnb_id = "AY7TT6NS73YV" # deactivate, it was not a bdg
        rnb_id = "JJ9NY489BF3V" # deactivate after datafix

        grapher = BuildingHistoryGrapher(rnb_id)
        grapher.render()


        print(f"################################################")
        print(f"Histoire du bâtiment {rnb_id}")
        print(f"################################################")
        print("")

        bdg_info(rnb_id, 0)




def bdg_info(rnb_id, indent=0):


    print("")
    print_indented(f"--------------------------------------", indent)

    history_rows = BuildingWithHistory.objects.filter(rnb_id=rnb_id).order_by('-updated_at')

    for idx, row in enumerate(history_rows):

        if idx == 0:
            print("")
            print_indented(f"> Version actuelle de {rnb_id}", indent)
            print("")

        if idx == 1:
            print("")
            print_indented(f"> Version(s) passée(s) de {rnb_id} ", indent)
            print("")


        bdg_version(row, indent)

    if history_rows[0].parent_buildings:
        print("")
        print_indented(f" >> Bâtiments parents de {rnb_id} : {row.parent_buildings}", indent)
        for parent_rnb_id in history_rows[0].parent_buildings:
            bdg_info(parent_rnb_id, indent + 4)




def bdg_version(row, indent):

    print_indented(f"RNB ID: {row.rnb_id}", indent)
    print_indented(f"is_active: {row.is_active}", indent)
    print_indented(f"status: {row.status}", indent)
    print_indented(f"shape type: {row.shape.geom_type}", indent)
    print_indented(f"addresses: {row.addresses_id}", indent)
    print_indented(f"parents: {row.parent_buildings}", indent)
    print_indented("--", indent)
    print_indented(f"A propos de cette version de {row.rnb_id} :", indent)
    print_indented(f"version id: {row.id}", indent)
    print_indented(f"version period: {row.sys_period}", indent)
    print_indented(f"event type: {row.event_type}", indent)
    print_indented(f"event user: {row.event_user}", indent)
    print_indented(f"event origin: {row.event_origin}", indent)

    if row.event_origin and row.event_origin.get('source') == 'import':
        bdg_import = BuildingImport.objects.get(id=row.event_origin.get('id'))
        print_indented(f"import {bdg_import.id}: {bdg_import.import_source}, département: {bdg_import.departement}", indent)

    if row.event_origin and row.event_origin.get('source') == 'contribution':
        contribution = Contribution.objects.get(id=row.event_origin.get('contribution_id'))
        print_indented(f"contribution {contribution.id}: {contribution.text}, ({contribution.status} by {contribution.review_user} on {contribution.status_changed_at})", indent)

    if row.event_origin and row.event_origin.get('source') == 'data_fix':
        datafix = DataFix.objects.get(id=row.event_origin.get('id'))
        print_indented(f"data fix {datafix.id}: {datafix.text}, ({datafix.user}) ", indent)

    print("")
    print("")

def print_indented(string, indent):
    print(' ' * indent + string)



class BuildingHistoryGrapher:
    def __init__(self, rnb_id):
        self.rnb_id = rnb_id
        self.dot = graphviz.Digraph(comment=f"Building {rnb_id} history")
        self.render_format = "png"

        self._bdg_history_to_graph(rnb_id)

    def _bdg_history_to_graph(self, rnb_id, child_first_identifier=None):

        history_rows = BuildingWithHistory.objects.filter(rnb_id=rnb_id).order_by('updated_at')
        # We try to complete the event types if they are missing
        history_rows = self._guess_event_types(history_rows)

        for idx, row in enumerate(history_rows):

            identifier = self._history_row_identifier(row)

            # We are seeing the first history of this building.
            # It is either created or issued from a merged|split event
            if idx == 0:

                # We add the node
                self.dot.node(identifier, f"{rnb_id}", shape="box")

                if row.event_type == 'create':
                    self._add_bdg_creation(identifier)
                elif row.event_type == 'merge' and row.is_active:
                    self._add_merged_parents(row.parent_buildings, identifier)
                elif row.event_type == 'split' and row.is_active:
                    raise NotImplementedError("Split event not implemented in grapher")
                else:
                    raise ValueError(f"First row of {rnb_id} history is not create, merge or split")

            # If we are not at the first row, we attach to the previous row
            if idx > 0:

                prev_identifier = self._history_row_identifier(history_rows[idx - 1])

                # We are seeing the merge|split event of the parents. We attach to the child(ren)
                if row.event_type == 'merge' and not row.is_active and child_first_identifier:
                    # we dont display the node. We directly attach the previoux to the child
                    self.dot.edge(prev_identifier, child_first_identifier, label="merge")
                elif row.event_type == 'split' and not row.is_active and child_first_identifier:
                    # TODO: implement split event
                    # TODO: also draw the others buildings created from the split
                    raise NotImplementedError("Split parents attachement not implemented in grapher")
                else:
                    self.dot.node(identifier, f"{rnb_id}", shape="box")
                    self.dot.edge(prev_identifier, identifier, label=row.event_type)

    def _add_bdg_creation(self, identifier):
        self.dot.node(f"{identifier}_creation", "", shape="point")
        self.dot.edge(f"{identifier}_creation", identifier, label="create")

    @staticmethod
    def _guess_event_types(rows: QuerySet):



        for idx, row in enumerate(rows):

            print(row.event_type)

            if row.event_type:
                continue

            if isinstance(row.event_origin, dict):
                if row.event_origin.get('source') == "import":

                    if idx == 0:
                        rows[idx].event_type = f"create"
                        continue

                    if idx > 0:
                        rows[idx].event_type = "update"
                        continue

            raise ValueError(f"Can't guess event types for building {row.rnb_id} history")

        return rows


    def _add_merged_parents(self, parents_rnb_ids, child_first_identifier):

        for rnb_id in parents_rnb_ids:
            self._bdg_history_to_graph(rnb_id, child_first_identifier=child_first_identifier)

    def render(self):
        self.dot.render(self.file_path, format=self.render_format, cleanup=True)

    @property
    def file_path(self):
        dl_dir = os.environ.get("DOWNLOAD_DIR")
        return f'{dl_dir}/graphviz/rnb_building_history_{self.rnb_id}'


    @staticmethod
    def _history_row_identifier(row: BuildingWithHistory):
        return f"{row.rnb_id}_{row.updated_at.timestamp()}"















