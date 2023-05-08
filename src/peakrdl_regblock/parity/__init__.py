from typing import TYPE_CHECKING


from .generators import ParityAssignmentGenerator


if TYPE_CHECKING:
    from ..exporter import RegblockExporter
    from systemrdl.node import AddrmapNode

class Parity:
    def __init__(self, exp:'RegblockExporter', do_fanin_stage: bool):
        self.exp = exp
        self.do_fanin_stage = do_fanin_stage

    @property
    def top_node(self) -> 'AddrmapNode':
        return self.exp.top_node
    
    @property
    def implements_parity(self) -> bool:
        return self.exp.top_node.implements_parity
    

    def get_implementation(self) -> str:
        gen = ParityAssignmentGenerator(self.exp)
        parity_assignments = gen.get_content(self.top_node)
        

        context = {
            "parity_assignments" : parity_assignments
        }

        template = self.exp.jj_env.get_template(
            "parity/templates/parity.sv"
        )
        return template.render(context)
